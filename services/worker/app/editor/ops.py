"""PURE edit operations on ClipEdit. No I/O, no side effects."""

from __future__ import annotations

from app.editor.replies import rebuild_replies
from app.models import (
    CaptionReply,
    ClipEdit,
    CropOverride,
    SourceInterval,
    Word,
)


def _subtract_range(intervals: list[SourceInterval], rs: float, re: float) -> list[SourceInterval]:
    """Return intervals with the half-open range [rs, re) punched out."""
    result: list[SourceInterval] = []
    for iv in intervals:
        if iv.source_end <= rs or iv.source_start >= re:
            result.append(iv)
        else:
            if iv.source_start < rs:
                result.append(SourceInterval(source_start=iv.source_start, source_end=rs))
            if iv.source_end > re:
                result.append(SourceInterval(source_start=re, source_end=iv.source_end))
    return result


def _with_intervals(
    edit: ClipEdit,
    intervals: list[SourceInterval],
    words: list[Word],
    keep: list[CaptionReply] | None = None,
) -> ClipEdit:
    replies = rebuild_replies(words, intervals, keep=keep or edit.captions.replies)
    new_track = edit.captions.model_copy(update={"replies": replies})
    return edit.model_copy(update={"source_intervals": intervals, "captions": new_track})


def apply_trim(edit: ClipEdit, word_indices: list[int], words: list[Word]) -> ClipEdit:
    """Cut out the time span covering the given word indices."""
    rs = min(words[i].start for i in word_indices)
    re = max(words[i].end for i in word_indices)
    new_intervals = _subtract_range(edit.source_intervals, rs, re)
    return _with_intervals(edit, new_intervals, words)


def add_section(
    edit: ClipEdit,
    source_start: float,
    source_end: float,
    at_index: int,
    words: list[Word],
) -> ClipEdit:
    """Insert a new source interval at position at_index."""
    new_iv = SourceInterval(source_start=source_start, source_end=source_end)
    new_intervals = list(edit.source_intervals)
    new_intervals.insert(at_index, new_iv)
    return _with_intervals(edit, new_intervals, words)


def apply_extend(
    edit: ClipEdit,
    *,
    edge: str,
    new_value: float,
    words: list[Word],
) -> ClipEdit:
    """Grow (or shrink) the start or end of the clip."""
    intervals = list(edit.source_intervals)
    if edge == "start":
        iv = intervals[0]
        intervals[0] = SourceInterval(source_start=new_value, source_end=iv.source_end)
    else:
        iv = intervals[-1]
        intervals[-1] = SourceInterval(source_start=iv.source_start, source_end=new_value)
    return _with_intervals(edit, intervals, words)


def set_crop_override(edit: ClipEdit, override: CropOverride) -> ClipEdit:
    """Replace any overlapping crop overrides with the new one."""
    kept = [
        ov
        for ov in edit.reframe_overrides
        if ov.source_end <= override.source_start or ov.source_start >= override.source_end
    ]
    return edit.model_copy(update={"reframe_overrides": kept + [override]})
