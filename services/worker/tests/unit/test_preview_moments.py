"""Косметический детектор моментов (co-watch). PURE. НЕ влияет на LLM-отбор."""

from app.models import Word
from app.pipeline.preview_moments import detect_preview_moments


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
