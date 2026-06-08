"""Stage 3 (Reframe): source.mp4 + сегмент → reframe_<clip_id>.json (V2, continuous tracking).

V2 «Continuous Reframe»: непрерывное покадровое слежение за лицом (exponential smoothing 0.15)
вместо per-shot модели R1. Нет PySceneDetect. Режим (fill/fit) решается на каждый сэмпл
(5 fps) по геометрии ВСЕХ лиц кадра. Данные → TrackRegion со сглаженной траекторией → Engine A
(ffmpeg piecewise expression) или Engine B (cv2 pipe) в stage5.

Шаги:
1) sample_faces_continuous (5 fps): кадры через ffmpeg + MediaPipe Tasks API → (t, [(cx,w), ...]);
2) build_trajectory: classify_frame (fit/fill по геометрии) + smooth_centers (exp smoothing cx)
   → [TrackPoint];
3) build_regions: consecutive-mode группировка + merge_short_regions (анти-флеш) → [TrackRegion];
4) speaker=True → ASD windows → shot_plan_to_regions (адаптер, совместимость).

Legacy ASD-путь: ShotPlan + build_shots + detect_cuts (ffmpeg) остаются для asd_reframe.py.
Выпилено: detect_scene_cuts (PySceneDetect), scenes_to_clip_cuts, build_shot_plan, stabilize_plan,
merge_shot_plan.

Границы: PURE-математика изолирована (unit-тесты); I/O (ffmpeg/MediaPipe) — обёртки, JobError.
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

_STAGE = "reframe"
_ASPECT_W, _ASPECT_H = 9, 16


# ─────────────────────────── Dataclasses ───────────────────────────


@dataclass(frozen=True)
class ShotPlan:
    """Legacy per-shot plan — сохранён для ASD speaker-пути (asd_reframe.py).

    mode='fill' → кроп 9:16 по center (доля X); mode='fit' → весь кадр + блюр-рамки.
    """

    t0: float
    t1: float
    mode: str
    center: float | None


@dataclass(frozen=True)
class TrackPoint:
    """Одна точка сглаженной траектории (V2). t — клип-относительные секунды (0-based)."""

    t: float
    mode: str  # "fill" | "fit"
    cx: float | None  # fill: сглаженный центр X (доля кадра); fit: None


@dataclass(frozen=True)
class TrackRegion:
    """Непрерывный регион с одним режимом (V2).

    fill: points — сглаженная траектория cx (build_fill_crop_expr → ffmpeg expr);
    fit: points=() (весь кадр + блюр-рамки, нет траектории).
    """

    t0: float
    t1: float
    mode: str  # "fill" | "fit"
    points: tuple[TrackPoint, ...]  # fill: значимые cx; fit: пустой tuple


# MediaPipe Tasks FaceDetector
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


def shot_is_wide(
    frame_centers: list[list[float]], *, crop_w_frac: float, wide_ratio: float = 0.5
) -> bool:
    """Шот «широкий»: 2+ разнесённых лица (размах > ширины 9:16-кропа) → fit обоих.

    frame_centers — x-центры лиц по сэмпл-кадрам (только кадры С лицами). Кадр широкий =
    ≥2 лица И размах > crop_w_frac. Шот широкий, если таких кадров ≥ wide_ratio. Пусто → False.
    """
    if not frame_centers:
        return False
    wide = sum(1 for cxs in frame_centers if len(cxs) >= 2 and (max(cxs) - min(cxs)) > crop_w_frac)
    return wide >= wide_ratio * len(frame_centers)


def smooth_centers(samples: list[float | None], smoothing: float = 0.15) -> list[float]:
    """Exponential smoothing по X-центрам лиц (как в прототипе). None=нет лица → держим.

    cx_smooth[i] = cx_smooth[i-1] + smoothing * (cx_raw[i] - cx_smooth[i-1]).
    Нет лица → держим последний сглаженный (или 0.5 если ни одного ещё не было).
    """
    result: list[float] = []
    last = 0.5
    for cx in samples:
        if cx is not None:
            last = last + smoothing * (cx - last)
        result.append(last)
    return result


def classify_frame(all_faces: list[tuple[float, float]], crop_w_frac: float) -> str:
    """fit/fill на один кадр по геометрии лиц (ВСЕ лица кадра).

    Нет лиц → fit; 2+ разнесённых (размах > crop_w_frac) → fit; одно/кластер → fill.
    """
    if not all_faces:
        return "fit"
    if shot_is_wide([[cx for cx, _ in all_faces]], crop_w_frac=crop_w_frac):
        return "fit"
    return "fill"


def build_trajectory(
    raw_samples: list[tuple[float, list[tuple[float, float]]]],
    smoothing: float,
    crop_w_frac: float,
    *,
    mode_setting: str = "auto",
) -> list[TrackPoint]:
    """raw_samples (t, [(cx,w),...]) → [TrackPoint] с exponential smoothing.

    Classify per-frame (auto/fit/fill), smooth_centers на cx крупнейшего лица.
    Для fit-точек cx=None (используется прежде всего для анти-флеш в build_regions).
    """
    cx_raws: list[float | None] = [
        max(faces, key=lambda f: f[1])[0] if faces else None for _, faces in raw_samples
    ]
    cx_smoothed = smooth_centers(cx_raws, smoothing)
    points: list[TrackPoint] = []
    for (t, faces), cx_sm in zip(raw_samples, cx_smoothed, strict=False):
        if mode_setting == "fit":
            mode = "fit"
        elif mode_setting == "fill":
            mode = "fill"
        else:  # auto
            mode = classify_frame(faces, crop_w_frac)
        cx = cx_sm if mode == "fill" else None
        points.append(TrackPoint(t=t, mode=mode, cx=cx))
    return points


def merge_short_regions(regions: list[TrackRegion], min_hold_sec: float) -> list[TrackRegion]:
    """Анти-флеш V2: регион < min_hold_sec поглощается предыдущим (держим его mode+points).

    Гасит рапидное чередование fill↔fit на коротких (<1.5с) планах — «флеши».
    Первый регион не глотаем (нет предыдущего).
    """
    if not regions:
        return []
    out = [regions[0]]
    for reg in regions[1:]:
        if reg.t1 - reg.t0 < min_hold_sec:
            prev = out[-1]
            out[-1] = TrackRegion(t0=prev.t0, t1=reg.t1, mode=prev.mode, points=prev.points)
        else:
            out.append(reg)
    return out


def build_regions(
    trajectory: list[TrackPoint],
    min_hold_sec: float,
    *,
    duration: float | None = None,
) -> list[TrackRegion]:
    """TrackPoint список → TrackRegion список (режим-группировка + merge_short_regions).

    Consecutive одинаковые режимы → один регион. t1 последнего = duration (если задан)
    или t последнего сэмпла. merge_short_regions применяется в конце.
    """
    if not trajectory:
        return []
    regions: list[TrackRegion] = []
    i = 0
    while i < len(trajectory):
        cur_mode = trajectory[i].mode
        j = i + 1
        while j < len(trajectory) and trajectory[j].mode == cur_mode:
            j += 1
        seg = trajectory[i:j]
        t0 = seg[0].t
        if j < len(trajectory):
            t1 = trajectory[j].t
        else:
            t1 = duration if duration is not None else seg[-1].t
        if cur_mode == "fit":
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
        else:
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fill", points=tuple(seg)))
        i = j
    return merge_short_regions(regions, min_hold_sec)


def shot_plan_to_regions(plan: list[ShotPlan]) -> list[TrackRegion]:
    """Adapter: ShotPlan (ASD speaker path) → TrackRegion для render_clip V2.

    fill-шот → TrackRegion fill с одной точкой на t=t0; fit-шот → пустые points.
    """
    regions: list[TrackRegion] = []
    for s in plan:
        if s.mode == "fit":
            regions.append(TrackRegion(t0=s.t0, t1=s.t1, mode="fit", points=()))
        else:
            pt = TrackPoint(t=s.t0, mode="fill", cx=s.center)
            regions.append(TrackRegion(t0=s.t0, t1=s.t1, mode="fill", points=(pt,)))
    return regions


# ─────────────────────── Legacy ASD helpers (сохранены для asd_reframe.py) ───────────────────────


def build_shots(cuts: list[float], duration: float) -> list[tuple[float, float]]:
    """Тайминги склеек (клип-относительные) → интервалы планов [(start, end), …].

    Используется ASD speaker-путём (asd_reframe.py). Склейки на 0 и в конце игнорируем.
    """
    if duration <= 0:
        return []
    pts = sorted({round(c, 3) for c in cuts if 0 < c < duration})
    bounds = [0.0, *pts, duration]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def detect_cuts(video: Path, start: float, end: float, *, threshold: float = 0.3) -> list[float]:
    """Тайминги склеек источника (ffmpeg scene-detect), КЛИП-относительные.

    Используется ASD speaker-путём (asd_reframe.py). JobError при сбое (№8).
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


