"""Stage 3 (Reframe): source.mp4 + сегмент → crop_<clip_id>.json (1 static 9:16 окно/клип).

Сэмплируем кадры сегмента (2 fps) через ffmpeg (декодит AV1), детектим лицо MediaPipe,
берём медиану центров (устойчиво к выбросам на мультиспикере) → ОДНО static-окно 9:16.
Нет лица → fallback center-crop (cx=0.5, face_found=False).

Границы: PURE-математика (compute_crop_window, aggregate_center) изолирована и покрыта
unit-тестами. I/O (ffmpeg/MediaPipe) — обёртки; JobError при сбое (правило №8).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from app.errors import JobError
from app.models import CropWindow

_STAGE = "reframe"
_ASPECT_W, _ASPECT_H = 9, 16

# MediaPipe Tasks FaceDetector требует файл модели (.tflite). Качаем в кэш при первом
# использовании (gitignored). URL стабилен (Google MediaPipe models).
_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
# stage3_reframe.py → parents[1] = app/
_FACE_MODEL_PATH = Path(__file__).resolve().parents[1] / "assets" / "blaze_face_short_range.tflite"


# ─────────────────────────── pure-математика (unit-тесты) ───────────────────────────


def compute_crop_window(src_w: int, src_h: int, center_x_frac: float, *, t: float) -> CropWindow:
    """9:16 static-окно по центру лица. x клипуется в [0, src_w-w]; y=0; h=src_h.

    JobError при нулевых размерах или если source уже 9:16-окна (кроп невозможен).
    """
    if src_w <= 0 or src_h <= 0:
        raise JobError(_STAGE, f"некорректные размеры source: {src_w}x{src_h}")
    w = round(src_h * _ASPECT_W / _ASPECT_H)
    h = src_h
    if w > src_w:
        raise JobError(_STAGE, f"source {src_w}x{src_h} уже, чем 9:16-окно ({w}px)")
    cx = min(1.0, max(0.0, center_x_frac))
    x = round(cx * src_w - w / 2)
    x = max(0, min(x, src_w - w))
    return CropWindow(t=t, x=x, y=0, w=w, h=h)


def aggregate_center(centers: list[float]) -> float:
    """Медиана центров лица (устойчива к выбросам). JobError на пустом списке."""
    vals = sorted(centers)
    n = len(vals)
    if n == 0:
        raise JobError(_STAGE, "нет центров лица для агрегации")
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def smooth_track(
    samples: list[tuple[float, float]],
    *,
    win: int = 5,
    dead_zone: float = 0.04,
    max_keyframes: int = 12,
) -> list[tuple[float, float]]:
    """Сэмплы (t, center_x) → сглаженный трек кейфреймов для динамического кропа.

    Три шага: (1) скользящее среднее окном ``win`` гасит дрожь детектора; (2) dead-zone —
    новый кейфрейм только при сдвиге центра ≥ ``dead_zone`` (статичный кадр сворачивается
    в ОДИН кейфрейм → окно не дёргается); (3) кап до ``max_keyframes`` (равномерно).
    Возвращает кейфреймы (t, center) по возрастанию t; ``[]`` на пустом входе.
    """
    n = len(samples)
    if n <= 1:
        return list(samples)

    # (1) скользящее среднее центров (порядок по времени уже монотонный)
    half = max(1, win // 2)
    smoothed: list[tuple[float, float]] = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        smoothed.append((samples[i][0], sum(c for _, c in samples[lo:hi]) / (hi - lo)))

    # (2) dead-zone: держим первый; новый кейфрейм при |Δcenter| ≥ dead_zone
    kept: list[tuple[float, float]] = [smoothed[0]]
    for t, c in smoothed[1:]:
        if abs(c - kept[-1][1]) >= dead_zone:
            kept.append((t, c))
    if len(kept) == 1:
        return kept  # статика → одно окно (build_vf отрисует константой)
    if kept[-1][0] != smoothed[-1][0]:
        kept.append(smoothed[-1])  # якорим конец, чтобы окно доехало до финала клипа

    # (3) кап до max_keyframes — равномерное прореживание, концы сохраняются
    if len(kept) > max_keyframes:
        step = (len(kept) - 1) / (max_keyframes - 1)
        idxs = sorted({round(k * step) for k in range(max_keyframes)})
        kept = [kept[i] for i in idxs]
    return kept


def decide_reframe_mode(setting: str, face_found: bool) -> str:
    """Режим reframe: 'fill' (кроп по лицу) или 'fit' (весь кадр + блюр-рамки, ничего не режет).

    auto → лицо есть: fill, нет: fit. Иначе принудительно setting ('fill'/'fit').
    """
    if setting == "fill":
        return "fill"
    if setting == "fit":
        return "fit"
    return "fill" if face_found else "fit"


# ─────────────────────────── I/O: кадры (ffmpeg) + лица (MediaPipe) ───────────────────────────


def _extract_frames(
    video: Path, start: float, end: float, out_dir: Path, *, fps: float = 2.0
) -> list[Path]:
    """ffmpeg извлекает кадры сегмента в PNG (fps кадров/с). Возвращает пути отсортированно."""
    pattern = str(out_dir / "f_%05d.png")
    cmd = [
        "ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
        "-vf", f"fps={fps}", "-f", "image2", pattern,
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
    if proc.returncode != 0:
        raise JobError(_STAGE, f"ffmpeg кадры код {proc.returncode}: {(proc.stderr or '')[-300:]}")
    return sorted(out_dir.glob("f_*.png"))


def _ensure_face_model() -> Path:
    """Вернуть путь к модели лица, скачав её в кэш при отсутствии. JobError при сбое."""
    if _FACE_MODEL_PATH.exists():
        return _FACE_MODEL_PATH
    import httpx  # noqa: PLC0415

    _FACE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get(_FACE_MODEL_URL, timeout=60.0)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise JobError(_STAGE, f"не скачать модель лица: {e}") from e
    _FACE_MODEL_PATH.write_bytes(r.content)
    return _FACE_MODEL_PATH


def sample_face_centers(
    video: Path, start: float, end: float, *, fps: float = 2.0
) -> list[tuple[float, float]]:
    """(клип-время t, доля по X) центра крупнейшего лица по кадрам сегмента.

    t = idx/fps — КЛИП-относительное (кадры берём с input-seek -ss, PTS→0). Кадры без
    лица пропускаем (трек разрежен — smooth_track это переносит). Пусто, если лиц нет.
    MediaPipe Tasks API: bounding_box в ПИКСЕЛЯХ → делим на ширину кадра.
    """
    import cv2  # noqa: PLC0415  (тяжёлые либы — ленивый импорт, pure-тесты их не тянут)
    import mediapipe as mp  # noqa: PLC0415
    from mediapipe.tasks import python as mp_python  # noqa: PLC0415
    from mediapipe.tasks.python import vision as mp_vision  # noqa: PLC0415

    model_path = _ensure_face_model()
    options = mp_vision.FaceDetectorOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        min_detection_confidence=0.5,
    )
    samples: list[tuple[float, float]] = []
    with tempfile.TemporaryDirectory() as td:
        frames = _extract_frames(video, start, end, Path(td), fps=fps)
        with mp_vision.FaceDetector.create_from_options(options) as detector:
            for idx, png in enumerate(frames):
                img = cv2.imread(str(png))
                if img is None:
                    continue
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                frame_w = rgb.shape[1]
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                res = detector.detect(mp_img)
                if not res.detections:
                    continue
                best = max(
                    res.detections, key=lambda d: d.bounding_box.width * d.bounding_box.height
                )
                bb = best.bounding_box
                cx = min(1.0, max(0.0, (bb.origin_x + bb.width / 2) / frame_w))
                samples.append((idx / fps, cx))
    return samples


def reframe_segment(
    video: Path,
    src_w: int,
    src_h: int,
    start: float,
    end: float,
    *,
    clip_id: str,
    out_dir: Path,
    mode_setting: str = "auto",
) -> tuple[str, list[CropWindow], bool]:
    """Сегмент → (mode, crop, face_found). mode='fill' → ТРЕК окон 9:16 (едет за лицом;
    статика сворачивается в 1 окно); mode='fit' → весь кадр + блюр-рамки (crop пустой).
    Пишет reframe_<clip_id>.json (список окон с клип-относительными t).
    """
    samples = sample_face_centers(video, start, end)
    face_found = bool(samples)
    mode = decide_reframe_mode(mode_setting, face_found)

    crop: list[CropWindow] = []
    if mode == "fill":
        if not face_found:
            crop = [compute_crop_window(src_w, src_h, 0.5, t=0.0)]
        else:
            keys = smooth_track(samples)
            if len(keys) == 1:
                # статичный кадр → робастный медианный центр (устойчив к выбросам детекта)
                cx = aggregate_center([c for _, c in samples])
                crop = [compute_crop_window(src_w, src_h, cx, t=0.0)]
            else:
                crop = [compute_crop_window(src_w, src_h, c, t=t) for (t, c) in keys]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"reframe_{clip_id}.json").write_text(
        json.dumps(
            {"mode": mode, "crop": [w.model_dump() for w in crop]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return mode, crop, face_found
