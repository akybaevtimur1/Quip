"""Тесты pure-сборки рендера Stage 5 (V2: TrackRegion + Engine A/B) — тест-первым.

Engine A: ffmpeg piecewise-const crop expr (build_fill_crop_expr) + filter_complex
(build_smooth_filter) — split→trim→crop_expr/fit→concat→subtitles. Аудио непрерывным.
Engine B: cv2 per-frame pipe — тестируется по интерфейсу (unit-тесты на чистую логику).
build_single_pass_cmd (без изменений) — сохранён.
"""

import pytest

from app.errors import JobError
from app.pipeline.stage3_reframe import TrackPoint, TrackRegion
from app.pipeline.stage5_render import (
    _chain_video_segs,
    _interp_cx,
    build_fill_crop_expr,
    build_single_pass_cmd,
    build_smooth_filter,
)

# ─────────────────────── helpers ───────────────────────


def _fill_region(t0: float, t1: float, cx_list: list[float]) -> TrackRegion:
    pts = tuple(TrackPoint(t=t0 + i * 0.2, mode="fill", cx=cx) for i, cx in enumerate(cx_list))
    return TrackRegion(t0=t0, t1=t1, mode="fill", points=pts)


def _fit_region(t0: float, t1: float) -> TrackRegion:
    return TrackRegion(t0=t0, t1=t1, mode="fit", points=())


def _split_region(t0: float, t1: float, cx_a: float, cx_b: float) -> TrackRegion:
    return TrackRegion(
        t0=t0,
        t1=t1,
        mode="split",
        points=(TrackPoint(t=t0, mode="split", cx=cx_a),),
        points_b=(TrackPoint(t=t0, mode="split", cx=cx_b),),
    )


# ─────────────────────── TestBuildFillCropExpr ───────────────────────


class TestBuildFillCropExpr:
    """Piecewise-constant if() expression для ffmpeg crop X (Engine A)."""

    def test_single_point_returns_static(self) -> None:
        # одна точка → просто x-значение (нет if())
        pt = TrackPoint(t=5.0, mode="fill", cx=0.5)
        expr = build_fill_crop_expr((pt,), t0_offset=5.0, src_w=1920, src_h=1080)
        assert "if" not in expr
        assert expr.isdigit()

    def test_two_points_builds_if(self) -> None:
        pts = (
            TrackPoint(t=0.0, mode="fill", cx=0.3),
            TrackPoint(t=0.2, mode="fill", cx=0.7),
        )
        expr = build_fill_crop_expr(pts, t0_offset=0.0, src_w=1920, src_h=1080)
        assert "if(lt(t" in expr
        # запятые экранированы \,
        assert "\\," in expr

    def test_t_offset_subtracted(self) -> None:
        # точки при region.t0=5.0 → t_rel = point.t - 5.0
        pts = (
            TrackPoint(t=5.0, mode="fill", cx=0.5),
            TrackPoint(t=5.2, mode="fill", cx=0.6),
        )
        expr = build_fill_crop_expr(pts, t0_offset=5.0, src_w=1920, src_h=1080)
        assert "0.200" in expr  # t_rel = 5.2 - 5.0 = 0.2

    def test_empty_raises(self) -> None:
        with pytest.raises(JobError):
            build_fill_crop_expr((), t0_offset=0.0, src_w=1920, src_h=1080)

    def test_cx_none_defaults_to_half(self) -> None:
        # cx=None → 0.5 (fallback для fit-точки попавшей в fill-регион)
        pt = TrackPoint(t=0.0, mode="fill", cx=None)
        expr = build_fill_crop_expr((pt,), t0_offset=0.0, src_w=1920, src_h=1080)
        # center=0.5 → x=656 для 1920x1080
        assert expr == "656"


# ─────────────────────── TestBuildSmoothFilter ───────────────────────


