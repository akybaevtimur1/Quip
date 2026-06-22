"""Сборка TimelineData для таймлайн-редактора (спека §B1). PURE.

Из готовых артефактов (meta/segments/transcript) строит данные таймлайна: ВСЕ кандидаты
ИИ как маркеры + пословный транскрипт для hover. Дорогих ИИ-вызовов НЕТ.
"""

from __future__ import annotations

from app.models import Segment, TimelineData, TimelineSegment, Word


def build_timeline_data(
    duration: float, segments: list[Segment], words: list[Word]
) -> TimelineData:
    """meta-длительность + сегменты + слова → TimelineData. PURE.

    `clip_id`=None для каждого маркера (привязка к клипу — задача фронта/будущего).
    """
    markers = [
        TimelineSegment(
            clip_id=None,
            start=seg.start,
            end=seg.end,
            type=seg.type,
            score=seg.score,
            reason=seg.reason,
            hook=seg.hook,
            why_works=seg.why_works,
        )
        for seg in segments
    ]
    return TimelineData(duration=duration, segments=markers, words=words)
