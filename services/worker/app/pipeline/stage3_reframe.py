"""Stage 3 (Reframe): source.mp4 + сегмент → reframe_<clip_id>.json (план шотов 9:16, per-shot).

Модель R1 «per-shot» (как живой монтажёр / Opus): кроп постоянен внутри плана, меняется
ровно на склейке (stage5 рендерит каждый план отдельным сегментом + concat → флешей нет
by-design). Шаги:
1) PySceneDetect ContentDetector → кадроточные склейки источника внутри сегмента;
2) сэмплируем кадры (2 fps), детектим ВСЕ лица MediaPipe (центр+ширина);
3) build_shot_plan по ГЕОМЕТРИИ лиц: нет лиц → fit (b-roll широко); 2+ РАЗНЕСЁННЫХ
   лица (не влезают в 9:16) → fit (оба видны, как OpusClip); одно/кластер → fill на
   крупнейшем. Так «широкий вид» включается осмысленно, а не только когда лиц нет;
4) speaker=True → центр fill-планов = ГОВОРЯЩИЙ (ASD); merge_shot_plan сливает смежные
   равные планы (статичная камера → 1 кодировка).

Границы: PURE-математика (compute_crop_window, aggregate_center, build_shots, scenes_to_clip_cuts,
build_shot_plan, merge_shot_plan, windows_to_shot_plan) изолирована и покрыта unit-тестами.
I/O (ffmpeg/PySceneDetect/MediaPipe) — обёртки; JobError при сбое (№8).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from app.errors import JobError
from app.models import CropWindow

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


def shot_is_wide(
    frame_centers: list[list[float]], *, crop_w_frac: float, wide_ratio: float = 0.5
) -> bool:
    """Шот «широкий» (2+ человека, тайт-кропом не охватить) → fit обоих, как OpusClip.

    frame_centers — x-центры лиц по сэмпл-кадрам шота (только кадры С лицами). Кадр широкий =
    ≥2 лица И размах (max−min) > ширины 9:16-кропа (crop_w_frac). Шот широкий, если таких
    кадров ≥ wide_ratio. Пусто → False.
    """
    if not frame_centers:
        return False
    wide = sum(1 for cxs in frame_centers if len(cxs) >= 2 and (max(cxs) - min(cxs)) > crop_w_frac)
    return wide >= wide_ratio * len(frame_centers)


def build_shot_plan(
    face_frames: list[tuple[float, list[tuple[float, float]]]],
    shots: list[tuple[float, float]],
    *,
    mode_setting: str = "auto",
    crop_w_frac: float = 0.32,
    default_center: float = 0.5,
) -> list[ShotPlan]:
    """Каждый план источника → ShotPlan по ГЕОМЕТРИИ лиц (режим РЕШАЕТСЯ НА ШОТ).

    face_frames: (t, [(cx, w_frac), …]) — ВСЕ лица по сэмпл-кадрам (2 fps). Логика auto:
    нет лиц → fit (b-roll широко); 2+ РАЗНЕСЁННЫХ лица (не влезают в 9:16) → fit (оба видны,
    говорящий всегда в кадре); одно/кластер → fill на КРУПНЕЙШЕМ (медиана крупнейших лиц/кадр).
    mode_setting forced 'fill'/'fit' перекрывает; fill без лиц → держим центр прошлого fill.
    """
    out: list[ShotPlan] = []
    prev_center = default_center
    for s0, s1 in shots:
        frames = [faces for (t, faces) in face_frames if s0 <= t < s1 and faces]
        has_face = bool(frames)
        wide = mode_setting == "auto" and shot_is_wide(
            [[cx for (cx, _w) in fr] for fr in frames], crop_w_frac=crop_w_frac
        )
        if mode_setting == "fit" or (mode_setting == "auto" and not has_face) or wide:
            out.append(ShotPlan(t0=s0, t1=s1, mode="fit", center=None))
            continue
        if has_face:  # fill на доминирующем (крупнейшем) лице каждого кадра
            center = aggregate_center([max(fr, key=lambda f: f[1])[0] for fr in frames])
        else:  # forced fill без лиц → держим прошлый центр
            center = prev_center
        prev_center = center
        out.append(ShotPlan(t0=s0, t1=s1, mode="fill", center=center))
    return out


def stabilize_plan(plan: list[ShotPlan], *, min_hold_sec: float) -> list[ShotPlan]:
    """Анти-флеш: короткий шот (длительность < min_hold_sec) НЕ переключает кадр — поглощается
    предыдущим сегментом (держим его mode+center). Гасит рапидное чередование fill↔fit и скачки
    центра на 0.4-0.8с шотах = «флеши». Первый шот не глотаем (нет предыдущего).
    """
    if not plan:
        return []
    out = [plan[0]]
    for seg in plan[1:]:
        if seg.t1 - seg.t0 < min_hold_sec:
            prev = out[-1]
            out[-1] = ShotPlan(t0=prev.t0, t1=seg.t1, mode=prev.mode, center=prev.center)
        else:
            out.append(seg)
    return out


def merge_shot_plan(plan: list[ShotPlan], *, tolerance: float = 0.0) -> list[ShotPlan]:
    """Сливаю смежные шоты с одинаковым (режим, центр) в один сегмент рендера.

    Зачем: статичная камера (N склеек, тот же кадр) → 1 кодировка, не N. Шот примыкает к
    текущему сегменту, если режим тот же И (fit, либо fill с |center − ДЕРЖИМЫЙ| ≤ tolerance).
    Сравнение с ДЕРЖИМЫМ центром сегмента (не предыдущим) → медленный дрейф не накапливается.
    Слитый сегмент: [run_t0, last_t1], центр = первый (держимый).
    """
    if not plan:
        return []
    out: list[ShotPlan] = []
    cur = plan[0]
    for nxt in plan[1:]:
        same_mode = nxt.mode == cur.mode
        joins = same_mode and (
            cur.mode == "fit"
            or (
                cur.center is not None
                and nxt.center is not None
                and abs(nxt.center - cur.center) <= tolerance
            )
        )
        if joins:
            cur = ShotPlan(t0=cur.t0, t1=nxt.t1, mode=cur.mode, center=cur.center)
        else:
            out.append(cur)
            cur = nxt
    out.append(cur)
    return out


def windows_to_shot_plan(
    windows: list[CropWindow], *, duration: float, src_w: int
) -> list[ShotPlan]:
    """Speaker-адаптер: окна говорящего (CropWindow на план, t=старт) → ShotPlan для рендера.

    center восстанавливаем из пикселей: (x + w/2)/src_w. t1 шота = старт следующего окна
    (последнего → duration). Все fill (speaker-режим подразумевает лица). Пусто → [] (fallback).
    """
    out: list[ShotPlan] = []
    for i, w in enumerate(windows):
        t1 = windows[i + 1].t if i + 1 < len(windows) else duration
        center = (w.x + w.w / 2) / src_w
        out.append(ShotPlan(t0=w.t, t1=t1, mode="fill", center=center))
    return out


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


def sample_faces(
    video: Path, start: float, end: float, *, fps: float = 2.0
) -> list[tuple[float, list[tuple[float, float]]]]:
    """(клип-время t, [(cx, w_frac), …]) — ВСЕ лица кадра по сэмплам сегмента (2 fps).

    cx, w_frac — доли ширины кадра (центр X и ширина bbox). Кадр без лиц → пустой список
    (t сохраняем). t = idx/fps клип-относительное (кадры с input-seek -ss, PTS→0).
    Нужны ВСЕ лица (не только крупнейшее): по ним решаем «широко vs тайт» на шот (2 человека).
    MediaPipe Tasks API: bbox в ПИКСЕЛЯХ → делим на ширину кадра.
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
    scene_threshold: float = 27.0,
    min_scene_sec: float = 0.4,
    min_hold_sec: float = 1.5,
    cut_threshold: float = 0.4,
    dead_zone: float = 0.12,
) -> tuple[list[ShotPlan], bool]:
    """Сегмент → (план шотов, face_found). Per-shot модель (R1): точные склейки PySceneDetect
    → планы источника; КАЖДЫЙ план решает свой режим (лицо → fill+центр; нет лица → fit,
    b-roll показываем широко). speaker=True → центр fill-планов = ГОВОРЯЩИЙ (ASD), иначе
    крупнейшее лицо. Смежные равные планы сливаем (tolerance=dead_zone). Пишет
    reframe_<clip_id>.json ({shots:[…]}); рендерит per-shot stage5 (флешей нет by-design).
    """
    duration = end - start
    face_frames = sample_faces(video, start, end)
    face_found = any(faces for (_t, faces) in face_frames)
    crop_w_frac = round(src_h * _ASPECT_W / _ASPECT_H) / src_w

    cuts = detect_scene_cuts(
        video, start, end, threshold=scene_threshold, min_scene_sec=min_scene_sec
    )
    shots = build_shots(cuts, duration)
    plan = build_shot_plan(face_frames, shots, mode_setting=mode_setting, crop_w_frac=crop_w_frac)

    if speaker and face_found and any(p.mode == "fill" for p in plan):
        from app.pipeline.asd_reframe import speaker_windows  # noqa: PLC0415

        windows = (
            speaker_windows(
                video, src_w, src_h, start, end,
                crop_scale=speaker_crop_scale, cut_threshold=cut_threshold, dead_zone=dead_zone,
            )
            or []
        )  # fmt: skip
        if windows:  # ASD нашёл дорожки → план по говорящему (иначе остаёмся на largest-face)
            plan = windows_to_shot_plan(windows, duration=duration, src_w=src_w)

    plan = merge_shot_plan(plan, tolerance=dead_zone)
    plan = merge_shot_plan(stabilize_plan(plan, min_hold_sec=min_hold_sec), tolerance=dead_zone)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"reframe_{clip_id}.json").write_text(
        json.dumps({"shots": [asdict(p) for p in plan]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return plan, face_found
