"""TDD tests for parse_video_map (Task D1.2) — PURE parser, no I/O.

Run (from services/worker with PATH refresh):
    uv run pytest tests/unit/test_video_map.py -q
"""

from __future__ import annotations

from app.editor.video_map import parse_video_map
from app.models import Segment, VideoMap

# ─── helpers ─────────────────────────────────────────────────────────────────


def _seg(start: float, end: float, idx: int = 0) -> Segment:
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
    # pass something that is not a dict at all — handled gracefully
    # parse_video_map expects dict; we simulate by passing something weird
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
