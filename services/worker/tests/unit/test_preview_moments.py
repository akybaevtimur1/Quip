"""Косметический детектор моментов (co-watch). PURE. НЕ влияет на LLM-отбор."""

from app.models import PreviewMoment, Word
from app.pipeline.preview_moments import (
    detect_energy_moments,
    detect_preview_moments,
    merge_moments,
)


def _w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_question_detected() -> None:
    # contiguous words (no gaps → no beats); content signal wins.
    ms = detect_preview_moments([_w("why", 0.0, 0.3), _w("now?", 0.3, 0.6)])
    assert [m.kind for m in ms] == ["question"]
    assert ms[0].t == 0.3


def test_emphasis_detected() -> None:
    ms = detect_preview_moments([_w("so", 0.0, 0.3), _w("big!", 0.3, 0.6)])
    assert [m.kind for m in ms] == ["emphasis"]


def test_stat_detected() -> None:
    ms = detect_preview_moments([_w("about", 0.0, 0.3), _w("90", 0.3, 0.6)])
    assert [m.kind for m in ms] == ["stat"]


def test_content_signal_beats_a_preceding_pause() -> None:
    # A "!" word AFTER a long pause is emphasis (content-first), not a beat.
    ms = detect_preview_moments([_w("wait", 0.0, 0.5), _w("boom!", 3.0, 3.5)], min_gap_s=0.5)
    assert [m.kind for m in ms] == ["emphasis"]


def test_intensities_in_range_and_sorted_by_time() -> None:
    words = [
        _w("why", 0.0, 0.3),
        _w("now?", 0.3, 0.6),
        _w("we", 0.6, 0.9),
        _w("got", 0.9, 1.2),
        _w("50", 1.2, 1.5),
        _w("more", 1.5, 1.8),
        _w("huge!", 1.8, 2.1),
    ]
    ms = detect_preview_moments(words, min_gap_s=0.5)
    assert all(0.0 <= m.intensity <= 1.0 for m in ms)
    assert ms == sorted(ms, key=lambda m: m.t)


def test_pause_before_word_is_a_beat_with_gap_scaled_intensity() -> None:
    words = [_w("Setup", 0.0, 0.5), _w("punchline", 3.0, 3.5)]  # 2.5s gap → strong beat
    ms = detect_preview_moments(words, min_gap_s=0.5)
    beats = [m for m in ms if m.kind == "beat"]
    assert len(beats) == 1
    assert beats[0].t == 3.0
    assert beats[0].intensity == 1.0  # gap >= _BEAT_FULL_GAP_S → max


def test_min_gap_keeps_stronger_marker_in_window() -> None:
    # Два сигнала ближе min_gap_s: держим более сильный (emphasis 0.85 > stat 0.6).
    words = [_w("5", 0.0, 0.2), _w("wow!", 0.4, 0.8)]
    ms = detect_preview_moments(words, min_gap_s=1.0)
    assert len(ms) == 1
    assert ms[0].kind == "emphasis"


def test_max_moments_cap_keeps_strongest_then_sorts_by_time() -> None:
    words = [_w(f"{i}", float(i) * 2, float(i) * 2 + 0.2) for i in range(1, 11)]  # 10 stats
    ms = detect_preview_moments(words, max_moments=3, min_gap_s=0.5)
    assert len(ms) == 3
    assert ms == sorted(ms, key=lambda m: m.t)


def test_empty_words_yields_nothing() -> None:
    assert detect_preview_moments([]) == []


# ── audio-energy detector (pure peak picker over a loudness curve) ──


def test_energy_peaks_become_emphasis_markers_at_right_times() -> None:
    # flat baseline with two clear peaks at indices 4 and 12; hop 0.5s → t=2.0 and t=6.0.
    rms = [-30.0] * 16
    rms[4] = -8.0
    rms[12] = -10.0
    ms = detect_energy_moments(rms, hop_s=0.5, min_gap_s=1.0)
    assert all(m.kind == "emphasis" for m in ms)
    times = {m.t for m in ms}
    assert 2.0 in times and 6.0 in times
    assert all(0.0 <= m.intensity <= 1.0 for m in ms)


def test_flat_loudness_yields_no_peaks() -> None:
    assert detect_energy_moments([-30.0] * 20, hop_s=0.5) == []


def test_energy_too_short_is_empty() -> None:
    assert detect_energy_moments([-10.0, -5.0], hop_s=0.5) == []


def test_merge_combines_and_spaces_two_groups() -> None:
    a = [PreviewMoment(t=1.0, kind="stat", intensity=0.6)]
    b = [
        PreviewMoment(t=1.2, kind="emphasis", intensity=0.9),  # within min_gap of a → stronger wins
        PreviewMoment(t=5.0, kind="question", intensity=0.7),
    ]
    out = merge_moments(a, b, min_gap_s=1.5)
    assert [m.t for m in out] == [1.2, 5.0]
    assert out[0].kind == "emphasis"  # stronger of the two near t≈1
