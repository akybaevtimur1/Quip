"""Reframe-анализ по диапазону source (кэш) + сборка регионов на интервалы (спека §5).

analyze_source_range — I/O (ffmpeg+MediaPipe), кэшируется по диапазону. resolve_regions — PURE.
Граница интервала = forced-склейка (каждый интервал анализируется независимо).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import CropOverride, SourceInterval
from app.pipeline.stage3_reframe import (
    TrackPoint,
    TrackRegion,
    build_regions_from_shots,
    build_shots,
    detect_cuts,
    sample_faces_continuous,
)

_ASPECT_W, _ASPECT_H = 9, 16

FaceSamples = list[tuple[float, list[tuple[float, float]]]]


@dataclass(frozen=True)
class RawReframe:
    """Сырой reframe-анализ диапазона (interval-relative, 0-based): лица + склейки."""

    faces: FaceSamples  # [(t, [(cx, w_frac), …]), …]
    cuts: list[float]  # тайминги склеек


def _override_for(overrides: list[CropOverride], iv: SourceInterval) -> CropOverride | None:
    """Последний override, пересекающий интервал (MVP: override применяется per-интервал)."""
    found: CropOverride | None = None
    for ov in overrides:
        if ov.source_start < iv.source_end and ov.source_end > iv.source_start:
            found = ov
    return found


def _manual_region(ov: CropOverride, dur: float) -> list[TrackRegion]:
    """Ручной override → один регион на весь интервал (новых границ нет — инвариант цел).

    split: два статичных центра (center/center_b; не заданы → явные дефолты 0.3/0.7).
    """
    if ov.mode == "fit":
        return [TrackRegion(t0=0.0, t1=dur, mode="fit", points=())]
    if ov.mode == "split":
        cx_a = min(1.0, max(0.0, ov.center if ov.center is not None else 0.3))
        cx_b = min(1.0, max(0.0, ov.center_b if ov.center_b is not None else 0.7))
        return [
            TrackRegion(
                t0=0.0,
                t1=dur,
                mode="split",
                points=(TrackPoint(t=0.0, mode="split", cx=cx_a),),
                points_b=(TrackPoint(t=0.0, mode="split", cx=cx_b),),
            )
        ]
    cx = ov.center if ov.center is not None else 0.5
    pt = TrackPoint(t=0.0, mode="fill", cx=cx)
    return [TrackRegion(t0=0.0, t1=dur, mode="fill", points=(pt,))]


def resolve_regions(
    intervals: list[SourceInterval],
    raw_by_interval: list[RawReframe],
    overrides: list[CropOverride],
    *,
    src_w: int,
    src_h: int,
    smoothing: float,
    min_hold_sec: float,
    mode_setting: str = "auto",
    wide_ratio: float = 0.5,
    split_enabled: bool = False,
) -> list[list[TrackRegion]]:
    """Регионы на каждый интервал (interval-relative). PURE.

    Override, пересекающий интервал, заменяет авто-регионы (per-интервал). Иначе —
    cut-aligned build_shots + build_regions_from_shots по сырому анализу интервала.
    """
    crop_w_frac = round(src_h * _ASPECT_W / _ASPECT_H) / src_w
    out: list[list[TrackRegion]] = []
    for iv, raw in zip(intervals, raw_by_interval, strict=True):
        dur = round(iv.source_end - iv.source_start, 3)
        ov = _override_for(overrides, iv)
        if ov is not None:
            out.append(_manual_region(ov, dur))
            continue
        shots = build_shots(raw.cuts, dur)
        regions = build_regions_from_shots(
            shots,
            raw.faces,
            crop_w_frac,
            smoothing,
            min_hold_sec,
            mode_setting=mode_setting,
            wide_ratio=wide_ratio,
            split_enabled=split_enabled,
        )
        if not regions:
            regions = [TrackRegion(t0=0.0, t1=dur, mode="fit", points=())]
        out.append(regions)
    return out


def _region_to_dict(r: TrackRegion) -> dict[str, Any]:
    def pts(ps: tuple[TrackPoint, ...]) -> list[dict[str, Any]]:
        return [{"t": p.t, "mode": p.mode, "cx": p.cx} for p in ps]

    return {
        "t0": r.t0,
        "t1": r.t1,
        "mode": r.mode,
        "points": pts(r.points),
        "points_b": pts(r.points_b),
    }


def _region_from_dict(d: dict[str, Any]) -> TrackRegion:
    def pts(arr: list[dict[str, Any]]) -> tuple[TrackPoint, ...]:
        return tuple(TrackPoint(t=p["t"], mode=p["mode"], cx=p["cx"]) for p in arr)

    return TrackRegion(
        t0=d["t0"], t1=d["t1"], mode=d["mode"],
        points=pts(d["points"]), points_b=pts(d.get("points_b", [])),
    )  # fmt: skip


def resolve_regions_accurate(
    video: Path,
    intervals: list[SourceInterval],
    overrides: list[CropOverride],
    *,
    src_w: int,
    src_h: int,
    fps: float,
    clip_id: str,
    out_dir: Path,
    cache_dir: Path,
    mode_setting: str = "auto",
    speaker_crop_scale: float = 0.55,
    face_fps: float = 25.0,
    smoothing: float = 0.15,
    min_hold_sec: float = 1.5,
    speak_threshold: float = 0.0,
    scene_threshold: float = 27.0,
    split_enabled: bool = False,
) -> list[list[TrackRegion]]:
    """Регионы на интервалы ЕДИНЫМ frame-accurate путём (как batch): per-interval
    `reframe_segment` (PySceneDetect frame-accurate + ASD-говорящий + held-crop по шотам).

    Это убирает рывки/флеши editor-пути (старый detect_cuts в СЕКУНДАХ + 5fps без ASD
    давал границы мимо реального кадра-склейки на ≠25fps → флеш; EMA-пан → рывки).
    Кадровая сетка цела: reframe_segment строит t0=cut_frame/fps в НАТИВНОМ fps, ровно
    как режет render (REFRAME_FPS_GRID_INVARIANT). Кэш по диапазону интервала → правки
    субтитров не перезапускают тяжёлый ASD. Override (таб «Кадр») заменяет авто-регионы.
    """
    from app.pipeline.stage3_reframe import reframe_segment  # noqa: PLC0415 (torch ленивый)

    cache_dir.mkdir(parents=True, exist_ok=True)
    out: list[list[TrackRegion]] = []
    for i, iv in enumerate(intervals):
        dur = round(iv.source_end - iv.source_start, 3)
        ov = _override_for(overrides, iv)
        if ov is not None:
            out.append(_manual_region(ov, dur))
            continue
        cache = cache_dir / f"acc_{iv.source_start:.2f}_{iv.source_end:.2f}.json"
        if cache.exists():
            out.append([_region_from_dict(d) for d in json.loads(cache.read_text("utf-8"))])
            continue
        cid = clip_id if i == 0 else f"{clip_id}_iv{i}"
        regions, _ = reframe_segment(
            video, src_w, src_h, iv.source_start, iv.source_end,
            clip_id=cid, out_dir=out_dir, fps=fps, mode_setting=mode_setting,
            speaker_crop_scale=speaker_crop_scale, face_fps=face_fps, smoothing=smoothing,
            min_hold_sec=min_hold_sec, speak_threshold=speak_threshold,
            scene_threshold=scene_threshold, split_enabled=split_enabled,
        )  # fmt: skip
        cache.write_text(
            json.dumps([_region_to_dict(r) for r in regions], ensure_ascii=False), "utf-8"
        )
        out.append(regions)
    return out


def regions_to_clip_time(
    region_lists: list[list[TrackRegion]], intervals: list[SourceInterval]
) -> list[dict[str, Any]]:
    """Per-interval (0-based) регионы → ПЛОСКИЙ список регионов в КЛИП-времени. PURE.

    Клип-время = конкатенация интервалов (как режет/склеивает render_timeline): регион i-го
    интервала сдвигается на сумму длительностей предыдущих интервалов. Формат совпадает с
    reframe_<clip>.json (`{t0,t1,mode,points,points_b}`) → фронт-превью читает один и тот же
    контракт и для batch-плана, и для этого эндпоинта (D2: один источник плана = что у рендера).
    """
    out: list[dict[str, Any]] = []
    offset = 0.0
    for iv, regions in zip(intervals, region_lists, strict=True):
        for r in regions:
            d = _region_to_dict(r)
            d["t0"] = round(r.t0 + offset, 3)
            d["t1"] = round(r.t1 + offset, 3)
            d["points"] = [{**p, "t": round(p["t"] + offset, 3)} for p in d["points"]]
            d["points_b"] = [{**p, "t": round(p["t"] + offset, 3)} for p in d["points_b"]]
            out.append(d)
        offset += round(iv.source_end - iv.source_start, 3)
    return out


def _cache_path(cache_dir: Path, src_start: float, src_end: float) -> Path:
    return cache_dir / f"reframe_{src_start:.2f}_{src_end:.2f}.json"


def analyze_source_range(
    video: Path,
    src_start: float,
    src_end: float,
    *,
    cache_dir: Path,
    fps: float = 5.0,
    cut_threshold: float = 0.4,
) -> RawReframe:
    """Сырой reframe-анализ диапазона [src_start, src_end]. Кэш по диапазону.

    Кэш-хит → читаем JSON (НЕ зовём ffmpeg).
    Промах → sample_faces_continuous + detect_cuts → пишем кэш.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, src_start, src_end)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        faces: FaceSamples = [(f["t"], [(c[0], c[1]) for c in f["faces"]]) for f in data["faces"]]
        return RawReframe(faces=faces, cuts=list(data["cuts"]))
    faces = sample_faces_continuous(video, src_start, src_end, fps=fps)
    cuts = detect_cuts(video, src_start, src_end, threshold=cut_threshold)
    face_data = [{"t": t, "faces": [[cx, w_frac] for cx, w_frac in fs]} for t, fs in faces]
    path.write_text(
        json.dumps({"faces": face_data, "cuts": cuts}, ensure_ascii=False),
        encoding="utf-8",
    )
    return RawReframe(faces=faces, cuts=cuts)
