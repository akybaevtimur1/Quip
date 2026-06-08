"""Тесты pure-математики Stage 3 (reframe 9:16) — баг-опасное место, тест-первым.

Crop-окно 9:16 + клип в границы кадра; агрегация центров лиц (медиана, устойчива
к выбросам на мультиспикере). I/O (ffmpeg+MediaPipe) тестируем глазами на сэмпле.
"""

import pytest

from app.errors import JobError
from app.models import CropWindow
from app.pipeline.stage3_reframe import (
    ShotPlan,
    aggregate_center,
    build_shot_plan,
    build_shots,
    compute_crop_window,
    decide_reframe_mode,
    merge_shot_plan,
    scenes_to_clip_cuts,
    shot_centers,
    windows_to_shot_plan,
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


class TestScenesToClipCuts:
    """PySceneDetect сцены (абс. сек) → КЛИП-относительные внутренние склейки.

    Граница плана = конец сцены i (== старт i+1). Офсет −start (seek был абсолютным);
    оставляем строго внутри (0, duration). Это «офсетная» зона, где рождались флеши.
    """

    def test_empty_no_cuts(self) -> None:
        assert scenes_to_clip_cuts([], start=66.0, duration=20.0) == []

    def test_single_scene_no_cuts(self) -> None:
        assert scenes_to_clip_cuts([(66.0, 86.0)], start=66.0, duration=20.0) == []

    def test_two_scenes_one_cut_offset(self) -> None:
        # реальные числа из спайка: start=66.005, граница на 66.96 → клип-рел 0.955
        assert scenes_to_clip_cuts(
            [(66.005, 66.96), (66.96, 86.74)], start=66.005, duration=20.735
        ) == [0.955]

    def test_interior_only_drops_first_start_and_last_end(self) -> None:
        # 3 сцены → 2 внутренние склейки (концы сцен 0 и 1); старт сцены 0 и конец сцены 2 не в счёт
        out = scenes_to_clip_cuts(
            [(66.0, 67.0), (67.0, 72.0), (72.0, 86.0)], start=66.0, duration=20.0
        )
        assert out == [1.0, 6.0]

    def test_cut_at_or_beyond_duration_filtered(self) -> None:
        # граница ровно на duration (или дальше) — не склейка внутри клипа
        out = scenes_to_clip_cuts([(66.0, 86.0), (86.0, 90.0)], start=66.0, duration=20.0)
        assert out == []


class TestBuildShotPlan:
    """Per-shot план: режим РЕШАЕТСЯ НА КАЖДЫЙ ШОТ (фикс боли «b-roll узким слайсом»).

    Лицо в шоте → fill+центр(медиана); нет лица → fit (широко, блюр-рамки). forced fill/fit
    перекрывает. fill без лица → держим центр предыдущего fill-плана (детект-промах ≠ прыжок).
    """

    def test_all_shots_have_faces_all_fill(self) -> None:
        samples = [(0.1, 0.3), (0.6, 0.4), (1.0, 0.5), (5.5, 0.8)]
        plan = build_shot_plan(samples, [(0.0, 5.0), (5.0, 10.0)])
        assert plan == [
            ShotPlan(t0=0.0, t1=5.0, mode="fill", center=0.4),  # медиана(0.3,0.4,0.5)=0.4
            ShotPlan(t0=5.0, t1=10.0, mode="fill", center=0.8),
        ]

    def test_faceless_shot_becomes_fit(self) -> None:
        # средний план без лиц (b-roll) → fit широко, не узкий слайс старого центра
        samples = [(0.1, 0.3), (11.0, 0.7)]
        plan = build_shot_plan(samples, [(0.0, 5.0), (5.0, 10.0), (10.0, 15.0)])
        assert plan[0] == ShotPlan(t0=0.0, t1=5.0, mode="fill", center=0.3)
        assert plan[1] == ShotPlan(t0=5.0, t1=10.0, mode="fit", center=None)
        assert plan[2] == ShotPlan(t0=10.0, t1=15.0, mode="fill", center=0.7)

    def test_first_shot_faceless_is_fit(self) -> None:
        samples = [(6.0, 0.7)]
        plan = build_shot_plan(samples, [(0.0, 5.0), (5.0, 10.0)])
        assert plan[0] == ShotPlan(t0=0.0, t1=5.0, mode="fit", center=None)
        assert plan[1] == ShotPlan(t0=5.0, t1=10.0, mode="fill", center=0.7)

    def test_forced_fill_faceless_carries_previous(self) -> None:
        # forced fill: faceless-шот не уходит в fit, а держит центр предыдущего fill
        samples = [(0.1, 0.3)]
        plan = build_shot_plan(
            samples, [(0.0, 5.0), (5.0, 10.0)], mode_setting="fill", default_center=0.5
        )
        assert plan == [
            ShotPlan(t0=0.0, t1=5.0, mode="fill", center=0.3),
            ShotPlan(t0=5.0, t1=10.0, mode="fill", center=0.3),  # держим прошлый центр
        ]

    def test_forced_fit_ignores_faces(self) -> None:
        samples = [(0.1, 0.3), (6.0, 0.7)]
        plan = build_shot_plan(samples, [(0.0, 5.0), (5.0, 10.0)], mode_setting="fit")
        assert all(s.mode == "fit" and s.center is None for s in plan)


class TestMergeShotPlan:
    """Слияние смежных шотов с одинаковым (режим, центр) → 1 сегмент рендера (эффективность).

    Статичная камера (10 склеек, тот же кадр) → 1 кодировка, не 10. tolerance ловит дрейф
    медианы сравнением с ДЕРЖИМЫМ центром (не предыдущим) → медленный дрейф не копится.
    """

    def test_empty(self) -> None:
        assert merge_shot_plan([]) == []

    def test_single_unchanged(self) -> None:
        plan = [ShotPlan(0.0, 5.0, "fill", 0.4)]
        assert merge_shot_plan(plan) == plan

    def test_same_center_merges_span(self) -> None:
        plan = [ShotPlan(0.0, 5.0, "fill", 0.4), ShotPlan(5.0, 9.0, "fill", 0.4)]
        assert merge_shot_plan(plan) == [ShotPlan(0.0, 9.0, "fill", 0.4)]

    def test_different_center_not_merged(self) -> None:
        plan = [ShotPlan(0.0, 5.0, "fill", 0.4), ShotPlan(5.0, 9.0, "fill", 0.6)]
        assert merge_shot_plan(plan, tolerance=0.05) == plan

    def test_within_tolerance_merges_holds_first_center(self) -> None:
        plan = [ShotPlan(0.0, 5.0, "fill", 0.40), ShotPlan(5.0, 9.0, "fill", 0.43)]
        assert merge_shot_plan(plan, tolerance=0.05) == [ShotPlan(0.0, 9.0, "fill", 0.40)]

    def test_fill_then_fit_not_merged(self) -> None:
        plan = [ShotPlan(0.0, 5.0, "fill", 0.4), ShotPlan(5.0, 9.0, "fit", None)]
        assert merge_shot_plan(plan) == plan

    def test_adjacent_fits_merge(self) -> None:
        plan = [ShotPlan(0.0, 5.0, "fit", None), ShotPlan(5.0, 9.0, "fit", None)]
        assert merge_shot_plan(plan) == [ShotPlan(0.0, 9.0, "fit", None)]

    def test_slow_drift_breaks_on_held_distance(self) -> None:
        # 0.43 в пределах 0.05 от держимого 0.40 → слив; 0.50 уже 0.10 от 0.40 → новый сегмент
        plan = [
            ShotPlan(0.0, 5.0, "fill", 0.40),
            ShotPlan(5.0, 9.0, "fill", 0.43),
            ShotPlan(9.0, 12.0, "fill", 0.50),
        ]
        assert merge_shot_plan(plan, tolerance=0.05) == [
            ShotPlan(0.0, 9.0, "fill", 0.40),
            ShotPlan(9.0, 12.0, "fill", 0.50),
        ]


class TestWindowsToShotPlan:
    """Speaker-адаптер: окна говорящего (CropWindow на план) → ShotPlan для единого рендера."""

    def test_empty(self) -> None:
        assert windows_to_shot_plan([], duration=20.0, src_w=2000) == []

    def test_single_window_spans_to_duration(self) -> None:
        w = CropWindow(t=0.0, x=900, y=0, w=600, h=1080)
        out = windows_to_shot_plan([w], duration=20.0, src_w=2000)
        # центр = (x + w/2)/src_w = (900+300)/2000 = 0.6
        assert out == [ShotPlan(0.0, 20.0, "fill", 0.6)]

    def test_two_windows_chain_t1(self) -> None:
        w0 = CropWindow(t=0.0, x=900, y=0, w=600, h=1080)
        w1 = CropWindow(t=8.0, x=200, y=0, w=600, h=1080)
        out = windows_to_shot_plan([w0, w1], duration=20.0, src_w=2000)
        assert out == [
            ShotPlan(0.0, 8.0, "fill", 0.6),  # t1 = старт следующего окна
            ShotPlan(8.0, 20.0, "fill", 0.25),  # (200+300)/2000 = 0.25; t1 = duration
        ]


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
