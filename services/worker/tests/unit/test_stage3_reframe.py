"""Тесты pure-математики Stage 3 (reframe 9:16) — баг-опасное место, тест-первым.

Crop-окно 9:16 + клип в границы кадра; агрегация центров лиц (медиана, устойчива
к выбросам на мультиспикере). I/O (ffmpeg+MediaPipe) тестируем глазами на сэмпле.
"""

import pytest

from app.errors import JobError
from app.pipeline.stage3_reframe import (
    aggregate_center,
    build_shots,
    compute_crop_window,
    decide_reframe_mode,
    shot_centers,
)


class TestComputeCropWindow:
    def test_1080p_center(self) -> None:
        c = compute_crop_window(1920, 1080, 0.5, t=0.0)
        assert c.h == 1080
        assert c.w == 608  # round(1080*9/16) = round(607.5)
        assert c.y == 0
        # центр: x = round(0.5*1920 - 304) = 656, в пределах [0, 1920-608]
        assert c.x == 656
        assert 0 <= c.x and c.x + c.w <= 1920

    def test_aspect_is_9_16_within_1px(self) -> None:
        c = compute_crop_window(1920, 1080, 0.5, t=0.0)
        assert abs(c.w * 16 - c.h * 9) <= 16  # ≈ 9:16 с точностью до пикселя

    def test_clamps_left_edge(self) -> None:
        c = compute_crop_window(1920, 1080, 0.0, t=0.0)
        assert c.x == 0

    def test_clamps_right_edge(self) -> None:
        c = compute_crop_window(1920, 1080, 1.0, t=0.0)
        assert c.x == 1920 - c.w
        assert c.x + c.w <= 1920

    def test_center_fraction_clamped(self) -> None:
        # выход за [0,1] не должен ломать кламп окна
        c = compute_crop_window(1920, 1080, 1.5, t=0.0)
        assert c.x + c.w <= 1920

    def test_source_too_narrow_raises(self) -> None:
        with pytest.raises(JobError):
            compute_crop_window(500, 1080, 0.5, t=0.0)  # 9:16 от 1080 = 608 > 500

    def test_bad_dims_raise(self) -> None:
        with pytest.raises(JobError):
            compute_crop_window(0, 1080, 0.5, t=0.0)


class TestAggregateCenter:
    def test_median_odd(self) -> None:
        assert aggregate_center([0.4, 0.6, 0.5]) == 0.5

    def test_median_even(self) -> None:
        assert aggregate_center([0.4, 0.6]) == 0.5

    def test_resists_outlier(self) -> None:
        # одиночный шальной детект (чужое лицо) не должен утащить центр
        assert aggregate_center([0.5, 0.5, 0.5, 0.95]) == 0.5

    def test_single(self) -> None:
        assert aggregate_center([0.7]) == 0.7

    def test_empty_raises(self) -> None:
        with pytest.raises(JobError):
            aggregate_center([])


class TestDecideReframeMode:
    def test_auto_face_fills(self) -> None:
        assert decide_reframe_mode("auto", True) == "fill"

    def test_auto_no_face_fits(self) -> None:
        assert decide_reframe_mode("auto", False) == "fit"

    def test_forced_fill_ignores_face(self) -> None:
        assert decide_reframe_mode("fill", False) == "fill"

    def test_forced_fit_ignores_face(self) -> None:
        assert decide_reframe_mode("fit", True) == "fit"


class TestBuildShots:
    """Интервалы планов из таймингов склеек источника (cut-aware reframe)."""

    def test_no_cuts_one_shot(self) -> None:
        assert build_shots([], 20.0) == [(0.0, 20.0)]

    def test_splits_at_cuts(self) -> None:
        assert build_shots([5.0, 10.0], 20.0) == [(0.0, 5.0), (5.0, 10.0), (10.0, 20.0)]

    def test_ignores_out_of_range_and_sorts(self) -> None:
        # склейки на 0 и в конце игнорируем; неотсортированные — сортируем
        assert build_shots([10.0, 0.0, 20.0, 5.0], 20.0) == [
            (0.0, 5.0),
            (5.0, 10.0),
            (10.0, 20.0),
        ]

    def test_dedups_cuts(self) -> None:
        assert build_shots([5.0, 5.0, 10.0], 20.0) == [(0.0, 5.0), (5.0, 10.0), (10.0, 20.0)]

    def test_zero_duration_empty(self) -> None:
        assert build_shots([], 0.0) == []


class TestShotCenters:
    """Один устойчивый центр на план (медиана лиц); план без лица → держим предыдущий."""

    def test_median_per_shot(self) -> None:
        samples = [(0.1, 0.3), (0.6, 0.5), (1.0, 0.4), (5.5, 0.8)]
        out = shot_centers(samples, [(0.0, 5.0), (5.0, 10.0)])
        assert out == [(0.0, 0.4), (5.0, 0.8)]  # медиана(0.3,0.4,0.5)=0.4; один сэмпл=0.8

    def test_empty_shot_carries_previous(self) -> None:
        # план без лиц не прыгает в центр, а держит кадр прошлого плана
        samples = [(1.0, 0.6)]
        out = shot_centers(samples, [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)])
        assert out == [(0.0, 0.6), (5.0, 0.6), (10.0, 0.6)]

    def test_first_shot_empty_uses_default(self) -> None:
        samples = [(6.0, 0.7)]
        out = shot_centers(samples, [(0.0, 5.0), (5.0, 10.0)], default=0.5)
        assert out == [(0.0, 0.5), (5.0, 0.7)]
