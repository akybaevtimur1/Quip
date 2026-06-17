"""TDD tests for parse_video_map (Task D1.2) and moment_to_interval (D1.3) — PURE, no I/O.

Run (from services/worker with PATH refresh):
    uv run pytest tests/unit/test_video_map.py -q
"""

from __future__ import annotations

from app.editor.video_map import moment_to_interval, parse_video_map
from app.models import Segment, VideoMap, Word

# ─── helpers ─────────────────────────────────────────────────────────────────


def _seg(start: float, end: float) -> Segment:
    """Minimal valid Segment for testing clip_id intersection."""
    return Segment(start=start, end=end, reason="r", score=0.5, type="hook")


def _raw_chapter(
    start: float,
    end: float,
    *,
    title: str = "T",
    summary: str = "S",
    moments: list[dict] | None = None,
) -> dict:
    return {
        "start": start,
        "end": end,
        "title": title,
        "summary": summary,
        "moments": moments or [],
    }


def _raw_moment(
    start: float,
    end: float,
    *,
    label: str = "L",
    why: str = "W",
    kind: str = "tension",
) -> dict:
    return {"start": start, "end": end, "label": label, "why": why, "kind": kind}


def _raw(chapters: list[dict], narrative: str = "N") -> dict:
    return {"narrative": narrative, "chapters": chapters}


# ─── garbage / empty raw ─────────────────────────────────────────────────────


def test_empty_dict_returns_failed_not_raises() -> None:
    result = parse_video_map({}, [], source_dur=100.0)
    assert isinstance(result, VideoMap)
    assert result.status == "failed"
    assert result.error and len(result.error) > 0


def test_chapters_not_list_returns_failed() -> None:
    result = parse_video_map({"chapters": "x", "narrative": "N"}, [], source_dur=100.0)
    assert result.status == "failed"
    assert result.error and len(result.error) > 0


def test_non_dict_raw_returns_failed() -> None:
    # pass something that is not a dict at all — the guard at top of parse_video_map fires
    result = parse_video_map([], [], source_dur=100.0)  # type: ignore[arg-type]
    assert result.status == "failed"
    assert result.error


def test_chapters_none_returns_failed() -> None:
    # dict but chapters key maps to None — missing chapters guard fires
    result = parse_video_map({"narrative": 42, "chapters": None}, [], source_dur=100.0)
    assert result.status == "failed"
    assert result.error


# ─── moment clamping ─────────────────────────────────────────────────────────


def test_moment_end_past_source_dur_clamped() -> None:
    source_dur = 60.0
    moment = _raw_moment(start=55.0, end=70.0)  # end > source_dur → clamp to 60
    chapter = _raw_chapter(0.0, 60.0, moments=[moment])
    result = parse_video_map(_raw([chapter]), [], source_dur=source_dur)
    assert result.status == "done"
    assert len(result.chapters) == 1
    m = result.chapters[0].moments[0]
    assert m.end == source_dur


def test_moment_end_le_start_after_clamp_dropped_sibling_kept() -> None:
    """A degenerate moment (end<=start after clamping) is dropped; valid siblings remain."""
    source_dur = 50.0
    bad_moment = _raw_moment(start=49.5, end=49.0)  # end < start → bad
    good_moment = _raw_moment(start=10.0, end=15.0, label="good", kind="funny")
    chapter = _raw_chapter(0.0, 50.0, moments=[bad_moment, good_moment])
    result = parse_video_map(_raw([chapter]), [], source_dur=source_dur)
    assert result.status == "done"
    assert len(result.chapters[0].moments) == 1
    assert result.chapters[0].moments[0].label == "good"


def test_moment_start_past_source_dur_dropped() -> None:
    """A moment that starts after source_dur (both clamp to source_dur → end<=start) is dropped."""
    source_dur = 30.0
    late_moment = _raw_moment(start=35.0, end=40.0)
    chapter = _raw_chapter(0.0, 30.0, moments=[late_moment])
    result = parse_video_map(_raw([chapter]), [], source_dur=source_dur)
    assert result.status == "done"
    assert result.chapters[0].moments == []


# ─── unknown kind coercion ────────────────────────────────────────────────────


def test_unknown_kind_coerced_not_dropped() -> None:
    moment = _raw_moment(start=5.0, end=10.0, kind="weird")
    chapter = _raw_chapter(0.0, 60.0, moments=[moment])
    result = parse_video_map(_raw([chapter]), [], source_dur=60.0)
    assert result.status == "done"
    m = result.chapters[0].moments[0]
    # moment kept, kind coerced to a valid value
    valid_kinds = {"tension", "quote", "emotional", "insight", "funny"}
    assert m.kind in valid_kinds


# ─── clip_ids intersection ────────────────────────────────────────────────────


def test_chapter_overlapping_segment2_has_clip02() -> None:
    """Chapter [30, 60) overlaps segment #2 (index 1, 0-based) → clip_ids contains 'clip_02'."""
    segments = [
        _seg(10.0, 25.0),  # clip_01
        _seg(30.0, 50.0),  # clip_02
        _seg(70.0, 90.0),  # clip_03
    ]
    chapter = _raw_chapter(28.0, 55.0)  # overlaps clip_02 [30,50]
    result = parse_video_map(_raw([chapter]), segments, source_dur=120.0)
    assert result.status == "done"
    assert "clip_02" in result.chapters[0].clip_ids


def test_chapter_not_overlapping_any_segment_empty_clip_ids() -> None:
    segments = [
        _seg(10.0, 20.0),  # clip_01
        _seg(30.0, 40.0),  # clip_02
    ]
    chapter = _raw_chapter(50.0, 60.0)  # no overlap with any segment
    result = parse_video_map(_raw([chapter]), segments, source_dur=100.0)
    assert result.status == "done"
    assert result.chapters[0].clip_ids == []


