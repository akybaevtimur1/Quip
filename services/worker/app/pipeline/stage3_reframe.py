"""Stage 3 (Reframe): source.mp4 + сегмент → reframe_<clip_id>.json (трек окон 9:16, cut-aware).

Модель «держим план — режем на склейке» (как живой монтажёр / Opus / Vizard):
1) ffmpeg scene-detect → тайминги склеек источника внутри сегмента;
2) сэмплируем кадры (2 fps), детектим лицо MediaPipe, берём центр крупнейшего;
3) для КАЖДОГО плана (между склейками) — один устойчивый центр (медиана лиц плана;
   нет лица → держим центр предыдущего плана) → окно НЕПОДВИЖНО внутри плана;
4) на склейке окно МГНОВЕННО скачет на новый план (ступенька в stage5, не панорама).
Нет лиц вовсе → fit (весь кадр + блюр-рамки) выбирается в run/decide_reframe_mode.

Границы: PURE-математика (compute_crop_window, aggregate_center, build_shots, shot_centers)
изолирована и покрыта unit-тестами. I/O (ffmpeg/MediaPipe) — обёртки; JobError при сбое (№8).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.errors import JobError
from app.models import CropWindow
from app.pipeline.stage3_speaker import apply_dead_zone

_STAGE = "reframe"
_ASPECT_W, _ASPECT_H = 9, 16


@dataclass(frozen=True)
class ShotPlan:
    """План одного шота для per-shot рендера (R1): интервал + режим + центр.

    mode='fill' → кроп 9:16 по center (доля X); mode='fit' → весь кадр + блюр-рамки
    (b-roll/перебивка без лица — показываем широко, без узкого слайса), center=None.
    """

    t0: float
    t1: float
    mode: str
    center: float | None


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


def build_shots(cuts: list[float], duration: float) -> list[tuple[float, float]]:
    """Тайминги склеек (клип-относительные) → интервалы планов [(start, end), …].

    Склейки на 0 и в конце игнорируем, сортируем, дедупим. Пустой источник (dur≤0) → [].
    """
    if duration <= 0:
        return []
    pts = sorted({round(c, 3) for c in cuts if 0 < c < duration})
    bounds = [0.0, *pts, duration]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def scenes_to_clip_cuts(
    scenes_abs: list[tuple[float, float]], *, start: float, duration: float
) -> list[float]:
    """Сцены PySceneDetect (абсолютные сек) → КЛИП-относительные внутренние склейки.

    Граница плана i = конец сцены i (== старт сцены i+1). seek/таймкоды PySceneDetect
    АБСОЛЮТНЫЕ → офсет −start. Оставляем строго внутри (0, duration). <2 сцен → склеек нет.
    Это «офсетная» зона, где рождались флеши: точный −start = склейка попадает в нужный кадр.
    """
    if len(scenes_abs) < 2:
        return []
    cuts = [round(end - start, 3) for (_s, end) in scenes_abs[:-1]]
    return [c for c in cuts if 0.0 < c < duration]


def shot_centers(
    samples: list[tuple[float, float]],
    shots: list[tuple[float, float]],
    *,
    default: float = 0.5,
) -> list[tuple[float, float]]:
    """Один устойчивый центр на план → [(shot_start, center), …].

    center = медиана центров лиц внутри плана; план без лиц НЕ прыгает в центр, а держит
    кадр предыдущего плана (первый план без лиц → ``default``).
    """
    out: list[tuple[float, float]] = []
    prev = default
    for s0, s1 in shots:
        cs = [c for (t, c) in samples if s0 <= t < s1]
        center = aggregate_center(cs) if cs else prev
        out.append((s0, center))
        prev = center
    return out


def build_shot_plan(
    samples: list[tuple[float, float]],
    shots: list[tuple[float, float]],
    *,
    mode_setting: str = "auto",
    default_center: float = 0.5,
) -> list[ShotPlan]:
    """Каждый план источника → свой ShotPlan (режим РЕШАЕТСЯ НА ШОТ — фикс «b-roll слайсом»).

    Лицо в плане → fill (center = медиана лиц плана); нет лица → fit (широко, блюр-рамки).
    mode_setting forced 'fill'/'fit' перекрывает auto. fill без лица в плане → держим центр
    предыдущего fill-плана (детект-промах ≠ прыжок в центр; первый → default_center).
    """
    out: list[ShotPlan] = []
    prev_center = default_center
    for s0, s1 in shots:
        faces = [c for (t, c) in samples if s0 <= t < s1]
        if decide_reframe_mode(mode_setting, bool(faces)) == "fill":
            center = aggregate_center(faces) if faces else prev_center
            prev_center = center
            out.append(ShotPlan(t0=s0, t1=s1, mode="fill", center=center))
        else:
            out.append(ShotPlan(t0=s0, t1=s1, mode="fit", center=None))
    return out


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


def detect_cuts(video: Path, start: float, end: float, *, threshold: float = 0.3) -> list[float]:
    """Тайминги склеек источника внутри сегмента (ffmpeg scene-detect), КЛИП-относительные.

    -ss ДО -i → pts_time 0-based (как и рендер). Пустой список = склеек нет (один план).
    JobError при сбое ffmpeg (№8: без тихого фолбэка).
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-ss", str(start), "-to", str(end), "-i", str(video),
        "-vf", f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
    if proc.returncode != 0:
        raise JobError(_STAGE, f"ffmpeg scene код {proc.returncode}: {(proc.stderr or '')[-300:]}")
    cuts: list[float] = []
    for m in re.finditer(r"pts_time:([0-9.]+)", proc.stderr or ""):
        cuts.append(float(m.group(1)))
    return cuts


