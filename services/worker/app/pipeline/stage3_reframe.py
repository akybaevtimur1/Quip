"""Stage 3 (Reframe): source.mp4 + сегмент → reframe_<clip_id>.json (per-shot, cut-aligned).

Главный путь (ASD): detect_scene_cuts → build_shots_frames → score_tracks_in_segment
→ plan_regions → merge_short_regions → [TrackRegion] (frame-accurate, no flashes).

Редактор-путь (reframe_cache.py): sample_faces_continuous + detect_cuts → build_shots
→ build_regions_from_shots (секунды, V2-legacy).

Каждый шот = стабильный mode (fill/fit) + центр говорящего (plan_regions). Короткие шоты
(<1.5с) поглощаются соседним (merge_short_regions). Per-shot границы = реальные склейки.

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
class TrackPoint:
    """Одна точка сглаженной траектории (V2). t — клип-относительные секунды (0-based)."""

    t: float
    mode: str  # "fill" | "fit"
    cx: float | None  # fill: сглаженный центр X (доля кадра); fit: None


@dataclass(frozen=True)
class TrackRegion:
    """Непрерывный регион с одним режимом (V2).

    fill: points — сглаженная траектория cx (build_fill_crop_expr → ffmpeg expr);
    fit: points=() (весь кадр + блюр-рамки, нет траектории);
    split (v3): points = траектория ВЕРХНЕГО спикера (меньший cx),
    points_b = траектория НИЖНЕГО (два кропа 1080×960 + vstack).
    """

    t0: float
    t1: float
    mode: str  # "fill" | "fit" | "split"
    points: tuple[TrackPoint, ...]  # fill/split: значимые cx; fit: пустой tuple
    points_b: tuple[TrackPoint, ...] = ()  # только split: второй спикер


@dataclass(frozen=True)
class SpeakerTrack:
    """Дорожка лица с ASD-скором (выход Pass-1 анализа, вход plan_regions).

    f0/f1 — клип-относительные КАДРЫ (полуинтервал [f0, f1)). cx — per-frame X-центр (доля
    кадра), len == f1-f0. width — средняя ширина лица (доля; для largest-face фолбэка и wide).
    speak — средний ASD speak-score (>0 ≈ говорит).
    """

    f0: int
    f1: int
    cx: tuple[float, ...]
    width: float
    speak: float


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


def smooth_centers(
    samples: list[float | None], smoothing: float = 0.15, *, init: float = 0.5
) -> list[float]:
    """Exponential smoothing по X-центрам лиц (как в прототипе). None=нет лица → держим.

    cx_smooth[i] = cx_smooth[i-1] + smoothing * (cx_raw[i] - cx_smooth[i-1]).
    Нет лица → держим последний сглаженный (или init если ни одного ещё не было).
    init=0.5 по умолчанию; передай первый cx лица, чтобы избежать пана от центра.
    """
    result: list[float] = []
    last = init
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
            out[-1] = TrackRegion(
                t0=prev.t0, t1=reg.t1, mode=prev.mode, points=prev.points, points_b=prev.points_b
            )
        else:
            out.append(reg)
    return out


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


def build_shots_frames(cuts: list[int], total_frames: int) -> list[tuple[int, int]]:
    """Номера кадров склеек (клип-относительные) → интервалы шотов [(f0, f1), …] в КАДРАХ. PURE.

    Frame-accurate замена build_shots (тот в секундах). Склейки на 0 и в конце игнорируем,
    дубликаты схлопываем. Пустой/нулевой total → []. Единица — КАДР (не float-секунда),
    чтобы граница шота попала ровно на кадр реальной склейки (нет рассинхрона в рендере).
    """
    if total_frames <= 0:
        return []
    pts = sorted({c for c in cuts if 0 < c < total_frames})
    bounds = [0, *pts, total_frames]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def resample_track(track: SpeakerTrack, src_fps: float, dst_fps: float) -> SpeakerTrack:
    """Пересэмплировать дорожку из сетки src_fps в сетку dst_fps (frame-grid conversion). PURE.

    ASD сэмплит лица @25fps (модель LR-ASD требует 4:1 audio/video), но геометрия
    (склейки/шоты/регионы) и рендер работают в НАТИВНОМ fps источника. Без этой конвертации
    границы регионов (кадры 25fps) не попадают на кадры рендера (нативный fps) → флеш-кадр.
    cx пересэмплируем nearest-neighbor по времени; width/speak — скаляры. f0/f1 — по времени.
    """
    if src_fps == dst_fps or not track.cx:
        return track
    nf0 = round(track.f0 / src_fps * dst_fps)
    nf1 = max(nf0 + 1, round(track.f1 / src_fps * dst_fps))
    n_src = len(track.cx)
    cx_new: list[float] = []
    for nf in range(nf0, nf1):
        idx = round(nf / dst_fps * src_fps) - track.f0  # время кадра dst → индекс в src-сетке
        cx_new.append(track.cx[max(0, min(n_src - 1, idx))])
    return SpeakerTrack(f0=nf0, f1=nf1, cx=tuple(cx_new), width=track.width, speak=track.speak)


def _track_cx_in_shot(t: SpeakerTrack, f0: int, f1: int) -> list[float]:
    """cx дорожки t для кадров пересечения с шотом [f0, f1). PURE."""
    lo, hi = max(t.f0, f0), min(t.f1, f1)
    return [t.cx[f - t.f0] for f in range(lo, hi)]


def _is_wide_shot(active: list[SpeakerTrack], f0: int, f1: int, spread_min: float) -> bool:
    """2+ дорожек, разнесённых по X сильнее spread_min (доля кадра) → широкий план (fit). PURE."""
    reps: list[float] = []
    for t in active:
        cxs = _track_cx_in_shot(t, f0, f1)
        if cxs:
            reps.append(sum(cxs) / len(cxs))
    return len(reps) >= 2 and (max(reps) - min(reps)) > spread_min


def _split_pair(
    active: list[SpeakerTrack],
    f0: int,
    f1: int,
    spread_min: float,
    coverage_min: float = 0.6,
) -> tuple[SpeakerTrack, SpeakerTrack] | None:
    """Пара для split: РОВНО 2 устойчивых трека (покрытие ≥ coverage_min шота),
    разнесённых сильнее spread_min. Возвращает (левый, правый) по среднему cx. PURE.

    3+ устойчивых лица или нестабильные треки → None (остаётся fit — требование
    фаундера «оставить горизонтальный вид для других ситуаций»).
    """
    shot_len = f1 - f0
    if shot_len <= 0:
        return None
    stable: list[tuple[float, SpeakerTrack]] = []
    for t in active:
        cxs = _track_cx_in_shot(t, f0, f1)
        if len(cxs) >= coverage_min * shot_len:
            stable.append((sum(cxs) / len(cxs), t))
    if len(stable) != 2:
        return None
    stable.sort(key=lambda p: p[0])
    (cx_a, ta), (cx_b, tb) = stable
    if cx_b - cx_a <= spread_min:
        return None  # кластер — это fill-кейс
    return ta, tb


def _pick_target(active: list[SpeakerTrack], speak_threshold: float) -> SpeakerTrack | None:
    """Выбрать дорожку в кадр: макс. speak; если ниже порога → макс. width (largest-face). PURE."""
    if not active:
        return None
    best = max(active, key=lambda t: t.speak)
    if best.speak < speak_threshold:
        best = max(active, key=lambda t: t.width)
    return best


def _track_trajectory(
    t: SpeakerTrack,
    f0: int,
    f1: int,
    fps: float,
    smoothing: float,
    min_delta: float = 0.03,
    *,
    init_cx: float | None = None,
) -> tuple[TrackPoint, ...]:
    """Сглаженная cx-траектория дорожки внутри шота → TrackPoint'ы (клип-время = кадр/fps). PURE.

    init_cx (НЕ None) = центр, на котором закончился ПРЕДЫДУЩИЙ fill-регион → пан EMA-едет
    от него к новому говорящему (непрерывность поперёк склейки, нет «телепорта»). None →
    init = первый реальный cx (старое поведение, пан не «течёт» от центра).
    Dead-zone: новый кейфрейм только при сдвиге ≥ min_delta от последнего — убирает
    per-frame дрожание детектора, сохраняет следование реальному движению человека.
    ⚠️ Границы режима (fill/fit) НЕ трогаем — инвариант docs/REFRAME_FPS_GRID_INVARIANT.md цел:
    меняется только стартовое значение cx-выражения внутри fill-региона (рендер не меняется).
    """
    lo, hi = max(t.f0, f0), min(t.f1, f1)
    raw = [t.cx[f - t.f0] for f in range(lo, hi)]
    if not raw:
        return (TrackPoint(t=f0 / fps, mode="fill", cx=0.5 if init_cx is None else init_cx),)
    sm = smooth_centers([c for c in raw], smoothing, init=raw[0] if init_cx is None else init_cx)
    last_cx = sm[0]
    pts: list[TrackPoint] = [TrackPoint(t=lo / fps, mode="fill", cx=last_cx)]
    for i, c in enumerate(sm[1:], 1):
        if abs(c - last_cx) >= min_delta:
            pts.append(TrackPoint(t=(lo + i) / fps, mode="fill", cx=c))
            last_cx = c
    return tuple(pts)


def plan_regions(
    shots: list[tuple[int, int]],
    tracks: list[SpeakerTrack],
    fps: float,
    *,
    crop_w_frac: float,
    smoothing: float = 0.15,
    speak_threshold: float = 0.0,
    wide_spread_min: float | None = None,
    mode_setting: str = "auto",
    split_enabled: bool = False,
) -> list[TrackRegion]:
    """Cut-aligned планировщик: на КАЖДЫЙ шот один режим + траектория. Сердце Pass-1. PURE.

    shots — интервалы [(f0,f1)] в КАДРАХ (build_shots_frames). На шот:
      широкий (2+ разнесённых дорожек) → split_enabled И ровно 2 устойчивых трека →
      split (верх/низ, оба full-bleed); иначе fit (пейзаж/толпа/3+ лиц — «горизонтальный
      вид» остаётся); не широкий → fill на говорящем (макс. speak), при молчании ASD
      (< speak_threshold) → фолбэк на крупнейшее лицо; нет дорожек → fit.
    mode_setting "fill"/"fit" — глобальный оверрайд. wide_spread_min дефолт = crop_w_frac.
    Границы регионов = границы шотов (= кадры склеек) → смена режима только на склейке
    (инвариант docs/REFRAME_FPS_GRID_INVARIANT.md не трогаем: split не двигает границы).
    """
    spread_min = crop_w_frac if wide_spread_min is None else wide_spread_min
    regions: list[TrackRegion] = []
    # cx конца предыдущего fill-региона → новый fill EMA-едет от него (непрерывность поперёк
    # склейки, нет «телепорта» камеры). Сбрасывается на fit/split (реальная смена плана).
    prev_fill_end_cx: float | None = None
    for f0, f1 in shots:
        active = [t for t in tracks if t.f0 < f1 and t.f1 > f0]
        t0, t1 = f0 / fps, f1 / fps
        if mode_setting == "fit":
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
            prev_fill_end_cx = None
            continue
        if mode_setting != "fill" and (not active or _is_wide_shot(active, f0, f1, spread_min)):
            pair = _split_pair(active, f0, f1, spread_min) if split_enabled else None
            if pair is not None:
                ta, tb = pair
                regions.append(
                    TrackRegion(
                        t0=t0,
                        t1=t1,
                        mode="split",
                        points=_track_trajectory(ta, f0, f1, fps, smoothing),
                        points_b=_track_trajectory(tb, f0, f1, fps, smoothing),
                    )
                )
                prev_fill_end_cx = None
                continue
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
            prev_fill_end_cx = None
            continue
        target = _pick_target(active, speak_threshold)
        pts = (
            _track_trajectory(target, f0, f1, fps, smoothing, init_cx=prev_fill_end_cx)
            if target is not None
            else (
                TrackPoint(
                    t=t0, mode="fill", cx=0.5 if prev_fill_end_cx is None else prev_fill_end_cx
                ),
            )
        )
        regions.append(TrackRegion(t0=t0, t1=t1, mode="fill", points=pts))
        prev_fill_end_cx = pts[-1].cx
    return regions


def samples_in_shot(
    raw_samples: list[tuple[float, list[tuple[float, float]]]], t0: float, t1: float
) -> list[tuple[float, list[tuple[float, float]]]]:
    """Сэмплы лиц (t, faces), попадающие в полуинтервал плана [t0, t1). PURE."""
    return [(t, faces) for (t, faces) in raw_samples if t0 <= t < t1]


def decide_shot_mode(
    shot_samples: list[tuple[float, list[tuple[float, float]]]],
    *,
    crop_w_frac: float,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
) -> str:
    """Один режим ("fill"|"fit") на весь план по геометрии лиц. PURE.

    План = "fit", если доля кадров с широкой геометрией (classify_frame) >= wide_ratio.
    Нет сэмплов -> "fit". mode_setting "fit"/"fill" -- глобальный оверрайд.
    """
    if mode_setting in ("fill", "fit"):
        return mode_setting
    if not shot_samples:
        return "fit"
    fit_frames = sum(1 for _t, faces in shot_samples if classify_frame(faces, crop_w_frac) == "fit")
    return "fit" if fit_frames >= wide_ratio * len(shot_samples) else "fill"


def build_shot_trajectory(
    shot_samples: list[tuple[float, list[tuple[float, float]]]], smoothing: float
) -> tuple[TrackPoint, ...]:
    """Сглаженная cx-траектория ВНУТРИ одного fill-плана. PURE.

    smooth_centers сбрасывается на каждый план (стартует с 0.5) -- пан не "протекает"
    сквозь склейку. cx берётся у КРУПНЕЙШЕГО лица; нет лица -- держим последний.
    """
    cx_raws: list[float | None] = [
        max(faces, key=lambda f: f[1])[0] if faces else None for _t, faces in shot_samples
    ]
    init_cx = next((cx for cx in cx_raws if cx is not None), 0.5)
    cx_sm = smooth_centers(cx_raws, smoothing, init=init_cx)
    return tuple(
        TrackPoint(t=t, mode="fill", cx=cx)
        for (t, _faces), cx in zip(shot_samples, cx_sm, strict=False)
    )


def split_centers_for_shot(
    shot_samples: list[tuple[float, list[tuple[float, float]]]],
    crop_w_frac: float,
    coverage_min: float = 0.6,
) -> tuple[float, float] | None:
    """Пара центров для split-режима по сэмплам лиц плана (editor-путь). PURE.

    Кадр «split-пригоден»: РОВНО 2 лица, разнесённые сильнее ширины 9:16-кропа.
    Таких кадров ≥ coverage_min от всех сэмплов плана → (медиана левых, медиана
    правых). 3+ лиц / нестабильная пара / кластер → None (fit остаётся —
    «горизонтальный вид для других ситуаций», решение фаундера).
    """
    if not shot_samples:
        return None
    lefts: list[float] = []
    rights: list[float] = []
    for _t, faces in shot_samples:
        if len(faces) != 2:
            continue
        cx_a, cx_b = sorted(f[0] for f in faces)
        if cx_b - cx_a > crop_w_frac:
            lefts.append(cx_a)
            rights.append(cx_b)
    if len(lefts) < coverage_min * len(shot_samples):
        return None
    lefts.sort()
    rights.sort()
    return lefts[len(lefts) // 2], rights[len(rights) // 2]


def build_regions_from_shots(
    shots: list[tuple[float, float]],
    raw_samples: list[tuple[float, list[tuple[float, float]]]],
    crop_w_frac: float,
    smoothing: float,
    min_hold_sec: float,
    *,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
    split_enabled: bool = False,
) -> list[TrackRegion]:
    """Cut-aligned регионы: ОДИН режим на план, пан внутри fill-плана. PURE.

    Заменяет grid-based build_trajectory+build_regions. Границы режима = границы планов
    (= реальные склейки) -> смена режима только на склейке -> нет флеша. merge_short_regions
    в конце гасит планы короче min_hold (рапид-монтаж).
    split_enabled (v3): «широкий» план с устойчивой парой разнесённых лиц → split
    (верх/низ, как plan_regions в batch-пути) вместо fit; границы НЕ двигаются.
    """
    regions: list[TrackRegion] = []
    for t0, t1 in shots:
        seg = samples_in_shot(raw_samples, t0, t1)
        mode = decide_shot_mode(
            seg, crop_w_frac=crop_w_frac, mode_setting=mode_setting, wide_ratio=wide_ratio
        )
        if mode == "fill":
            pts = build_shot_trajectory(seg, smoothing)
            if not pts:
                pts = (TrackPoint(t=t0, mode="fill", cx=0.5),)
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fill", points=pts))
            continue
        pair = split_centers_for_shot(seg, crop_w_frac) if split_enabled else None
        if pair is not None:
            cx_a, cx_b = pair
            regions.append(
                TrackRegion(
                    t0=t0,
                    t1=t1,
                    mode="split",
                    points=(TrackPoint(t=t0, mode="split", cx=cx_a),),
                    points_b=(TrackPoint(t=t0, mode="split", cx=cx_b),),
                )
            )
        else:
            regions.append(TrackRegion(t0=t0, t1=t1, mode="fit", points=()))
    return merge_short_regions(regions, min_hold_sec)


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


def detect_scene_cuts(
    video: Path, start: float, end: float, fps: float, *, threshold: float = 27.0
) -> list[int]:
    """Frame-accurate склейки сегмента (PySceneDetect ContentDetector), КЛИП-относительные КАДРЫ.

    Сегмент режется ffmpeg в temp h264 (декодит AV1, старт=0 → seek-точность), затем
    PySceneDetect на нём. Возвращает номера кадров склеек (0-based от старта сегмента).
    Нет склеек → []. JobError при сбое (№8).
    """
    from scenedetect import ContentDetector, SceneManager, open_video  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        seg = Path(td) / "seg.mp4"
        cut_cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-to",
            str(end),
            "-i",
            str(video),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-r",
            str(fps),
            str(seg),
        ]
        try:
            proc = subprocess.run(cut_cmd, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-300:]
            raise JobError(_STAGE, f"ffmpeg seg код {proc.returncode}: {tail}")
        vid = None
        try:
            vid = open_video(str(seg))
            sm = SceneManager()
            sm.add_detector(ContentDetector(threshold=threshold))
            sm.detect_scenes(vid)
            scenes = sm.get_scene_list()
        except Exception as e:
            raise JobError(_STAGE, f"PySceneDetect сбой: {e}") from e
        finally:
            # Закрываем дескриптор ДО выхода из TemporaryDirectory (Windows держит лок на файл).
            # ОБЯЗАТЕЛЬНО в finally: при сбое detect_scenes незакрытый VideoCapture держит лок →
            # cleanup temp роняет PermissionError, маскируя исходную JobError.
            # VideoStreamCv2 не имеет release() — закрываем вложенный cv2.VideoCapture напрямую.
            if vid is not None and hasattr(vid, "capture") and hasattr(vid.capture, "release"):
                vid.capture.release()
    # get_scene_list даёт [(start, end), …]; склейка = start КАДР каждой сцены, кроме первой (0).
    return [s[0].get_frames() for s in scenes[1:]]


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
                        "points_b": [{"t": p.t, "mode": p.mode, "cx": p.cx} for p in r.points_b],
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
    fps: float,
    mode_setting: str = "auto",
    speaker_crop_scale: float = 0.55,
    face_fps: float = 25.0,
    smoothing: float = 0.15,
    min_hold_sec: float = 1.5,
    speak_threshold: float = 0.0,
    scene_threshold: float = 27.0,
    split_enabled: bool = False,
) -> tuple[list[TrackRegion], bool]:
    """Сегмент → (cut-aligned регионы, face_found). Единый путь (ASD по дефолту).

    PySceneDetect → кадры склеек → build_shots_frames → score_tracks_in_segment (MediaPipe+ASD)
    → plan_regions → merge_short_regions. Пишет reframe_<clip_id>.json ({regions:[...]}).
    """
    from app.pipeline.asd_reframe import score_tracks_in_segment  # noqa: PLC0415

    # Геометрия (склейки/шоты/регионы) И рендер работают в НАТИВНОЙ сетке fps источника.
    # origin = aligned_start (= round(start*fps)/fps) — ТА ЖЕ граница кадра, что в render_clip,
    # иначе t0 регионов уезжает на <1 кадр от filtergraph-часов → флеш. ASD остаётся @face_fps
    # (модель требует 25fps), дорожки потом ресемплим в нативную сетку (resample_track).
    aligned_start = round(start * fps) / fps
    duration = end - aligned_start
    total_frames = round(duration * fps)
    crop_w_frac = round(src_h * _ASPECT_W / _ASPECT_H) / src_w

    cuts = detect_scene_cuts(video, aligned_start, end, fps, threshold=scene_threshold)
    shots = build_shots_frames(cuts, total_frames)

    tracks_native = score_tracks_in_segment(
        video, src_w, src_h, aligned_start, end, face_fps, crop_scale=speaker_crop_scale
    )
    face_found = bool(tracks_native)
    tracks = [resample_track(t, face_fps, fps) for t in tracks_native]

    regions = merge_short_regions(
        plan_regions(
            shots,
            tracks,
            fps,
            crop_w_frac=crop_w_frac,
            smoothing=smoothing,
            speak_threshold=speak_threshold,
            mode_setting=mode_setting,
            split_enabled=split_enabled,
        ),
        min_hold_sec,
    )
    if not regions:
        regions = [TrackRegion(t0=0.0, t1=duration, mode="fit", points=())]

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_reframe_json(out_dir, clip_id, regions)
    return regions, face_found
