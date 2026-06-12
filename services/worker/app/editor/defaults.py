"""Сборка дефолтного ClipEdit из выбранного сегмента (спека §10). PURE."""

from __future__ import annotations

from app.editor.replies import default_caption_track
from app.models import ClipEdit, Segment, SourceInterval, Word


def default_clip_edit(clip_id: str, segment: Segment, all_words: list[Word]) -> ClipEdit:
    """Сегмент ИИ → дефолтный рецепт: один интервал [start,end], авто-субтитры, без overrides."""
    intervals = [SourceInterval(source_start=segment.start, source_end=segment.end)]
    return ClipEdit(
        id=clip_id,
        version=1,
        source_intervals=intervals,
        captions=default_caption_track(all_words, intervals, hook=segment.hook),
        reframe_overrides=[],
        aspect="9:16",
    )