def detect_scene_cuts(
    video: Path, start: float, end: float, *, threshold: float = 27.0, min_scene_sec: float = 0.4
) -> list[float]:
    """КЛИП-относительные склейки источника через PySceneDetect ContentDetector (frame-accurate).

    Точнее сырого ffmpeg-порога: контент-разница по HSV+edge + ``min_scene_len`` (анти-дребезг,
    гасит ложные «вспышки»). ``seek``/``end_time`` абсолютные → конвертим клип-рел через
    ``scenes_to_clip_cuts``. Пустой список = один план. JobError при сбое (№8, без тихого фолбэка).

    threshold — шкала ContentDetector (~27 дефолт, НЕ ffmpeg-0..1). min_scene_sec → кадров по fps.
    """
    from scenedetect import SceneManager, open_video  # noqa: PLC0415
    from scenedetect.detectors import ContentDetector  # noqa: PLC0415

    try:
        vid = open_video(str(video))
        fps = vid.frame_rate
        sm = SceneManager()
        sm.add_detector(
            ContentDetector(threshold=threshold, min_scene_len=max(1, round(min_scene_sec * fps)))
        )
        vid.seek(start)
        sm.detect_scenes(vid, end_time=end)
        scenes = [(s.seconds, e.seconds) for (s, e) in sm.get_scene_list()]
    except Exception as e:  # PySceneDetect бросает разнородные I/O-ошибки → заворачиваем явно
        raise JobError(_STAGE, f"PySceneDetect сбой: {e}") from e
    return scenes_to_clip_cuts(scenes, start=start, duration=end - start)


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
    speaker: bool = False,
    speaker_crop_scale: float = 0.55,
    cut_threshold: float = 0.4,
    dead_zone: float = 0.12,
) -> tuple[str, list[CropWindow], bool]:
    """Сегмент → (mode, crop, face_found). mode='fill' → ОДНО окно 9:16 на план источника
    (держим внутри плана, скачок на склейке); mode='fit' → весь кадр + блюр-рамки (crop пустой).
    speaker=True → центр плана = ГОВОРЯЩЕЕ лицо (ASD); иначе крупнейшее (D2, fallback).
    Пишет reframe_<clip_id>.json (список окон с клип-относительными t = начало плана).
    """
    samples = sample_face_centers(video, start, end)
    face_found = bool(samples)
    mode = decide_reframe_mode(mode_setting, face_found)

    crop: list[CropWindow] = []
    if mode == "fill":
        if not face_found:
            crop = [compute_crop_window(src_w, src_h, 0.5, t=0.0)]
        else:
            if speaker:
                from app.pipeline.asd_reframe import speaker_windows  # noqa: PLC0415

                crop = (
                    speaker_windows(
                        video,
                        src_w,
                        src_h,
                        start,
                        end,
                        crop_scale=speaker_crop_scale,
                        cut_threshold=cut_threshold,
                        dead_zone=dead_zone,
                    )
                    or []
                )
            if not crop:  # speaker off или ASD не нашёл дорожек → cut-aware largest-face (D2)
                cuts = detect_cuts(video, start, end, threshold=cut_threshold)
                shots = build_shots(cuts, end - start)
                centers = apply_dead_zone(shot_centers(samples, shots), dead_zone=dead_zone)
                crop = [compute_crop_window(src_w, src_h, c, t=t0) for (t0, c) in centers]

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"reframe_{clip_id}.json").write_text(
        json.dumps(
            {"mode": mode, "crop": [w.model_dump() for w in crop]}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return mode, crop, face_found
