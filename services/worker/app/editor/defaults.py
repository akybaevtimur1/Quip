"""Сборка дефолтного ClipEdit из выбранного сегмента (спека §10). PURE."""

from __future__ import annotations

from typing import Any

from app.editor.replies import default_caption_track
from app.models import CaptionStyle, ClipEdit, HighlightStyle, Segment, SourceInterval, Word


def default_clip_edit(
    clip_id: str,
    segment: Segment,
    all_words: list[Word],
    *,
    pref_style: CaptionStyle | None = None,
    pref_highlight: HighlightStyle | None = None,
    pref_hook_look: dict[str, Any] | None = None,
) -> ClipEdit:
    """Сегмент ИИ → дефолтный рецепт: один интервал [start,end], авто-субтитры, без overrides.

    pref_* (domain 5): сохранённый дефолт-стиль владельца джобы → новые клипы стартуют с него
    вместо preset A. None = нет сохранённого стиля.
    """
    intervals = [SourceInterval(source_start=segment.start, source_end=segment.end)]
    return ClipEdit(
        id=clip_id,
        version=1,
        source_intervals=intervals,
        captions=default_caption_track(
            all_words,
            intervals,
            hook=segment.hook,
            pref_style=pref_style,
            pref_highlight=pref_highlight,
            pref_hook_look=pref_hook_look,
        ),
        reframe_overrides=[],
        aspect="9:16",
    )