class TestBuildSmoothFilter:
    """filter_complex Engine A: split→trim+crop_expr/fit→concat→subtitles."""

    def test_single_fill_region(self) -> None:
        region = _fill_region(0.0, 5.0, [0.5, 0.52])
        fc = build_smooth_filter([region], 1920, 1080, 24.0, "cap.ass")
        assert "[0:v]setpts=PTS-STARTPTS,split=1[a0];" in fc
        assert "trim=start_frame=0:end_frame=120" in fc
        assert "crop=" in fc
        assert "scale=1080:1920:flags=lanczos" in fc
        # n=1: no concat/xfade chain, go direct to subtitles burn
        assert "[s0]subtitles=cap.ass[outv]" in fc

    def test_single_fit_region(self) -> None:
        region = _fit_region(0.0, 5.0)
        fc = build_smooth_filter([region], 1920, 1080, 24.0, "c.ass")
        assert "gblur" in fc
        assert "overlay=(W-w)/2:(H-h)/2" in fc

    def test_trim_is_frame_exact(self) -> None:
        # t0=2.12, fps=24 → start_frame=round(50.88)=51
        regions = [_fill_region(0.0, 2.12, [0.3]), _fill_region(2.12, 5.0, [0.7])]
        fc = build_smooth_filter(regions, 1920, 1080, 24.0, "c.ass")
        assert "trim=start_frame=0:end_frame=51" in fc
        assert "trim=start_frame=51:end_frame=120" in fc
        # same-mode (fill→fill): pairwise concat, no xfade
        assert "concat=n=2:v=1" in fc
        assert "xfade" not in fc

    def test_setsar_on_each_region(self) -> None:
        # concat требует одинаковый SAR (fill и fit дают разный) → setsar=1 на каждом
        regions = [_fill_region(0.0, 2.0, [0.3]), _fit_region(2.0, 5.0)]
        fc = build_smooth_filter(regions, 1920, 1080, 24.0, "c.ass")
        assert fc.count("setsar=1") == 2

    def test_fit_labels_unique_per_region(self) -> None:
        regions = [_fit_region(0.0, 2.0), _fit_region(2.0, 5.0)]
        fc = build_smooth_filter(regions, 1920, 1080, 24.0, "c.ass")
        assert "[bg0]" in fc and "[bg1]" in fc

    def test_fill_without_points_raises(self) -> None:
        bad = TrackRegion(t0=0.0, t1=5.0, mode="fill", points=())
        with pytest.raises(JobError):
            build_smooth_filter([bad], 1920, 1080, 24.0, "c.ass")

    def test_empty_raises(self) -> None:
        with pytest.raises(JobError):
            build_smooth_filter([], 1920, 1080, 24.0, "c.ass")

    def test_fill_to_fit_is_hard_cut(self) -> None:
        regions = [_fill_region(0.0, 3.0, [0.5]), _fit_region(3.0, 7.0)]
        fc = build_smooth_filter(regions, 1920, 1080, 30.0, "c.ass")
        assert "xfade" not in fc
        assert "concat=n=2:v=1:a=0" in fc

    def test_fit_to_fill_is_hard_cut(self) -> None:
        regions = [_fit_region(0.0, 3.0), _fill_region(3.0, 7.0, [0.5])]
        fc = build_smooth_filter(regions, 1920, 1080, 30.0, "c.ass")
        assert "xfade" not in fc
        assert "concat=n=2:v=1:a=0" in fc

    def test_split_region_has_vstack_two_crops(self) -> None:
        region = _split_region(0.0, 5.0, 0.2, 0.8)
        fc = build_smooth_filter([region], 1920, 1080, 25.0, None)
        assert "vstack=inputs=2" in fc
        assert fc.count("crop=") >= 2
        assert "scale=1080:960" in fc  # каждая половина 1080×960
        assert "setsar=1" in fc

    def test_split_labels_unique_two_regions(self) -> None:
        # 2 split-региона → лейблы половин не коллидируют (урок R1c про [bg][fg])
        regions = [_split_region(0.0, 3.0, 0.2, 0.8), _split_region(3.0, 6.0, 0.3, 0.7)]
        fc = build_smooth_filter(regions, 1920, 1080, 25.0, "c.ass")
        assert "[pa0]" in fc and "[pa1]" in fc
        assert "[pb0]" in fc and "[pb1]" in fc

    def test_split_without_points_b_raises(self) -> None:
        bad = TrackRegion(
            t0=0.0, t1=5.0, mode="split", points=(TrackPoint(t=0.0, mode="split", cx=0.5),)
        )
        with pytest.raises(JobError):
            build_smooth_filter([bad], 1920, 1080, 25.0, None)

    def test_split_too_narrow_source_raises(self) -> None:
        # ширина кропа половины = src_h*1.125; для квадратного источника 1000×1000 → 1125 > 1000
        with pytest.raises(JobError):
            build_smooth_filter([_split_region(0.0, 5.0, 0.2, 0.8)], 1000, 1000, 25.0, None)

    def test_fill_fill_fit_fill_all_concat(self) -> None:
        # все переходы — concat (жёсткий cut), нет xfade
        regions = [
            _fill_region(0.0, 2.0, [0.5]),
            _fill_region(2.0, 4.0, [0.5]),
            _fit_region(4.0, 7.0),
            _fill_region(7.0, 10.0, [0.5]),
        ]
        fc = build_smooth_filter(regions, 1920, 1080, 30.0, "c.ass")
        assert "xfade" not in fc
        assert fc.count("concat=n=2:v=1:a=0") >= 1


