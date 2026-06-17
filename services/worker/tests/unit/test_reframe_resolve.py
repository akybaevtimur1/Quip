import json

from app.editor.reframe_cache import (
    RawReframe,
    _region_from_dict,
    _region_to_dict,
    analyze_source_range,
    apply_overrides_to_regions,
    regions_to_clip_time,
    resolve_regions,
)
from app.models import CropOverride, SourceInterval
from app.pipeline.stage3_reframe import TrackPoint, TrackRegion


def test_regions_to_clip_time_offsets_by_interval_durations():
    # D2: per-interval (0-based) регионы → клип-время = конкатенация интервалов.
    iv = [
        SourceInterval(source_start=10.0, source_end=13.0),  # длительность 3.0
        SourceInterval(source_start=40.0, source_end=42.0),  # длительность 2.0
    ]
    pt = TrackPoint(t=1.0, mode="fill", cx=0.4)
    region_lists = [
        [TrackRegion(t0=0.0, t1=3.0, mode="fill", points=(pt,))],
        [TrackRegion(t0=0.0, t1=2.0, mode="fit", points=())],
    ]
    flat = regions_to_clip_time(region_lists, iv)
    assert [(r["t0"], r["t1"], r["mode"]) for r in flat] == [(0.0, 3.0, "fill"), (3.0, 5.0, "fit")]
    # точки второго интервала сдвинуты на 3.0 (длительность первого)
    assert flat[0]["points"][0]["t"] == 1.0  # первый интервал: без сдвига


def test_region_json_roundtrip():
    # сериализация регионов для кэша acc_*.json (resolve_regions_accurate): без потерь
    r = TrackRegion(
        t0=0.0, t1=3.3, mode="fill",
        points=(TrackPoint(t=0.0, mode="fill", cx=0.42), TrackPoint(t=1.0, mode="fill", cx=0.6)),
    )  # fmt: skip
    back = _region_from_dict(json.loads(json.dumps(_region_to_dict(r))))
    assert back == r


def test_region_json_roundtrip_split():
    r = TrackRegion(
        t0=0.0, t1=5.0, mode="split",
        points=(TrackPoint(t=0.0, mode="split", cx=0.3),),
        points_b=(TrackPoint(t=0.0, mode="split", cx=0.7),),
    )  # fmt: skip
    back = _region_from_dict(json.loads(json.dumps(_region_to_dict(r))))
    assert back == r


SRC_W, SRC_H = 1920, 1080  # crop_w = 607.5→608; crop_w_frac ≈ 0.316


def _faces_centered(n, fps=5.0):
    # n сэмплов: одно центрированное лицо (cx=0.5, ширина 0.2)
    return [(i / fps, [(0.5, 0.2)]) for i in range(n)]


