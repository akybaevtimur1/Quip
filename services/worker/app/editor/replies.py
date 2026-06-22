"""Сборка реплик субтитров из слов и интервалов (спека §4.1, §7). PURE.

rebuild_replies — единственное место синхронизации субтитров с интервалами:
структурная правка интервалов → перегруппировать слова в интервалах.
Переиспользует group_words_into_chunks (правила группировки не дублируем).
"""

from __future__ import annotations

from typing import Any

from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    HighlightStyle,
    HookOverlay,
    SourceInterval,
    Word,
)
from app.pipeline.stage4_captions import group_words_into_chunks


def clip_words(all_words: list[Word], intervals: list[SourceInterval]) -> list[tuple[int, Word]]:
    """PURE. (индекс_в_all_words, слово) для слов внутри интервалов, в clip-порядке (по
    порядку интервалов; внутри интервала — по возрастанию = source-порядок). Единая точка
    отбора слов клипа: переиспользуется субтитрами (rebuild_replies) и хук-регеном (W4)."""
    selected: list[tuple[int, Word]] = []
    for iv in intervals:  # clip-порядок интервалов
        for i, w in enumerate(all_words):  # внутри — по возрастанию (= source-порядок)
            if iv.source_start <= w.start < iv.source_end:
                selected.append((i, w))
    return selected


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
    selected = clip_words(all_words, intervals)
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


def default_caption_track(
    all_words: list[Word],
    intervals: list[SourceInterval],
    *,
    hook: str | None = None,
    pref_style: CaptionStyle | None = None,
    pref_highlight: HighlightStyle | None = None,
    pref_hook_look: dict[str, Any] | None = None,
) -> CaptionTrack:
    """Дефолтный трек: стиль = сид-пресет A («Караоке-бокс», коралловая подсветка).

    Раньше брались голые дефолты моделей (HighlightStyle → жёлтый #FFE000) —
    дефолт расходился с заявленным «дефолт = preset A» (фидбек фаундера).

    Domain 5: если у владельца джобы СОХРАНЁН дефолт-стиль (pref_*), сидим из НЕГО, а не из
    preset A — так новые видео стартуют со стиля юзера (подстройка под его вкус). pref_* уже
    провалидированы вызывающим (ensure_edit), None = нет сохранённого стиля → preset A.

    hook (T1) — текст топ-заголовка от Gemini: задан → сидим включённый HookOverlay
    (бренд-плашка по дефолту); None/пусто → без хука (track.hook = None).
    """
    from app.editor.preset_seeds import DEFAULT_PRESET_ID, seed_presets

    if pref_style is not None:
        style = pref_style.model_copy()
        highlight = pref_highlight.model_copy() if pref_highlight is not None else None
    else:
        default = next(p for p in seed_presets() if p.id == DEFAULT_PRESET_ID)
        style = default.style.model_copy()
        highlight = default.highlight.model_copy() if default.highlight else None
    hook_overlay = HookOverlay(text=hook, enabled=True) if hook and hook.strip() else None
    if hook_overlay is not None and pref_hook_look:
        from app.editor.style_prefs import HOOK_LOOK_FIELDS

        look = {k: pref_hook_look[k] for k in HOOK_LOOK_FIELDS if k in pref_hook_look}
        hook_overlay = hook_overlay.model_copy(update=look)
    return CaptionTrack(
        style=style,
        highlight=highlight,
        replies=rebuild_replies(all_words, intervals),
        hook=hook_overlay,
    )
