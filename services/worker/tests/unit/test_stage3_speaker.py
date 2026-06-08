"""Тесты pure-логики active-speaker reframe: IOU-трекинг лиц + выбор говорящей дорожки/план.

Только numpy (без torch/scipy) → гоняется в базовом гейте без asd-экстры.
"""

from app.pipeline.stage3_speaker import apply_dead_zone, build_tracks, pick_speaker_centers


def _face(frame: int, x1: float, y1: float, x2: float, y2: float) -> dict:
    return {"frame": frame, "bbox": [x1, y1, x2, y2]}


class TestBuildTracks:
    def test_single_face_forms_one_track(self) -> None:
        # одно лицо в одном месте 15 кадров подряд → одна дорожка
        frames = [[_face(i, 100, 100, 200, 200)] for i in range(15)]
        tracks = build_tracks(frames, min_track=10)
        assert len(tracks) == 1
        assert len(tracks[0]["frame"]) == 15

    def test_two_faces_two_tracks(self) -> None:
        # два лица (слева и справа) во всех кадрах → две дорожки
        frames = [[_face(i, 100, 100, 200, 200), _face(i, 800, 100, 900, 200)] for i in range(15)]
        tracks = build_tracks(frames, min_track=10)
        assert len(tracks) == 2
        centers = sorted(((t["bbox"][:, 0] + t["bbox"][:, 2]) / 2).mean() for t in tracks)
        assert centers[0] < 300 and centers[1] > 700

    def test_short_track_dropped(self) -> None:
        # дорожка короче min_track отбрасывается
        frames = [[_face(i, 100, 100, 200, 200)] for i in range(5)]
        assert build_tracks(frames, min_track=10) == []

    def test_gap_within_tolerance_bridged(self) -> None:
        # пропуск детекта на 2 кадра (< num_failed_det) → дорожка не рвётся, bbox интерполируется
        frames = []
        for i in range(15):
            frames.append([] if i in (5, 6) else [_face(i, 100, 100, 200, 200)])
        tracks = build_tracks(frames, min_track=10, num_failed_det=10)
        assert len(tracks) == 1
        assert len(tracks[0]["frame"]) == 15  # дыры заполнены интерполяцией


class TestPickSpeakerCenters:
    # дорожка = (t_start, t_end, center_x_frac, speak_score)
    def test_picks_speaking_not_largest(self) -> None:
        # в плане два лица: молчащее крупное (center 0.3) и говорящее (center 0.7) → берём говорящее
        tracks = [(0.0, 5.0, 0.30, -1.2), (0.0, 5.0, 0.70, 0.4)]
        out = pick_speaker_centers(tracks, [(0.0, 5.0)])
        assert out == [(0.0, 0.70)]

    def test_speaker_switch_between_shots(self) -> None:
        tracks = [(0.0, 5.0, 0.30, 0.5), (5.0, 10.0, 0.75, 0.6)]
        out = pick_speaker_centers(tracks, [(0.0, 5.0), (5.0, 10.0)])
        assert out == [(0.0, 0.30), (5.0, 0.75)]

    def test_shot_without_track_carries_previous(self) -> None:
        tracks = [(0.0, 5.0, 0.40, 0.5)]
        out = pick_speaker_centers(tracks, [(0.0, 5.0), (5.0, 10.0)])
        assert out == [(0.0, 0.40), (5.0, 0.40)]  # второй план без лиц → держим прошлый центр

    def test_first_shot_without_track_uses_default(self) -> None:
        tracks = [(5.0, 10.0, 0.70, 0.5)]
        out = pick_speaker_centers(tracks, [(0.0, 5.0), (5.0, 10.0)], default=0.5)
        assert out == [(0.0, 0.50), (5.0, 0.70)]


class TestApplyDeadZone:
    """Умная статика: окно держим, пока центр не сместился больше порога (гасит «флеши»)."""

    def test_holds_small_changes(self) -> None:
        # серия быстрых склеек с близким кадром → держим первый центр (ноль прыжков)
        centers = [(0.0, 0.50), (2.0, 0.55), (4.0, 0.58), (6.0, 0.47)]
        out = apply_dead_zone(centers, dead_zone=0.12)
        assert out == [(0.0, 0.50), (2.0, 0.50), (4.0, 0.50), (6.0, 0.50)]

    def test_jumps_on_big_shift(self) -> None:
        centers = [(0.0, 0.30), (2.0, 0.70)]  # сдвиг 0.40 >= порога → прыжок
        out = apply_dead_zone(centers, dead_zone=0.12)
        assert out == [(0.0, 0.30), (2.0, 0.70)]

    def test_compares_to_held_not_previous(self) -> None:
        # дрейф 0.3→0.4→0.5→0.6: к ДЕРЖИМОМУ (0.3) 0.4 близко (держим), 0.5 далеко (прыжок),
        # затем к новому держимому (0.5) 0.6 близко (держим)
        centers = [(0.0, 0.30), (2.0, 0.40), (4.0, 0.50), (6.0, 0.60)]
        out = apply_dead_zone(centers, dead_zone=0.12)
        assert out == [(0.0, 0.30), (2.0, 0.30), (4.0, 0.50), (6.0, 0.50)]

    def test_empty_and_single(self) -> None:
        assert apply_dead_zone([], dead_zone=0.12) == []
        assert apply_dead_zone([(0.0, 0.4)], dead_zone=0.12) == [(0.0, 0.4)]
