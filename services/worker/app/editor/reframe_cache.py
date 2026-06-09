"""Reframe-анализ по диапазону source (кэш) + сборка регионов на интервалы (спека §5).

analyze_source_range — I/O (ffmpeg+MediaPipe), кэшируется по диапазону. resolve_regions — PURE.
Граница интервала = forced-склейка (каждый интервал анализируется независимо).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
    """Ручной override → один регион на весь интервал."""
    if ov.mode == "fit":
        return [TrackRegion(t0=0.0, t1=dur, mode="fit", points=())]
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
        )
        if not regions:
            regions = [TrackRegion(t0=0.0, t1=dur, mode="fit", points=())]
        out.append(regions)
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
