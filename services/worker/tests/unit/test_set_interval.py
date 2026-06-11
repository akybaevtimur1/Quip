"""PURE-тесты для clamp_interval / set_interval (таймлайн: двигать/resize шортс).

Кламп границ в [0,duration] и мин/макс длины — частый источник off-by-one/багов,
поэтому тест ПЕРВЫМ (правило №3).
"""

from __future__ import annotations

from app.editor.ops import clamp_interval, set_interval
from app.models import CaptionStyle, CaptionTrack, ClipEdit, SourceInterval, Word

# ─── clamp_interval (PURE) ───────────────────────────────────────────────────


def test_clamp_in_range_unchanged() -> None:
    assert clamp_interval(40, 66, duration=200, min_sec=15, max_sec=60) == (40.0, 66.0)


def test_clamp_negative_start() -> None:
    assert clamp_interval(-5, 20, duration=200, min_sec=15, max_sec=60) == (0.0, 20.0)


def test_clamp_end_past_duration() -> None:
    # 190..210 → end clamp to 200, len 10 < 15 → расширяем влево до 185..200
    assert clamp_interval(190, 210, duration=200, min_sec=15, max_sec=60) == (185.0, 200.0)


def test_clamp_too_short_extends_to_min() -> None:
    assert clamp_interval(10, 12, duration=200, min_sec=15, max_sec=60) == (10.0, 25.0)


def test_clamp_too_long_trims_to_max() -> None:
    assert clamp_interval(10, 100, duration=200, min_sec=15, max_sec=60) == (10.0, 70.0)


def test_clamp_inverted_range_fixed() -> None:
    # end <= start → схлопывается, затем расширяется до min
    assert clamp_interval(50, 40, duration=200, min_sec=15, max_sec=60) == (50.0, 65.0)


def test_clamp_duration_shorter_than_min() -> None:
    # источник короче min: окно = весь источник
    assert clamp_interval(0, 100, duration=8, min_sec=15, max_sec=60) == (0.0, 8.0)


# ─── set_interval (PURE) ─────────────────────────────────────────────────────


def _edit() -> ClipEdit:
    return ClipEdit(
        id="clip_01",
        source_intervals=[SourceInterval(source_start=40.0, source_end=66.0)],
        captions=CaptionTrack(style=CaptionStyle()),
    )


def _words() -> list[Word]:
    return [Word(text="a", start=101.0, end=101.5), Word(text="b", start=120.0, end=120.5)]


def test_set_interval_replaces_with_single_clamped() -> None:
    new = set_interval(_edit(), 100, 130, _words(), duration=200, min_sec=15, max_sec=60)
    assert len(new.source_intervals) == 1
    assert new.source_intervals[0].source_start == 100.0
    assert new.source_intervals[0].source_end == 130.0


def test_set_interval_clamps_out_of_range() -> None:
    new = set_interval(_edit(), -10, 5, _words(), duration=200, min_sec=15, max_sec=60)
    assert new.source_intervals[0].source_start == 0.0
    assert new.source_intervals[0].source_end == 15.0  # extended to min
