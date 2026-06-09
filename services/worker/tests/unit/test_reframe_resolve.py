import json

from app.editor.reframe_cache import RawReframe, analyze_source_range, resolve_regions
from app.models import CropOverride, SourceInterval

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
