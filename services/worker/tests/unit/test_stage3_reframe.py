"""Тесты pure-математики Stage 3 (reframe 9:16) — тест-первым.

Cut-aligned reframe: TrackPoint/TrackRegion, classify_frame, smooth_centers,
merge_short_regions, build_regions_from_shots, plan_regions, build_shots_frames.
I/O (ffmpeg/MediaPipe) тестируем глазами на сэмпле.
"""

import pytest

from app.errors import JobError
from app.pipeline.stage3_reframe import (
    TrackPoint,
    TrackRegion,
    classify_frame,
    compute_crop_window,
    merge_short_regions,
    shot_is_wide,
    smooth_centers,
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
        c = compute_crop_window(1920, 1080, 1.5, t=0.0)
        assert c.x + c.w <= 1920

    def test_source_too_narrow_raises(self) -> None:
        with pytest.raises(JobError):
            compute_crop_window(500, 1080, 0.5, t=0.0)

    def test_bad_dims_raise(self) -> None:
        with pytest.raises(JobError):
            compute_crop_window(0, 1080, 0.5, t=0.0)


class TestShotIsWide:
    def test_empty_not_wide(self) -> None:
        assert shot_is_wide([], crop_w_frac=0.32) is False

    def test_single_face_frames_not_wide(self) -> None:
        assert shot_is_wide([[0.5], [0.52], [0.48]], crop_w_frac=0.32) is False

    def test_two_spread_faces_wide(self) -> None:
        assert shot_is_wide([[0.3, 0.7], [0.3, 0.7]], crop_w_frac=0.32) is True

    def test_two_close_faces_not_wide(self) -> None:
        assert shot_is_wide([[0.45, 0.55], [0.45, 0.55]], crop_w_frac=0.32) is False

    def test_majority_wide_triggers(self) -> None:
        assert shot_is_wide([[0.3, 0.7], [0.5]], crop_w_frac=0.32) is True


class TestSmoothCenters:
    """Exponential smoothing: нет лица → держим последний; первый без лица → 0.5."""

    def test_smoothing_zero_freezes(self) -> None:
        # smoothing=0 → camera never moves (last = last + 0*(cx-last) = last всегда)
        result = smooth_centers([None, 0.3, 0.7], smoothing=0.0)
        assert result[0] == 0.5  # нет лица, дефолт 0.5
        assert result[1] == 0.5  # smoothing=0 → заморожено на 0.5
        assert result[2] == 0.5  # всё ещё 0.5

    def test_no_face_holds_last(self) -> None:
        result = smooth_centers([0.6, None, None], smoothing=1.0)
        assert result[0] == pytest.approx(0.5 + 1.0 * (0.6 - 0.5))  # = 0.6
        assert result[1] == result[0]  # нет лица → держим
        assert result[2] == result[0]  # нет лица → держим

    def test_first_without_face_defaults_to_half(self) -> None:
        result = smooth_centers([None, None, 0.8], smoothing=0.15)
        assert result[0] == 0.5  # нет лица сначала → 0.5
        assert result[1] == 0.5  # всё ещё нет лица
        assert result[2] == pytest.approx(0.5 + 0.15 * (0.8 - 0.5))  # плавно к 0.8

    def test_smoothing_toward_target(self) -> None:
        result = smooth_centers([0.8], smoothing=0.15)
        # last=0.5; 0.5 + 0.15*(0.8-0.5) = 0.5 + 0.045 = 0.545
        assert result[0] == pytest.approx(0.545)

    def test_smoothing_one_jumps(self) -> None:
        result = smooth_centers([0.3, 0.9], smoothing=1.0)
        assert result[0] == pytest.approx(0.3)
        assert result[1] == pytest.approx(0.9)

    def test_empty_returns_empty(self) -> None:
        assert smooth_centers([]) == []


class TestClassifyFrame:
    """fit/fill по геометрии лиц одного кадра."""

    def test_no_faces_is_fit(self) -> None:
        assert classify_frame([], crop_w_frac=0.32) == "fit"

    def test_single_face_is_fill(self) -> None:
        assert classify_frame([(0.5, 0.1)], crop_w_frac=0.32) == "fill"

    def test_two_spread_faces_is_fit(self) -> None:
        # размах 0.7-0.3=0.4 > 0.32 → широко
        assert classify_frame([(0.3, 0.1), (0.7, 0.1)], crop_w_frac=0.32) == "fit"

    def test_two_close_faces_is_fill(self) -> None:
        # размах 0.55-0.45=0.1 < 0.32 → кластер → fill
        assert classify_frame([(0.45, 0.1), (0.55, 0.1)], crop_w_frac=0.32) == "fill"


class TestMergeShortRegions:
    """Анти-флеш V2: регион < min_hold_sec поглощается предыдущим."""

    def test_empty(self) -> None:
        assert merge_short_regions([], min_hold_sec=1.5) == []

    def test_single_unchanged(self) -> None:
        reg = [TrackRegion(0.0, 5.0, "fill", ())]
        assert merge_short_regions(reg, min_hold_sec=1.5) == reg

    def test_short_region_absorbed(self) -> None:
        prev_pt = TrackPoint(t=0.0, mode="fill", cx=0.5)
        regions = [
            TrackRegion(0.0, 3.0, "fill", (prev_pt,)),
            TrackRegion(3.0, 3.4, "fit", ()),  # 0.4с < 1.5 → поглощается
            TrackRegion(3.4, 6.0, "fill", ()),
        ]
        result = merge_short_regions(regions, min_hold_sec=1.5)
        # fit-регион поглощён в предыдущий fill → [0,3.4 fill, 3.4,6 fill]
        assert len(result) == 2
        assert result[0].t0 == 0.0
        assert result[0].t1 == 3.4
        assert result[0].mode == "fill"
        assert result[1].t0 == 3.4

    def test_long_regions_kept(self) -> None:
        regions = [
            TrackRegion(0.0, 3.0, "fill", ()),
            TrackRegion(3.0, 6.0, "fit", ()),  # 3с ≥ 1.5 → остаётся
        ]
        assert merge_short_regions(regions, min_hold_sec=1.5) == regions

    def test_first_short_not_absorbed(self) -> None:
        # первый регион короткий — нет предыдущего → остаётся
        regions = [
            TrackRegion(0.0, 0.3, "fit", ()),
            TrackRegion(0.3, 5.0, "fill", ()),
        ]
        result = merge_short_regions(regions, min_hold_sec=1.5)
        assert result[0].t0 == 0.0  # первый не поглощён


class TestBuildShotsFrames:
    def test_no_cuts_one_shot(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        assert build_shots_frames([], total_frames=150) == [(0, 150)]

    def test_cuts_split_into_frame_intervals(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        # склейки на кадрах 50 и 100 → 3 шота в КАДРАХ
        assert build_shots_frames([50, 100], total_frames=150) == [(0, 50), (50, 100), (100, 150)]

    def test_dedup_and_sort(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        assert build_shots_frames([100, 50, 50], total_frames=150) == [
            (0, 50),
            (50, 100),
            (100, 150),
        ]

    def test_cuts_at_bounds_ignored(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        # склейка на 0 и на total — не порождают пустых шотов
        assert build_shots_frames([0, 150], total_frames=150) == [(0, 150)]

    def test_zero_total_empty(self) -> None:
        from app.pipeline.stage3_reframe import build_shots_frames

        assert build_shots_frames([10], total_frames=0) == []


class TestSamplesInShot:
    def test_filters_to_interval_half_open(self) -> None:
        from app.pipeline.stage3_reframe import samples_in_shot

        raw = [(0.0, [(0.5, 0.1)]), (0.2, [(0.4, 0.1)]), (0.4, []), (0.6, [(0.7, 0.1)])]
        # интервал [0.2, 0.6): берём t=0.2 и t=0.4, НЕ берём 0.0 и 0.6
        got = samples_in_shot(raw, 0.2, 0.6)
        assert [t for t, _ in got] == [0.2, 0.4]

    def test_empty_when_no_samples_in_range(self) -> None:
        from app.pipeline.stage3_reframe import samples_in_shot

        assert samples_in_shot([(0.0, []), (5.0, [])], 1.0, 2.0) == []


class TestDecideShotMode:
    def test_no_samples_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        assert decide_shot_mode([], crop_w_frac=0.3) == "fit"

    def test_single_face_cluster_is_fill(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        # одно лицо в каждом кадре → fill
        samples = [(0.0, [(0.5, 0.1)]), (0.2, [(0.52, 0.1)]), (0.4, [(0.48, 0.1)])]
        assert decide_shot_mode(samples, crop_w_frac=0.3) == "fill"

    def test_two_spread_faces_majority_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        # 2 разнесённых лица (размах 0.6 > crop_w_frac 0.3) в большинстве кадров → fit
        wide = [(0.1, 0.1), (0.7, 0.1)]
        samples = [(0.0, wide), (0.2, wide), (0.4, [(0.5, 0.1)])]
        assert decide_shot_mode(samples, crop_w_frac=0.3) == "fit"

    def test_mode_setting_overrides(self) -> None:
        from app.pipeline.stage3_reframe import decide_shot_mode

        wide = [(0.1, 0.1), (0.7, 0.1)]
        assert decide_shot_mode([(0.0, wide)], crop_w_frac=0.3, mode_setting="fill") == "fill"
        assert decide_shot_mode([(0.0, [(0.5, 0.1)])], crop_w_frac=0.3, mode_setting="fit") == "fit"


class TestBuildShotTrajectory:
    def test_returns_trackpoints_with_smoothed_cx(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        samples = [(1.0, [(0.2, 0.1)]), (1.2, [(0.8, 0.1)])]
        pts = build_shot_trajectory(samples, smoothing=0.5)
        assert len(pts) == 2
        assert pts[0].t == 1.0 and pts[0].mode == "fill"
        # init=first face cx=0.2; первый сэмпл: 0.2 + 0.5*(0.2-0.2) = 0.2 (снэп)
        assert abs(pts[0].cx - 0.2) < 1e-9
        # второй: 0.2 + 0.5*(0.8-0.2) = 0.5
        assert abs(pts[1].cx - 0.5) < 1e-9

    def test_largest_face_chosen(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        # два лица: крупнейшее (w=0.3) на cx=0.9 → к нему ведём
        pts = build_shot_trajectory([(0.0, [(0.1, 0.1), (0.9, 0.3)])], smoothing=1.0)
        assert abs(pts[0].cx - 0.9) < 1e-9

    def test_no_face_holds_last(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        pts = build_shot_trajectory([(0.0, [(0.2, 0.1)]), (0.2, [])], smoothing=1.0)
        # второй сэмпл без лица → держим последний (0.2)
        assert abs(pts[1].cx - 0.2) < 1e-9

    def test_first_point_snaps_to_face_not_center(self) -> None:
        from app.pipeline.stage3_reframe import build_shot_trajectory

        # Face at cx=0.9 (far from center 0.5). With smoothing=0.15, old code:
        # first = 0.5 + 0.15*(0.9 - 0.5) = 0.56 (drift from center).
        # New code: init=0.9, first = 0.9 + 0.15*(0.9 - 0.9) = 0.9 (snap to face).
        pts = build_shot_trajectory([(0.0, [(0.9, 0.1)])], smoothing=0.15)
        assert abs(pts[0].cx - 0.9) < 1e-6  # must snap, not drift


class TestBuildRegionsFromShots:
    def test_one_mode_per_shot_cut_aligned(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_from_shots

        # 3 плана по реальным склейкам; средний -- широкий (2 разнесённых лица)
        shots = [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]
        single = [(0.5, 0.1)]
        wide = [(0.1, 0.1), (0.8, 0.1)]
        raw = [
            (0.0, single),
            (1.0, single),  # план 1 -> fill
            (2.0, wide),
            (3.0, wide),  # план 2 -> fit
            (4.0, single),
            (5.0, single),  # план 3 -> fill
        ]
        regions = build_regions_from_shots(
            shots, raw, crop_w_frac=0.3, smoothing=0.15, min_hold_sec=0.0
        )
        assert [(r.t0, r.t1, r.mode) for r in regions] == [
            (0.0, 2.0, "fill"),
            (2.0, 4.0, "fit"),
            (4.0, 6.0, "fill"),
        ]
        # границы режима = границы планов (= реальные склейки), НЕ сетка сэмплов
        assert regions[0].points and regions[2].points  # fill-планы имеют траекторию
        assert regions[1].points == ()  # fit-план без траектории

    def test_short_shot_absorbed_by_min_hold(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_from_shots

        # короткий средний план (0.3с < min_hold 1.5) поглощается предыдущим -> нет дрожи
        shots = [(0.0, 2.0), (2.0, 2.3), (2.3, 4.0)]
        single = [(0.5, 0.1)]
        wide = [(0.1, 0.1), (0.8, 0.1)]
        raw = [(0.0, single), (2.0, wide), (2.3, single)]
        regions = build_regions_from_shots(
            shots, raw, crop_w_frac=0.3, smoothing=0.15, min_hold_sec=1.5
        )
        assert all(r.mode == "fill" for r in regions)  # короткий fit съеден

    def test_fill_without_faces_has_fallback_point(self) -> None:
        from app.pipeline.stage3_reframe import build_regions_from_shots

        # mode_setting=fill форсит fill даже без лиц -> должна быть точка-фолбэк (cx=0.5)
        regions = build_regions_from_shots(
            [(0.0, 2.0)],
            [(0.0, [])],
            crop_w_frac=0.3,
            smoothing=0.15,
            min_hold_sec=0.0,
            mode_setting="fill",
        )
        assert regions[0].mode == "fill"
        assert regions[0].points and abs(regions[0].points[0].cx - 0.5) < 1e-9


class TestPlanRegions:
    """plan_regions: shots(кадры) + SpeakerTrack → TrackRegion, решение на шот."""

    def _track(self, f0: int, f1: int, cx: float, width: float, speak: float):  # type: ignore[no-untyped-def]
        from app.pipeline.stage3_reframe import SpeakerTrack

        n = f1 - f0
        return SpeakerTrack(f0=f0, f1=f1, cx=tuple([cx] * n), width=width, speak=speak)

    def test_single_speaker_fill_on_track(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # один шот [0,30 кадров), один говорящий на cx=0.7
        tracks = [self._track(0, 30, 0.7, 0.12, 0.9)]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.0
        )
        assert len(regions) == 1
        assert regions[0].mode == "fill"
        assert regions[0].points  # есть траектория
        assert abs(regions[0].points[0].cx - 0.7) < 1e-9

    def test_two_spread_speakers_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        tracks = [
            self._track(0, 30, 0.2, 0.1, 0.5),
            self._track(0, 30, 0.8, 0.1, 0.5),
        ]
        regions = plan_regions([(0, 30)], tracks, fps=30.0, crop_w_frac=0.32)
        assert regions[0].mode == "fit"
        assert regions[0].points == ()

    def test_picks_louder_speaker_not_largest(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # ДВА лица КЛАСТЕРОМ (размах 0.15 < crop_w 0.32 → не широко). Крупнее (width 0.3) на
        # cx=0.45 молчит; говорит мелкое (width 0.1) на cx=0.60 → кадр на говорящего.
        tracks = [
            self._track(0, 30, 0.45, 0.3, 0.1),
            self._track(0, 30, 0.60, 0.1, 0.95),
        ]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.3
        )
        assert regions[0].mode == "fill"
        assert abs(regions[0].points[0].cx - 0.60) < 1e-9  # на говорящего, не на крупнейшего

    def test_asd_silent_falls_back_to_largest_face(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # Кластер (не широко); никто не превышает порог → берём крупнейшее лицо (width 0.3, cx=0.45)
        tracks = [
            self._track(0, 30, 0.45, 0.3, 0.05),
            self._track(0, 30, 0.60, 0.1, 0.10),
        ]
        regions = plan_regions(
            [(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, smoothing=1.0, speak_threshold=0.5
        )
        assert regions[0].mode == "fill"
        assert abs(regions[0].points[0].cx - 0.45) < 1e-9  # фолбэк на largest-face

    def test_no_tracks_is_fit(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        regions = plan_regions([(0, 30)], [], fps=30.0, crop_w_frac=0.32)
        assert regions[0].mode == "fit"

    def test_speaker_change_between_shots(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        # шот1 [0,30): говорит A(cx0.3); шот2 [30,60): говорит B(cx0.7)
        tracks = [
            self._track(0, 30, 0.3, 0.1, 0.9),
            self._track(30, 60, 0.7, 0.1, 0.9),
        ]
        regions = plan_regions(
            [(0, 30), (30, 60)],
            tracks,
            fps=30.0,
            crop_w_frac=0.32,
            smoothing=1.0,
            speak_threshold=0.0,
        )
        assert len(regions) == 2
        assert abs(regions[0].points[0].cx - 0.3) < 1e-9
        assert abs(regions[1].points[0].cx - 0.7) < 1e-9
        # границы регионов = границы шотов в СЕКУНДАХ (кадр/fps)
        assert regions[0].t0 == 0.0 and regions[0].t1 == 1.0
        assert regions[1].t0 == 1.0 and regions[1].t1 == 2.0

    def test_mode_setting_fit_overrides(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        tracks = [self._track(0, 30, 0.5, 0.1, 0.9)]
        regions = plan_regions([(0, 30)], tracks, fps=30.0, crop_w_frac=0.32, mode_setting="fit")
        assert regions[0].mode == "fit"

    def test_mode_setting_fill_no_track_fallback_center(self) -> None:
        from app.pipeline.stage3_reframe import plan_regions

        regions = plan_regions([(0, 30)], [], fps=30.0, crop_w_frac=0.32, mode_setting="fill")
        assert regions[0].mode == "fill"
        assert regions[0].points and abs(regions[0].points[0].cx - 0.5) < 1e-9