# ─────────────────────── TestChainVideoSegs ───────────────────────


class TestChainVideoSegs:
    """_chain_video_segs: всегда попарный concat (жёсткий cut на границе шота)."""

    def test_two_segments_concat(self) -> None:
        parts = _chain_video_segs(["s0", "s1"], "cv")
        assert parts == ["[s0][s1]concat=n=2:v=1:a=0[cv];"]

    def test_three_segments_chain(self) -> None:
        parts = _chain_video_segs(["s0", "s1", "s2"], "cv")
        assert parts == [
            "[s0][s1]concat=n=2:v=1:a=0[ch1];",
            "[ch1][s2]concat=n=2:v=1:a=0[cv];",
        ]

    def test_never_uses_xfade(self) -> None:
        parts = _chain_video_segs(["s0", "s1", "s2"], "cv")
        assert all("xfade" not in p for p in parts)


class TestBuildSmoothFilterHardCut:
    def test_fill_to_fit_is_hard_cut(self) -> None:
        regions = [
            TrackRegion(0.0, 2.0, "fill", (TrackPoint(0.0, "fill", 0.5),)),
            TrackRegion(2.0, 4.0, "fit", ()),
        ]
        fc = build_smooth_filter(regions, 1920, 1080, 30.0, "c.ass")
        assert "xfade" not in fc
        assert "concat=n=2" in fc


# ─────────────────────── TestInterpCx ───────────────────────


class TestInterpCx:
    """Engine B: линейная интерполяция cx между TrackPoint."""

    def test_empty_points_returns_half(self) -> None:
        region = _fit_region(0.0, 5.0)
        assert _interp_cx(region, 2.5) == 0.5

    def test_single_point_returns_its_cx(self) -> None:
        region = _fill_region(0.0, 5.0, [0.7])
        assert _interp_cx(region, 2.5) == pytest.approx(0.7)

    def test_interpolates_between_two_points(self) -> None:
        region = _fill_region(0.0, 5.0, [0.4, 0.8])  # t=0.0 cx=0.4, t=0.2 cx=0.8
        # t=0.1 → midpoint → cx = 0.4 + 0.5*(0.8-0.4) = 0.6
        assert _interp_cx(region, 0.1) == pytest.approx(0.6)

    def test_before_first_point_returns_first(self) -> None:
        region = _fill_region(2.0, 5.0, [0.6])  # t=2.0 cx=0.6
        assert _interp_cx(region, 1.5) == pytest.approx(0.6)

    def test_after_last_point_returns_last(self) -> None:
        region = _fill_region(0.0, 5.0, [0.4, 0.8])  # last cx=0.8
        assert _interp_cx(region, 10.0) == pytest.approx(0.8)


# ─────────────────────── TestBuildSinglePassCmd ───────────────────────


class TestBuildSinglePassCmd:
    """ffmpeg: -ss ДО -i, filter_complex, видео [outv] + аудио непрерывным 0:a."""

    def test_ss_before_input(self) -> None:
        cmd = build_single_pass_cmd("source.mp4", 24.75, 31.57, "FC", "clips/clip_01.mp4")
        assert cmd.index("-ss") < cmd.index("-i")

    def test_filter_and_maps(self) -> None:
        cmd = build_single_pass_cmd("source.mp4", 24.75, 31.57, "FC", "out.mp4")
        s = " ".join(cmd)
        assert "-filter_complex FC" in s
        assert "-map [outv]" in s
        assert "-map 0:a" in s

    def test_codecs_and_output(self) -> None:
        cmd = build_single_pass_cmd("source.mp4", 24.75, 31.57, "FC", "clips/clip_01.mp4")
        s = " ".join(cmd)
        assert "libx264" in s
        assert "-crf 20" in s
        assert "aac" in s
        assert "+faststart" in s
        assert cmd[-1] == "clips/clip_01.mp4"