def test_chapter_overlapping_multiple_segments_has_all_ids() -> None:
    segments = [
        _seg(5.0, 15.0),  # clip_01
        _seg(20.0, 35.0),  # clip_02
        _seg(40.0, 60.0),  # clip_03
    ]
    chapter = _raw_chapter(10.0, 45.0)  # overlaps clip_01, clip_02, clip_03
    result = parse_video_map(_raw([chapter]), segments, source_dur=100.0)
    ids = result.chapters[0].clip_ids
    assert "clip_01" in ids
    assert "clip_02" in ids
    assert "clip_03" in ids


def test_touching_segments_not_counted_as_overlap() -> None:
    """Segments that merely touch (share an endpoint) but don't overlap are excluded."""
    segments = [_seg(0.0, 10.0)]  # clip_01
    chapter = _raw_chapter(10.0, 20.0)  # starts exactly where clip_01 ends
    result = parse_video_map(_raw([chapter]), segments, source_dur=60.0)
    # open interval intersection: [0,10) ∩ [10,20) = empty
    assert result.chapters[0].clip_ids == []


# ─── valid result structure ───────────────────────────────────────────────────


def test_valid_raw_returns_done_with_narrative() -> None:
    chapter = _raw_chapter(0.0, 30.0)
    result = parse_video_map(_raw([chapter], narrative="Great video"), [], source_dur=30.0)
    assert result.status == "done"
    assert result.narrative == "Great video"
    assert result.error is None


def test_chapter_times_clamped_to_source_dur() -> None:
    chapter = _raw_chapter(0.0, 200.0)  # end > source_dur
    result = parse_video_map(_raw([chapter]), [], source_dur=100.0)
    assert result.status == "done"
    assert result.chapters[0].end <= 100.0


def test_chapter_with_missing_required_fields_dropped() -> None:
    """A chapter dict missing title or summary is dropped gracefully."""
    bad_chapter = {"start": 0.0, "end": 30.0}  # missing title, summary
    good_chapter = _raw_chapter(30.0, 60.0, title="Good", summary="Fine")
    result = parse_video_map(_raw([bad_chapter, good_chapter]), [], source_dur=60.0)
    assert result.status == "done"
    assert len(result.chapters) == 1
    assert result.chapters[0].title == "Good"


# ─── moment_to_interval (D1.3) ───────────────────────────────────────────────


def _make_words(starts: list[float], dur: float = 2.0) -> list[Word]:
    """Build a list of Word objects with sequential timing.

    Each word spans [start, start+dur). Text alternates sentence-ending words to give
    snap_start/snap_end clean boundaries.
    """
    words: list[Word] = []
    for i, s in enumerate(starts):
        # Every 5th word ends a sentence so snap has clean boundaries available.
        text = "Hello." if (i % 5 == 4) else "word"
        words.append(Word(text=text, start=s, end=s + dur))
    return words


def test_moment_to_interval_short_moment_expands_to_min_sec() -> None:
    """A 10-second moment should expand to ≥20s (default min_sec)."""
    # 40 words spaced 2s apart → transcript covers 0..82s
    starts = [float(i * 2) for i in range(40)]
    words = _make_words(starts)
    source_dur = words[-1].end  # 82.0

    # moment at 20s–30s = 10s long
    s, e = moment_to_interval(20.0, 30.0, words, source_dur=source_dur)
    assert e - s >= 20.0, f"expected ≥20s, got {e - s:.2f}s"
    assert 0.0 <= s
    assert e <= source_dur


def test_moment_to_interval_near_eov_expands_left() -> None:
    """A moment near the end of video must expand LEFT; end must stay ≤ source_dur."""
    starts = [float(i * 2) for i in range(40)]
    words = _make_words(starts)
    source_dur = words[-1].end  # 82.0

    # moment at 77s–82s = 5s, near EOV
    s, e = moment_to_interval(77.0, 82.0, words, source_dur=source_dur)
    assert e <= source_dur, f"end {e} exceeded source_dur {source_dur}"
    assert e - s >= 20.0, f"expected ≥20s, got {e - s:.2f}s"
    # end must NOT be pushed beyond source_dur; the expansion went left
    assert s < e


def test_moment_to_interval_snaps_to_word_boundaries() -> None:
    """Returned times must match words[idx].start / words[idx].end exactly."""
    # Simple uniform transcript: 30 words, each 1s wide, 0.5s gap between
    # pattern: word spans [i*1.5, i*1.5+1.0]. Every 5th word sentence-ends.
    words: list[Word] = []
    for i in range(30):
        text = "end." if (i % 5 == 4) else "word"
        words.append(Word(text=text, start=i * 1.5, end=i * 1.5 + 1.0))
    source_dur = words[-1].end  # 44.5

    # moment input in the middle
    s, e = moment_to_interval(10.0, 25.0, words, source_dur=source_dur)

    # returned times must align exactly with some word's .start and some word's .end
    word_starts = {w.start for w in words}
    word_ends = {w.end for w in words}
    assert s in word_starts, f"s={s} is not a word boundary (.start)"
    assert e in word_ends, f"e={e} is not a word boundary (.end)"


def test_moment_to_interval_already_long_enough_not_trimmed() -> None:
    """A moment ≥20s should NOT be trimmed (only clamped to source_dur)."""
    starts = [float(i * 2) for i in range(40)]
    words = _make_words(starts)
    source_dur = words[-1].end

    # 25s moment — already above min_sec; result should be ≥25s (after snapping)
    # (snap may extend slightly; clamp ensures we don't exceed source_dur)
    s, e = moment_to_interval(10.0, 35.0, words, source_dur=source_dur)
    assert e - s >= 20.0
    assert e <= source_dur