def windows_to_shot_plan(
    windows: list[CropWindow], *, duration: float, src_w: int
) -> list[ShotPlan]:
    """Speaker-адаптер: окна говорящего (CropWindow) → ShotPlan (для ASD → shot_plan_to_regions).

    center восстанавливаем из пикселей: (x + w/2)/src_w. t1 шота = старт следующего окна
    (последнего → duration). Пусто → [].
    """
    out: list[ShotPlan] = []
    for i, w in enumerate(windows):
        t1 = windows[i + 1].t if i + 1 < len(windows) else duration
        center = (w.x + w.w / 2) / src_w
        out.append(ShotPlan(t0=w.t, t1=t1, mode="fill", center=center))
    return out


# ─────────────────────────── I/O: кадры (ffmpeg) + лица (MediaPipe) ───────────────────────────


def _extract_frames(
    video: Path, start: float, end: float, out_dir: Path, *, fps: float = 5.0
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


def sample_faces_continuous(
    video: Path, start: float, end: float, *, fps: float = 5.0
) -> list[tuple[float, list[tuple[float, float]]]]:
    """(клип-время t, [(cx, w_frac), …]) — ВСЕ лица кадра по сэмплам сегмента.

    Дефолт fps=5 (V2, непрерывное слежение; R1 был 2 fps). t клип-относительное (0-based,
    от -ss seek). ВСЕ лица нужны для classify_frame (геометрия широкого плана).
    MediaPipe Tasks API: bbox в ПИКСЕЛЯХ → делим на ширину кадра.
    """
    import cv2  # noqa: PLC0415
    import mediapipe as mp  # noqa: PLC0415
    from mediapipe.tasks import python as mp_python  # noqa: PLC0415
    from mediapipe.tasks.python import vision as mp_vision  # noqa: PLC0415

    model_path = _ensure_face_model()
    options = mp_vision.FaceDetectorOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        min_detection_confidence=0.5,
    )
    samples: list[tuple[float, list[tuple[float, float]]]] = []
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
                faces: list[tuple[float, float]] = []
                for d in res.detections:
                    bb = d.bounding_box
                    cx = min(1.0, max(0.0, (bb.origin_x + bb.width / 2) / frame_w))
                    faces.append((cx, bb.width / frame_w))
                samples.append((idx / fps, faces))
    return samples


