"""W3: тулзы агента над edit-state клипа. Тонкие обёртки над ops/hook_ops/render.

Границы (см. дизайн §8): НЕТ тулзов на субтитры и reframe. Каждый тул читает СВЕЖИЙ edit-state,
применяет pure-операцию, сохраняет с optimistic-lock (ретрай 1 раз на EditConflict — параллельная
ручная правка). Ошибка → возвращаем {"error": …} (НЕ исключение): луп отдаёт её модели, та
исправляется/сообщает (правило №8 — видимо, не молча).
"""

from __future__ import annotations

from typing import Any

from app import artifacts
from app.editor import store
from app.editor.store import EditConflict
from app.errors import JobError
from app.models import ClipEdit, HookOverlay, Word

# Ограничители для get_surrounding_transcript (защита контекста модели).
_SURROUND_DEFAULT_SEC = 30.0
_SURROUND_MAX_SEC = 90.0
_SURROUND_MAX_WORDS = 400

# ─────────────────────────── pure helpers ───────────────────────────


def compute_nudge(start: float, end: float, edge: str, delta: float) -> tuple[float, float]:
    """PURE. Сдвинуть один край интервала на delta (может быть отрицательным). Кламп — потом."""
    if edge == "start":
        return (start + delta, end)
    if edge == "end":
        return (start, end + delta)
    raise ValueError(f"edge must be 'start'|'end', got {edge!r}")


def words_in_window(
    words: list[Word], start: float, end: float, max_words: int
) -> list[dict[str, Any]]:
    """PURE. Слова транскрипта, пересекающие окно [start, end] (source-секунды).

    Слово включается, если его [w.start, w.end] пересекает окно (w.end >= start AND
    w.start <= end). Возвращает <= max_words ПЕРВЫХ слов (по порядку транскрипта) как
    {"text", "start", "end"} с округлением до 0.01с — компактный контекст для модели.
    """
    out: list[dict[str, Any]] = []
    for w in words:
        if w.end >= start and w.start <= end:
            out.append({"text": w.text, "start": round(w.start, 2), "end": round(w.end, 2)})
            if len(out) >= max_words:
                break
    return out


def _outer(edit: ClipEdit) -> tuple[float, float]:
    """Внешние границы клипа (start первого интервала, end последнего)."""
    ivs = edit.source_intervals
    return ivs[0].source_start, ivs[-1].source_end


def _ival_str(edit: ClipEdit) -> str:
    s, e = _outer(edit)
    return f"{s:.1f}-{e:.1f}s"


def _mutate(job_id: str, clip_id: str, fn: Any) -> ClipEdit:
    """Load → fn(edit)→new → save (optimistic-lock). Ретрай 1 раз на EditConflict (сц. №6)."""
    last: EditConflict | None = None
    for _ in range(2):
        edit = store.ensure_edit(job_id, clip_id)
        new = fn(edit)  # может бросить JobError (валидация ops)
        try:
            return store.save_edit(job_id, clip_id, new, expected_version=edit.version)
        except EditConflict as e:
            last = e
    assert last is not None
    raise last


# ─────────────────────────── состояние клипа (контекст + тул) ───────────────────────────


def clip_state(job_id: str, clip_id: str) -> dict[str, Any]:
    """Текущее состояние клипа для агента: интервал, длина, транскрипт клипа, хук, лимиты."""
    from app.config import get_settings
    from app.editor.replies import clip_words

    s = get_settings()
    edit = store.ensure_edit(job_id, clip_id)
    tr = artifacts.load_transcript(job_id)
    meta = artifacts.load_meta(job_id)
    cw = clip_words(tr.words, edit.source_intervals)
    start, end = _outer(edit)
    hook = edit.captions.hook
    return {
        "interval": [round(start, 2), round(end, 2)],
        "clip_seconds": round(end - start, 2),
        "source_seconds": round(meta.duration, 2),
        "language": tr.language,
        "transcript": " ".join(w.text for _i, w in cw),
        "hook": (hook.text if hook and hook.enabled else None),
        "min_clip_seconds": s.clip_min_sec,
        "max_clip_seconds": s.clip_max_sec,
    }


# ─────────────────────────── тулзы (мутации) ───────────────────────────


