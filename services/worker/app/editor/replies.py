"""Сборка реплик субтитров из слов и интервалов (спека §4.1, §7). PURE.

rebuild_replies — единственное место синхронизации субтитров с интервалами:
структурная правка интервалов → перегруппировать слова в интервалах.
Переиспользует group_words_into_chunks (правила группировки не дублируем).
"""

from __future__ import annotations

from app.models import (
    CaptionReply,
    CaptionTrack,
    SourceInterval,
    Word,
)
from app.pipeline.stage4_captions import group_words_into_chunks


def rebuild_replies(
    all_words: list[Word],
    intervals: list[SourceInterval],
    *,
    max_words: int = 5,
    max_gap: float = 0.4,
    max_dur: float = 2.5,
    keep: list[CaptionReply] | None = None,
) -> list[CaptionReply]:
    """Перегруппировать слова, попадающие в интервалы (clip-порядок), в реплики.

    word_refs = индексы в all_words. Слова вне интервалов выпадают. keep сохраняет
    text_override/hidden для реплик с НЕизменившимся набором word_refs.
    """
    selected: list[tuple[int, Word]] = []
    for iv in intervals:  # clip-порядок интервалов
        for i, w in enumerate(all_words):  # внутри — по возрастанию (= source-порядок)
            if iv.source_start <= w.start < iv.source_end:
                selected.append((i, w))
    if not selected:
        return []
    chunks = group_words_into_chunks(
        [w for _i, w in selected], max_words=max_words, max_gap=max_gap, max_dur=max_dur
    )
    keyed = {tuple(r.word_refs): r for r in (keep or [])}
    replies: list[CaptionReply] = []
    pos = 0
    for ch in chunks:
        refs = [selected[pos + k][0] for k in range(len(ch.words))]
        pos += len(ch.words)
        prev = keyed.get(tuple(refs))
        replies.append(
            CaptionReply(
                word_refs=refs,
                text_override=prev.text_override if prev else None,
                hidden=prev.hidden if prev else False,
            )
        )
    return replies


def default_caption_track(all_words: list[Word], intervals: list[SourceInterval]) -> CaptionTrack:
    """Дефолтный трек: стиль = сид-пресет A («Караоке-бокс», коралловая подсветка).

    Раньше брались голые дефолты моделей (HighlightStyle → жёлтый #FFE000) —
    дефолт расходился с заявленным «дефолт = preset A» (фидбек фаундера).
    """
    from app.editor.preset_seeds import DEFAULT_PRESET_ID, seed_presets

    default = next(p for p in seed_presets() if p.id == DEFAULT_PRESET_ID)
    return CaptionTrack(
        style=default.style.model_copy(),
        highlight=default.highlight.model_copy() if default.highlight else None,
        replies=rebuild_replies(all_words, intervals),
    )