def _write_reframe_json(out_dir: Path, clip_id: str, regions: list[TrackRegion]) -> None:
    (out_dir / f"reframe_{clip_id}.json").write_text(
        json.dumps(
            {
                "regions": [
                    {
                        "t0": r.t0,
                        "t1": r.t1,
                        "mode": r.mode,
                        "points": [{"t": p.t, "mode": p.mode, "cx": p.cx} for p in r.points],
                    }
                    for r in regions
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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
    face_fps: float = 5.0,
    smoothing: float = 0.15,
    min_hold_sec: float = 1.5,
    cut_threshold: float = 0.4,
    dead_zone: float = 0.12,
) -> tuple[list[TrackRegion], bool]:
    """Сегмент → (регионы V2, face_found). Continuous per-frame tracking.

    sample_faces_continuous → build_trajectory → build_regions → merge_short_regions.
    speaker=True → ASD windows → shot_plan_to_regions (fallback → standard path).
    Пишет reframe_<clip_id>.json ({regions:[...]}).
    """
    duration = end - start
    crop_w_frac = round(src_h * _ASPECT_W / _ASPECT_H) / src_w

    face_frames = sample_faces_continuous(video, start, end, fps=face_fps)
    face_found = any(faces for (_t, faces) in face_frames)

    regions: list[TrackRegion]

    if speaker and face_found:
        from app.pipeline.asd_reframe import speaker_windows  # noqa: PLC0415

        windows = (
            speaker_windows(
                video, src_w, src_h, start, end,
                crop_scale=speaker_crop_scale,
                cut_threshold=cut_threshold,
                dead_zone=dead_zone,
            )
            or []
        )  # fmt: skip
        if windows:
            shot_plan = windows_to_shot_plan(windows, duration=duration, src_w=src_w)
            regions = shot_plan_to_regions(shot_plan)
            out_dir.mkdir(parents=True, exist_ok=True)
            _write_reframe_json(out_dir, clip_id, regions)
            return regions, face_found

    trajectory = build_trajectory(face_frames, smoothing, crop_w_frac, mode_setting=mode_setting)
    regions = build_regions(trajectory, min_hold_sec, duration=duration)

    if not regions:
        regions = [TrackRegion(t0=0.0, t1=duration, mode="fit", points=())]

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_reframe_json(out_dir, clip_id, regions)
    return regions, face_found
