"""Persist-at-select: clip metadata must be on the wire (empty video_url) right after select,
in the SAME order the render fan-out uses, so set_clip_ready(idx) stays aligned. PURE."""

from app.models import ClipType, Segment, Word
from app.run import build_clip_out


def _seg(start: float, end: float, *, reason: str = "r", score: float = 0.5) -> Segment:
    return Segment(start=start, end=end, reason=reason, score=score, type=ClipType.hook)


def _words() -> list[Word]:
    return [Word(text="a", start=0.0, end=0.1), Word(text="b", start=10.0, end=10.1)]


def test_build_clip_out_pending_has_metadata_empty_video_url() -> None:
    c = build_clip_out("clip_03", _seg(1.0, 3.0, reason="why", score=0.7), _words(), "")
    assert c.id == "clip_03"
    assert c.video_url == ""  # pending = no rendered file yet
    assert c.reason == "why"
    assert c.score == 0.7
    assert c.duration == 2.0


def test_clip_ids_are_1based_in_segment_order() -> None:
    # The render fan-out builds clips from the SAME `segments` list in this order; persisting at
    # select must produce identical ids/order so set_clip_ready(idx) targets the right clip.
    segs = [_seg(0, 2), _seg(5, 7), _seg(9, 11)]
    ids = [build_clip_out(f"clip_{i:02d}", s, _words(), "").id for i, s in enumerate(segs, start=1)]
    assert ids == ["clip_01", "clip_02", "clip_03"]
