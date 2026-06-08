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
        assert "concat=n=1:v=1[cv];[cv]subtitles=cap.ass[outv]" in fc

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
        assert "concat=n=2:v=1" in fc

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
