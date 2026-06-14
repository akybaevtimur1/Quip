"""PURE edit operations on ClipEdit. No I/O, no side effects."""

from __future__ import annotations

from app.editor.replies import rebuild_replies
from app.errors import JobError
from app.models import (
    CaptionReply,
    ClipEdit,
    CropOverride,
    SourceInterval,
    Word,
)

_STAGE = "editor"


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
    if not word_indices:
        raise JobError(_STAGE, "trim: пустой список слов")
    if any(i < 0 or i >= len(words) for i in word_indices):
        raise JobError(_STAGE, "trim: индекс слова вне диапазона транскрипта")
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
    if source_end <= source_start:
        raise JobError(_STAGE, "add-section: source_end должен быть больше source_start")
    # Пересечение с существующим интервалом → дублирование слов в rebuild_replies
    # (одно слово попадёт в 2 интервала) и поломка тайм-мапа. Запрещаем (правило №8).
    if any(
        source_start < iv.source_end and iv.source_start < source_end
        for iv in edit.source_intervals
    ):
        raise JobError(_STAGE, "add-section: новый интервал пересекает существующий")
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
    if edge not in ("start", "end"):
        raise JobError(_STAGE, f"extend: неизвестный край {edge!r} (ожидался 'start'|'end')")
    if not edit.source_intervals:
        raise JobError(_STAGE, "extend: нет интервалов")
    intervals = list(edit.source_intervals)
    if edge == "start":
        iv = intervals[0]
        if new_value >= iv.source_end:
            raise JobError(_STAGE, "extend: новый старт должен быть меньше конца интервала")
        intervals[0] = SourceInterval(source_start=new_value, source_end=iv.source_end)
    else:
        iv = intervals[-1]
        if new_value <= iv.source_start:
            raise JobError(_STAGE, "extend: новый конец должен быть больше старта интервала")
        intervals[-1] = SourceInterval(source_start=iv.source_start, source_end=new_value)
    return _with_intervals(edit, intervals, words)


def clamp_interval(
    source_start: float,
    source_end: float,
    *,
    duration: float,
    min_sec: float,
    max_sec: float,
) -> tuple[float, float]:
    """PURE. Загнать [start,end] в [0,duration] и в длину [min_sec,max_sec].

    Используется таймлайном (двигать/resize шортс). Если источник короче min_sec —
    окно = весь источник. Гарантирует start<end и валидную длину.
    """
    s = max(0.0, min(float(source_start), duration))
    e = max(0.0, min(float(source_end), duration))
    if e <= s:
        e = s
    length = e - s
    if length < min_sec:
        e = s + min_sec
        if e > duration:
            e = duration
            s = max(0.0, e - min_sec)
    elif length > max_sec:
        e = s + max_sec
    return s, e


def set_interval(
    edit: ClipEdit,
    source_start: float,
    source_end: float,
    words: list[Word],
    *,
    duration: float,
    min_sec: float,
    max_sec: float,
) -> ClipEdit:
    """Заменить интервалы клипа ОДНИМ окном [start,end] (двигать/resize на таймлайне).

    Границы клампятся (clamp_interval). Trim-дырки сбрасываются (блок на таймлайне = один
    непрерывный кусок; вырезание слов делается ПОСЛЕ позиционирования). Реплики пересобираются.
    """
    s, e = clamp_interval(
        source_start, source_end, duration=duration, min_sec=min_sec, max_sec=max_sec
    )
    return _with_intervals(edit, [SourceInterval(source_start=s, source_end=e)], words)


def set_crop_override(edit: ClipEdit, override: CropOverride) -> ClipEdit:
    """Replace any overlapping crop overrides with the new one."""
    kept = [
        ov
        for ov in edit.reframe_overrides
        if ov.source_end <= override.source_start or ov.source_start >= override.source_end
    ]
    return edit.model_copy(update={"reframe_overrides": kept + [override]})


def clear_crop_overrides(edit: ClipEdit, source_start: float, source_end: float) -> ClipEdit:
    """Убрать все overrides, пересекающие диапазон → вернуть авто-reframe (mode=\"auto\" в UI)."""
    kept = [
        ov
        for ov in edit.reframe_overrides
        if ov.source_end <= source_start or ov.source_start >= source_end
    ]
    return edit.model_copy(update={"reframe_overrides": kept})
