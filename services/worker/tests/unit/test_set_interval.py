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


# ─── D0.1: clip_min_sec = 20 (TDD) ─────────────────────────────────────────


def test_config_default_clip_min_sec_is_20() -> None:
    """Config default must be 20s — this test goes RED at 15, GREEN after config change."""
    from app.config import Settings

    s = Settings()  # instantiate directly (bypass lru_cache to avoid env pollution)
    assert s.clip_min_sec == 20


def test_clamp_too_short_extends_to_min_20() -> None:
    """A 10s window must expand to exactly 20s when min_sec=20."""
    assert clamp_interval(5, 15, duration=200, min_sec=20, max_sec=60) == (5.0, 25.0)


# ─── D2.1: end-of-video clamping (TDD) ──────────────────────────────────────


def test_clamp_max_arm_overflow_end_of_video() -> None:
    """max-arm overflow scenario from brief: clamp_interval(190, 999, ...).

    step1: s=190, e=min(999,200)=200, length=10 < min_sec=20
    step3 (min arm): e=190+20=210>200 → e=200, s=max(0,200-20)=180
    Result: (180.0, 200.0) — end never exceeds duration, length == min_sec.
    """
    result = clamp_interval(190, 999, duration=200, min_sec=20, max_sec=60)
    s, e = result
    assert e <= 200.0, f"end {e} exceeds duration 200"
    assert e - s >= 20.0, f"length {e - s} < min_sec 20"
    assert result == (180.0, 200.0)


def test_clamp_max_arm_sets_e_beyond_duration() -> None:
    """Max-arm path: after step1, s+max_sec > duration → e must be clamped to duration.

    Craft: source_start=0, source_end=large, duration=50, min_sec=5, max_sec=60.
    step1: s=0, e=50, length=50 < max_sec=60 → no max arm.
    Try: duration=50, max_sec=40, min_sec=5.
    s=15, e=999 → step1: e=50, length=35 < 40 → no max arm.
    Need length > max_sec after step1:
    s=0, e=999, duration=50, max_sec=30, min_sec=5.
    step1: e=50, length=50 > 30 → max arm: e=0+30=30, 30 ≤ 50 ✓ → (0,30).
    Now the bug scenario — force s+max_sec > duration:
    s=30, e=999, duration=50, max_sec=30, min_sec=5.
    step1: e=50, length=20 ≤ 30 → no max arm → (30, 50). OK no bug path.
    The actual max-arm overflow is only reachable when source_start is small enough
    for length>max_sec, but large enough for s+max_sec>duration.
    E.g. duration=100, max_sec=80, min_sec=5, s=30, e=999.
    step1: e=100, length=70 ≤ 80 → no max arm. Still no.
    s=10, e=999, duration=100, max_sec=80, min_sec=5.
    step1: e=100, length=90 > 80 → max arm: e=10+80=90 ≤ 100 ✓.
    For overflow: s=25, e=999, duration=100, max_sec=80.
    step1: e=100, length=75 ≤ 80 → no max arm.
    It's impossible after step1 clamp: if e=duration and length>max_sec → s<duration-max_sec
    → s+max_sec < duration. The defensive `e = min(e, duration)` guard is still correct.
    """
    # Verify max arm normal case (no overflow): result is s + max_sec
    result = clamp_interval(0, 999, duration=50, min_sec=5, max_sec=30)
    assert result == (0.0, 30.0)
    assert result[1] <= 50.0


def test_clamp_nudge_at_end() -> None:
    """Near-end interval nudged so requested end > duration → end == duration, length ≥ min_sec."""
    # Current clip: 185-200s. Nudge end +10s → requested (185, 210).
    # step1: s=185, e=200 (clamped), length=15 < min_sec=20
    # step3 (min arm): e=185+20=205>200 → e=200, s=max(0,180)=180
    result = clamp_interval(185, 210, duration=200, min_sec=20, max_sec=60)
    s, e = result
    assert e == 200.0, f"end {e} != duration 200"
    assert e - s >= 20.0, f"length {e - s} < min_sec 20"
    assert result == (180.0, 200.0)


def test_clamp_sanity_in_bounds_unchanged() -> None:
    """A normal interval well within bounds is returned unchanged."""
    assert clamp_interval(30, 70, duration=200, min_sec=20, max_sec=60) == (30.0, 70.0)