def _t_set_interval(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    from app.config import get_settings
    from app.editor.ops import set_interval

    try:
        start = float(args["start_sec"])
        end = float(args["end_sec"])
    except (KeyError, TypeError, ValueError):
        return {"error": "set_interval requires numeric start_sec and end_sec"}
    words = store.load_transcript_words(job_id)
    meta = artifacts.load_meta(job_id)
    s = get_settings()
    before: str | None = None

    def fn(edit: ClipEdit) -> ClipEdit:
        nonlocal before
        before = _ival_str(edit)
        return set_interval(
            edit, start, end, words,
            duration=meta.duration, min_sec=s.clip_min_sec, max_sec=s.clip_max_sec,
        )  # fmt: skip

    try:
        saved = _mutate(job_id, clip_id, fn)
    except JobError as e:
        return {"error": str(e)}
    after = _ival_str(saved)
    clamped = ""
    if after != f"{start:.1f}-{end:.1f}s":
        clamped = " (clamped to limits/source)"
    return {"ok": True, "summary": f"interval {before} → {after}{clamped}", "before": before,
            "after": after}  # fmt: skip


def _t_nudge(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    edge = str(args.get("edge", ""))
    if edge not in ("start", "end"):
        return {"error": "nudge_interval edge must be 'start' or 'end'"}
    try:
        delta = float(args["delta_sec"])
    except (KeyError, TypeError, ValueError):
        return {"error": "nudge_interval requires numeric delta_sec"}
    edit = store.ensure_edit(job_id, clip_id)
    start, end = _outer(edit)
    ns, ne = compute_nudge(start, end, edge, delta)
    return _t_set_interval(job_id, clip_id, {"start_sec": ns, "end_sec": ne})


def _t_regenerate_hook(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    from app.editor.hook_ops import regenerate_hook_for_clip

    style = args.get("style_hint")
    style_s = str(style) if style else None
    before: str | None = None

    def fn(edit: ClipEdit) -> ClipEdit:
        nonlocal before
        before = edit.captions.hook.text if edit.captions.hook else None
        new_edit, _txt = regenerate_hook_for_clip(job_id, edit, style_hint=style_s)
        return new_edit

    try:
        saved = _mutate(job_id, clip_id, fn)
    except JobError as e:
        return {"error": str(e)}
    after = saved.captions.hook.text if saved.captions.hook else None
    return {"ok": True, "summary": f"hook → {after!r}", "before": before, "after": after}


def _t_set_hook_text(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text", "")).strip()
    if not text:
        return {"error": "set_hook_text requires non-empty text"}

    def fn(edit: ClipEdit) -> ClipEdit:
        cur = edit.captions.hook
        nh = (
            cur.model_copy(update={"text": text, "enabled": True})
            if cur is not None
            else HookOverlay(text=text, enabled=True)
        )
        return edit.model_copy(update={"captions": edit.captions.model_copy(update={"hook": nh})})

    saved = _mutate(job_id, clip_id, fn)
    after = saved.captions.hook.text if saved.captions.hook else None
    return {"ok": True, "summary": f"hook text set → {after!r}", "after": after}


def _t_request_render(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    from app import db, dispatch

    db.set_render_status(job_id, clip_id, "rendering", None, None)
    if dispatch.modal_spawn_enabled():
        try:
            dispatch.spawn("render_job", job_id, clip_id)
        except Exception as e:  # noqa: BLE001 — сбой диспатча видим (правило №8)
            db.set_render_status(job_id, clip_id, "failed", None, f"dispatch failed: {e}")
            return {"error": f"render dispatch failed: {e}"}
    else:
        from app.tasks import render_clip_edit_job

        render_clip_edit_job(job_id, clip_id)
    return {"ok": True, "summary": "re-render started"}


def _t_get_clip_state(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **clip_state(job_id, clip_id)}


def _t_get_surrounding_transcript(
    job_id: str, clip_id: str, args: dict[str, Any]
) -> dict[str, Any]:
    """Транскрипт ВОКРУГ клипа (с source-таймстемпами) — чтобы агент выбрал чистые точки реза."""
    try:
        sec = float(args.get("seconds_around", _SURROUND_DEFAULT_SEC))
    except (TypeError, ValueError):
        return {"error": "get_surrounding_transcript: seconds_around must be a number"}
    sec = max(0.0, min(sec, _SURROUND_MAX_SEC))

    edit = store.ensure_edit(job_id, clip_id)
    tr = artifacts.load_transcript(job_id)
    start, end = _outer(edit)
    win_start = max(0.0, start - sec)
    win_end = min(tr.duration, end + sec)
    words = words_in_window(tr.words, win_start, win_end, _SURROUND_MAX_WORDS)
    return {
        "ok": True,
        "interval": [round(start, 2), round(end, 2)],
        "window": [round(win_start, 2), round(win_end, 2)],
        "language": tr.language,
        "words": words,
        "note": (
            "These are SOURCE-second timestamps around the clip. Pick clean start/end on sentence "
            "boundaries (after a full stop / pause), then call set_interval with those seconds."
        ),
    }


_DISPATCH = {
    "get_clip_state": _t_get_clip_state,
    "get_surrounding_transcript": _t_get_surrounding_transcript,
    "set_interval": _t_set_interval,
    "nudge_interval": _t_nudge,
    "regenerate_hook": _t_regenerate_hook,
    "set_hook_text": _t_set_hook_text,
    "request_render": _t_request_render,
}


def apply_tool(name: str, args: dict[str, Any], *, job_id: str, clip_id: str) -> dict[str, Any]:
    """Выполнить тул по имени. Неизвестный тул / ошибка → {"error": …} (не исключение)."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(job_id, clip_id, args)
    except EditConflict:
        return {"error": "clip changed concurrently — re-read state with get_clip_state"}
    except (FileNotFoundError, KeyError, JobError) as e:
        return {"error": str(e)}