def test_single_fill_interval():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=_faces_centered(10), cuts=[])]
    out = resolve_regions(
        intervals, raw, [], src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert len(out) == 1
    assert out[0][0].mode == "fill"
    assert out[0][0].points  # есть траектория


def test_no_faces_is_fit():
    intervals = [SourceInterval(source_start=0.0, source_end=2.0)]
    raw = [RawReframe(faces=[(i / 5.0, []) for i in range(10)], cuts=[])]
    out = resolve_regions(
        intervals, raw, [], src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert out[0][0].mode == "fit"


def test_override_fit_replaces_interval():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=_faces_centered(10), cuts=[])]  # авто было бы fill
    ov = [CropOverride(source_start=10.0, source_end=12.0, mode="fit")]
    out = resolve_regions(
        intervals, raw, ov, src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert len(out[0]) == 1 and out[0][0].mode == "fit"


def test_override_split_two_centers():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=_faces_centered(10), cuts=[])]
    ov = [CropOverride(source_start=10.0, source_end=12.0, mode="split", center=0.25, center_b=0.8)]
    out = resolve_regions(
        intervals, raw, ov, src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    reg = out[0][0]
    assert reg.mode == "split"
    assert reg.points[0].cx == 0.25
    assert reg.points_b[0].cx == 0.8


def test_override_split_default_centers():
    # center/center_b не заданы → явные дефолты 0.3/0.7
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=_faces_centered(10), cuts=[])]
    ov = [CropOverride(source_start=10.0, source_end=12.0, mode="split")]
    out = resolve_regions(
        intervals, raw, ov, src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    reg = out[0][0]
    assert reg.mode == "split"
    assert reg.points[0].cx == 0.3 and reg.points_b[0].cx == 0.7


def test_override_fill_center():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    raw = [RawReframe(faces=[(i / 5.0, []) for i in range(10)], cuts=[])]  # авто было бы fit
    ov = [CropOverride(source_start=10.0, source_end=12.0, mode="fill", center=0.7)]
    out = resolve_regions(
        intervals, raw, ov, src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert out[0][0].mode == "fill"
    assert out[0][0].points[0].cx == 0.7


def test_two_intervals_independent_region_lists():
    intervals = [
        SourceInterval(source_start=10.0, source_end=12.0),
        SourceInterval(source_start=30.0, source_end=32.0),
    ]
    raw = [
        RawReframe(faces=_faces_centered(10), cuts=[]),
        RawReframe(faces=_faces_centered(10), cuts=[]),
    ]
    out = resolve_regions(
        intervals, raw, [], src_w=SRC_W, src_h=SRC_H, smoothing=0.15, min_hold_sec=1.5
    )
    assert len(out) == 2  # отдельный список регионов на каждый интервал (граница = forced-cut)


def test_analyze_reads_cache_without_ffmpeg(tmp_path):
    # пред-записываем кэш → analyze должен прочитать его, НЕ зовя ffmpeg
    cache = tmp_path / "analysis"
    cache.mkdir()
    (cache / "reframe_10.00_12.00.json").write_text(
        json.dumps({"faces": [{"t": 0.0, "faces": [[0.5, 0.2]]}], "cuts": [1.0]}),
        encoding="utf-8",
    )
    raw = analyze_source_range(
        tmp_path / "nonexistent.mp4", 10.0, 12.0, cache_dir=cache, fps=5.0, cut_threshold=0.4
    )
    assert raw.cuts == [1.0]
    assert raw.faces == [(0.0, [(0.5, 0.2)])]


# ── apply_overrides_to_regions — "recolor, don't re-cut" (bug #5) ────────────────
# Per-shot force-framing must recolor ONLY the covered shot, keeping every region's
# t0/t1 (cut-frame boundaries) untouched (REFRAME_FPS_GRID_INVARIANT). Coverage rule:
# region midpoint mid = iv.source_start + (t0+t1)/2; LAST override with
# ov.source_start <= mid < ov.source_end wins.


def _three_shots():
    # interval-relative regions: shot#1 [0,2) fill, shot#2 [2,4) fill, shot#3 [4,6) fit
    return [
        TrackRegion(t0=0.0, t1=2.0, mode="fill", points=(TrackPoint(t=0.0, mode="fill", cx=0.4),)),
        TrackRegion(t0=2.0, t1=4.0, mode="fill", points=(TrackPoint(t=2.0, mode="fill", cx=0.6),)),
        TrackRegion(t0=4.0, t1=6.0, mode="fit", points=()),
    ]


def test_apply_overrides_recolors_only_covered_shot():
    # override covers ONLY shot#2 (abs source 12..14; mid of shot#2 = 10+3 = 13)
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    ov = [CropOverride(source_start=12.0, source_end=14.0, mode="fit")]
    out = apply_overrides_to_regions(regions, ov, iv)
    assert len(out) == 3  # same length — no new boundaries
    # shot#1 unchanged (same boundaries + original mode/points)
    assert (out[0].t0, out[0].t1, out[0].mode) == (0.0, 2.0, "fill")
    assert out[0].points == regions[0].points
    # shot#2 recolored to fit, boundaries kept
    assert (out[1].t0, out[1].t1, out[1].mode) == (2.0, 4.0, "fit")
    assert out[1].points == ()
    # shot#3 unchanged
    assert (out[2].t0, out[2].t1, out[2].mode) == (4.0, 6.0, "fit")
    assert out[2].points == regions[2].points


def test_apply_overrides_fill_center():
    # override mode fill + center=0.7 over shot#3 (abs mid = 10+5 = 15)
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    ov = [CropOverride(source_start=14.0, source_end=16.0, mode="fill", center=0.7)]
    out = apply_overrides_to_regions(regions, ov, iv)
    assert (out[2].t0, out[2].t1, out[2].mode) == (4.0, 6.0, "fill")
    assert out[2].points[0].cx == 0.7
    assert out[2].points[0].t == 4.0  # point anchored at region t0
    # shots #1/#2 untouched
    assert out[0] == regions[0] and out[1] == regions[1]


def test_apply_overrides_split_clamps_centers():
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    ov = [CropOverride(source_start=12.0, source_end=14.0, mode="split", center=0.25, center_b=0.8)]
    out = apply_overrides_to_regions(regions, ov, iv)
    assert out[1].mode == "split"
    assert out[1].points[0].cx == 0.25
    assert out[1].points_b[0].cx == 0.8
    assert (out[1].t0, out[1].t1) == (2.0, 4.0)


def test_apply_overrides_no_overrides_unchanged():
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    out = apply_overrides_to_regions(regions, [], iv)
    assert out == regions


def test_apply_overrides_last_wins():
    # two overlapping overrides over shot#2 → LAST one wins
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    ov = [
        CropOverride(source_start=11.0, source_end=15.0, mode="fit"),
        CropOverride(source_start=12.0, source_end=14.0, mode="fill", center=0.9),
    ]
    out = apply_overrides_to_regions(regions, ov, iv)
    # shot#2 mid=13 covered by BOTH → last (fill 0.9) wins
    assert out[1].mode == "fill" and out[1].points[0].cx == 0.9
    # shot#1 mid=11 → fit (first only); shot#3 mid=15 → unchanged (half-open excludes it)
    assert out[0].mode == "fit"
    assert out[2] == regions[2]


def test_apply_overrides_unknown_mode_unchanged():
    iv = SourceInterval(source_start=10.0, source_end=16.0)
    regions = _three_shots()
    ov = [CropOverride(source_start=12.0, source_end=14.0, mode="bogus")]
    out = apply_overrides_to_regions(regions, ov, iv)
    assert out[1] == regions[1]  # unknown mode → region left unchanged
