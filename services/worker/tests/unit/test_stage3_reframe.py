"""Тесты pure-математики Stage 3 (reframe 9:16) — баг-опасное место, тест-первым.

Crop-окно 9:16 + клип в границы кадра; агрегация центров лиц (медиана, устойчива
к выбросам на мультиспикере). I/O (ffmpeg+MediaPipe) тестируем глазами на сэмпле.
"""

import pytest

from app.errors import JobError
from app.pipeline.stage3_reframe import (
    aggregate_center,
    compute_crop_window,
    decide_reframe_mode,
    smooth_track,
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


class TestSmoothTrack:
    """Динамический трек: сглаживание дрожи + dead-zone (статика → 1 кейфрейм) + кап."""

    def test_empty_returns_empty(self) -> None:
        assert smooth_track([]) == []

    def test_single_sample_passthrough(self) -> None:
        assert smooth_track([(0.0, 0.7)]) == [(0.0, 0.7)]

    def test_static_collapses_to_one_keyframe(self) -> None:
        # лицо неподвижно (один спикер) → ОДНО окно, никакого дрожания на рендере
        samples = [(i * 0.5, 0.5) for i in range(20)]
        out = smooth_track(samples, dead_zone=0.04)
        assert len(out) == 1
        assert out[0][1] == 0.5

    def test_jitter_below_dead_zone_collapses(self) -> None:
        # мелкая дрожь детектора (±0.02 < dead_zone) после сглаживания → 1 кейфрейм
        samples = [(i * 0.5, 0.5 + (0.02 if i % 2 else -0.02)) for i in range(20)]
        out = smooth_track(samples, win=5, dead_zone=0.05)
        assert len(out) == 1
        assert abs(out[0][1] - 0.5) < 0.03

    def test_tracks_real_movement(self) -> None:
        # лицо реально едет 0.2 → 0.8: трек монотонно растёт, концы близко к краям
        samples = [(i * 0.5, 0.2 + 0.6 * i / 19) for i in range(20)]
        out = smooth_track(samples, win=5, dead_zone=0.04, max_keyframes=12)
        assert len(out) > 1
        centers = [c for _, c in out]
        assert centers == sorted(centers)  # монотонно вверх
        assert out[0][1] < 0.4  # начинает слева
        assert out[-1][1] > 0.6  # заканчивает справа

    def test_caps_keyframes(self) -> None:
        # пилообразное движение даёт много кандидатов → не больше max_keyframes
        samples = [(i * 0.5, 0.2 + 0.6 * (i % 2)) for i in range(60)]
        out = smooth_track(samples, win=3, dead_zone=0.04, max_keyframes=8)
        assert len(out) <= 8

    def test_preserves_endpoints_time(self) -> None:
        samples = [(i * 0.5, 0.2 + 0.6 * i / 19) for i in range(20)]
        out = smooth_track(samples, win=5, dead_zone=0.04)
        assert out[0][0] == samples[0][0]
        assert out[-1][0] == samples[-1][0]
