"""W3: тулзы агента над edit-state клипа. Тонкие обёртки над ops/hook_ops/render.

Границы (см. дизайн §8): НЕТ тулзов на субтитры и reframe. Каждый тул читает СВЕЖИЙ edit-state,
применяет pure-операцию, сохраняет с optimistic-lock (ретрай 1 раз на EditConflict — параллельная
ручная правка). Ошибка → возвращаем {"error": …} (НЕ исключение): луп отдаёт её модели, та
исправляется/сообщает (правило №8 — видимо, не молча).
"""

from __future__ import annotations

import logging
from typing import Any

from app import artifacts
from app.editor import store
from app.editor.store import EditConflict
from app.errors import JobError
from app.models import (
    CaptionStyle,
    CaptionTrack,
    ClipEdit,
    CropOverride,
    HighlightStyle,
    HookOverlay,
    Word,
)

_log = logging.getLogger("clipflow.agent")
_STAGE_AGENT = "agent"

# Ограничители для get_surrounding_transcript (защита контекста модели).
_SURROUND_DEFAULT_SEC = 30.0
_SURROUND_MAX_SEC = 90.0
_SURROUND_MAX_WORDS = 400

# Допустимые соотношения сторон (зеркало UI FrameTab).
_ALLOWED_ASPECTS = ("9:16", "1:1", "4:5", "16:9")
# Лейблы режимов кадра в терминах юзера (для summary тулзов).
_CROP_LABEL = {"fill": "Tight", "fit": "Wide", "split": "Split", "auto": "Auto"}

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
    {"i", "text", "start", "end"} — где `i` = ГЛОБАЛЬНЫЙ индекс слова в `words` (нужен
    тулзе trim_words). Тайминги округлены до 0.01с — компактный контекст для модели.
    """
    out: list[dict[str, Any]] = []
    for i, w in enumerate(words):
        if w.end >= start and w.start <= end:
            out.append({"i": i, "text": w.text, "start": round(w.start, 2), "end": round(w.end, 2)})
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
    """Полное состояние клипа для агента: интервал(ы), длина, транскрипт + индексы слов,
    хук, СТИЛЬ субтитров/хука, караоке, burn, aspect, лимиты. Достаточно, чтобы агент
    точечно правил ЛЮБОЙ аспект клипа, не угадывая текущие значения."""
    from app.config import get_settings
    from app.editor.replies import clip_words

    s = get_settings()
    edit = store.ensure_edit(job_id, clip_id)
    tr = artifacts.load_transcript(job_id)
    meta = artifacts.load_meta(job_id)
    cw = clip_words(tr.words, edit.source_intervals)
    start, end = _outer(edit)
    cap = edit.captions
    st = cap.style
    hl = cap.highlight
    hook = cap.hook
    return {
        "interval": [round(start, 2), round(end, 2)],
        # ВСЕ интервалы (после trim/montage клип может быть несколькими кусками source).
        "source_intervals": [
            [round(iv.source_start, 2), round(iv.source_end, 2)] for iv in edit.source_intervals
        ],
        "clip_seconds": round(end - start, 2),
        "source_seconds": round(meta.duration, 2),
        "language": tr.language,
        "transcript": " ".join(w.text for _i, w in cw),
        # Слова клипа с ГЛОБАЛЬНЫМ индексом в transcript.words → для trim_words (вырезать слова).
        "words": [{"i": gi, "text": w.text} for gi, w in cw],
        "aspect": edit.aspect,
        "captions_burned": cap.burn,  # True = накладываем наши субтитры; False = видео уже с ними
        "caption_style": {
            "font": st.font,
            "size": st.size,
            "color": st.color,
            "outline_color": st.outline_color,
            "outline_w": st.outline_w,
            "box_color": st.box_color,
            "box_opacity": st.box_opacity,
            "margin_v": st.margin_v,
            "uppercase": st.uppercase,
            "emphasis_color": st.emphasis_color,
        },
        "highlight": (
            None if hl is None else {"animation": hl.animation, "color": hl.color, "box": hl.box}
        ),
        # `hook` stays the TEXT (build_system_prompt + back-compat); full look = `hook_style`.
        "hook": (hook.text if hook and hook.enabled else None),
        "hook_style": {
            "enabled": hook.enabled,
            "full_clip": hook.full_clip,
            "duration_sec": hook.duration_sec,
            "font": hook.font,
            "size": hook.size,
            "color": hook.color,
            "box_color": hook.box_color,
            "animation": hook.animation,
            "uppercase": hook.uppercase,
        }
        if hook is not None
        else None,
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
    from app.editor.video_map import load_video_map

    style = args.get("style_hint")
    style_s = str(style) if style else None

    # Pass whole-video context to hook generation when available (optional, backwards-compatible).
    video_summary: str | None = None
    try:
        vm = load_video_map(job_id)
        if vm is not None and vm.status == "done":
            compact = _compact_video_map_summary(vm)
            narrative = compact.get("narrative", "")
            if narrative:
                video_summary = narrative
    except Exception as e:  # noqa: BLE001 — video map is optional; never block hook regen
        # Rule #8: don't swallow silently — log so a broken map/load is visible, but
        # degrade gracefully (hook regen proceeds without whole-video context).
        _log.warning("get_video_map for hook context failed (job=%s): %s", job_id, e)

    before: str | None = None

    def fn(edit: ClipEdit) -> ClipEdit:
        nonlocal before
        before = edit.captions.hook.text if edit.captions.hook else None
        new_edit, _txt = regenerate_hook_for_clip(
            job_id, edit, style_hint=style_s, video_summary=video_summary
        )
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


# ── compact video-map helpers ──────────────────────────────────────────────────────────────────

_NARRATIVE_TRUNCATE = 600  # chars; keep compact to avoid context bloat


def _fmt_mmss(sec: float) -> str:
    """Format seconds as mm:ss string."""
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def _compact_video_map_summary(vm: Any) -> dict[str, Any]:
    """Return a compact agent-readable dict from a VideoMap (status='done')."""

    narrative = vm.narrative or ""
    if len(narrative) > _NARRATIVE_TRUNCATE:
        narrative = narrative[:_NARRATIVE_TRUNCATE] + "…"

    chapters_out = []
    for ch in vm.chapters:
        moment_labels = [m.label for m in ch.moments if m.label]
        chapters_out.append(
            {
                "range": f"{_fmt_mmss(ch.start)}–{_fmt_mmss(ch.end)}",
                "title": ch.title,
                "summary": ch.summary,
                "moment_labels": moment_labels,
                "clip_ids": ch.clip_ids,
            }
        )

    return {
        "ok": True,
        "status": "done",
        "narrative": narrative,
        "chapters": chapters_out,
    }


def _t_get_video_map(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Возвращает компактный обзор всего видео (narrative + chapters). Без аргументов."""
    from app.editor.video_map import load_video_map

    vm = load_video_map(job_id)
    if vm is None:
        return {
            "ok": False,
            "status": "not_available",
            "note": "Video map has not been generated yet for this job.",
        }
    if vm.status == "pending":
        return {
            "ok": False,
            "status": "pending",
            "note": "Video map is still being generated — try again shortly.",
        }
    if vm.status == "failed":
        return {
            "ok": False,
            "status": "failed",
            "error": vm.error or "video map generation failed",
        }
    # status == "done"
    return _compact_video_map_summary(vm)


# ─────────────────────────── монтаж (trim / montage / extend) ───────────────────────────


def _t_trim_words(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Вырезать из клипа диапазон слов (по ГЛОБАЛЬНЫМ индексам из get_clip_state.words)."""
    from app.editor.ops import apply_trim

    raw = args.get("word_indices")
    if not isinstance(raw, list) or not raw:
        return {
            "error": "trim_words requires a non-empty word_indices list "
            "(global indices from get_clip_state.words)"
        }
    try:
        idx = [int(i) for i in raw]
    except (TypeError, ValueError):
        return {"error": "trim_words: word_indices must be integers"}
    words = store.load_transcript_words(job_id)
    before: str | None = None

    def fn(edit: ClipEdit) -> ClipEdit:
        nonlocal before
        before = _ival_str(edit)
        return apply_trim(edit, idx, words)

    try:
        saved = _mutate(job_id, clip_id, fn)
    except JobError as e:
        return {"error": str(e)}
    return {
        "ok": True,
        "summary": f"cut {len(idx)} word(s); interval {before} → {_ival_str(saved)}",
    }


def _t_add_section(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Вставить НЕсмежный кусок source в клип (монтаж из другого места видео)."""
    from app.editor.ops import add_section

    try:
        ss = float(args["source_start"])
        se = float(args["source_end"])
    except (KeyError, TypeError, ValueError):
        return {"error": "add_section requires numeric source_start and source_end"}
    words = store.load_transcript_words(job_id)

    def fn(edit: ClipEdit) -> ClipEdit:
        at = args.get("at_index")
        at_index = int(at) if isinstance(at, (int, float)) else len(edit.source_intervals)
        return add_section(edit, ss, se, at_index, words)

    try:
        saved = _mutate(job_id, clip_id, fn)
    except JobError as e:
        return {"error": str(e)}
    return {"ok": True, "summary": f"added {ss:.1f}-{se:.1f}s; interval now {_ival_str(saved)}"}


def _t_extend_edge(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Передвинуть ОДИН край интервала на точное значение (не схлопывает multi-interval)."""
    from app.editor.ops import apply_extend

    edge = str(args.get("edge", ""))
    if edge not in ("start", "end"):
        return {"error": "extend_edge: edge must be 'start' or 'end'"}
    try:
        nv = float(args["new_value_sec"])
    except (KeyError, TypeError, ValueError):
        return {"error": "extend_edge requires numeric new_value_sec"}
    words = store.load_transcript_words(job_id)
    before: str | None = None

    def fn(edit: ClipEdit) -> ClipEdit:
        nonlocal before
        before = _ival_str(edit)
        return apply_extend(edit, edge=edge, new_value=nv, words=words)

    try:
        saved = _mutate(job_id, clip_id, fn)
    except JobError as e:
        return {"error": str(e)}
    return {"ok": True, "summary": f"interval {before} → {_ival_str(saved)}"}


# ─────────────────────────── стиль субтитров / хука / пресеты ───────────────────────────

_STYLE_STR_FIELDS = ("font", "color", "outline_color")
_STYLE_INT_FIELDS = ("size", "outline_w", "shadow", "margin_v", "box_radius")
_HOOK_STR_FIELDS = ("font", "color", "outline_color")
_HOOK_INT_FIELDS = ("size", "outline_w", "shadow", "margin_v")


def _apply_caption_style(captions: CaptionTrack, args: dict[str, Any]) -> CaptionTrack:
    """PURE-ish: построить новый CaptionTrack из частичного патча стиля/караоке. Невалидные
    значения (плохой enum-animation/цвет/диапазон) поднимают ValidationError → тул вернёт error."""
    style_patch: dict[str, Any] = {}
    for k in _STYLE_STR_FIELDS:
        if args.get(k) is not None:
            style_patch[k] = str(args[k])
    for k in _STYLE_INT_FIELDS:
        if args.get(k) is not None:
            style_patch[k] = int(args[k])
    if "uppercase" in args:
        style_patch["uppercase"] = bool(args["uppercase"])
    if "box_color" in args:
        v = args["box_color"]
        style_patch["box_color"] = None if v in (None, "none", "") else str(v)
    if "box_opacity" in args and args["box_opacity"] is not None:
        style_patch["box_opacity"] = float(args["box_opacity"])
    if "emphasis_color" in args:
        v = args["emphasis_color"]
        style_patch["emphasis_color"] = None if v in (None, "none", "") else str(v)

    hl_patch: dict[str, Any] = {}
    if args.get("highlight_animation") is not None:
        hl_patch["animation"] = str(args["highlight_animation"])
    if args.get("highlight_color") is not None:
        hl_patch["color"] = str(args["highlight_color"])

    if not style_patch and not hl_patch and not args.get("highlight_off"):
        raise JobError(_STAGE_AGENT, "set_caption_style: no recognized fields to change")

    new_style = captions.style
    if style_patch:
        new_style = CaptionStyle.model_validate(
            captions.style.model_copy(update=style_patch).model_dump()
        )

    new_hl = captions.highlight
    if args.get("highlight_off"):
        new_hl = None
    elif hl_patch:
        base = captions.highlight or HighlightStyle()
        new_hl = HighlightStyle.model_validate(base.model_copy(update=hl_patch).model_dump())

    return captions.model_copy(update={"style": new_style, "highlight": new_hl})


def _t_set_caption_style(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Частично изменить ВИД субтитров (шрифт/размер/цвет/обводка/позиция/uppercase/караоке)."""
    from pydantic import ValidationError

    def fn(edit: ClipEdit) -> ClipEdit:
        return edit.model_copy(update={"captions": _apply_caption_style(edit.captions, args)})

    try:
        _mutate(job_id, clip_id, fn)
    except (JobError, ValidationError, ValueError, TypeError) as e:
        return {"error": f"set_caption_style: {e}"}
    return {"ok": True, "summary": "caption style updated"}


def _t_set_hook_style(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Частично изменить ВИД хука (шрифт/размер/цвет/плашка/анимация/позиция/тайминг)."""
    from pydantic import ValidationError

    def fn(edit: ClipEdit) -> ClipEdit:
        hook = edit.captions.hook
        if hook is None:
            raise JobError(
                _STAGE_AGENT, "no hook to style — set the hook text first (set_hook_text)"
            )
        patch: dict[str, Any] = {}
        for k in _HOOK_STR_FIELDS:
            if args.get(k) is not None:
                patch[k] = str(args[k])
        for k in _HOOK_INT_FIELDS:
            if args.get(k) is not None:
                patch[k] = int(args[k])
        if "uppercase" in args:
            patch["uppercase"] = bool(args["uppercase"])
        if args.get("animation") is not None:
            patch["animation"] = str(args["animation"])
        if "box_color" in args:
            v = args["box_color"]
            patch["box_color"] = None if v in (None, "none", "") else str(v)
        if "box_opacity" in args and args["box_opacity"] is not None:
            patch["box_opacity"] = float(args["box_opacity"])
        if "full_clip" in args:
            patch["full_clip"] = bool(args["full_clip"])
        if args.get("duration_sec") is not None:
            patch["duration_sec"] = float(args["duration_sec"])
        if not patch:
            raise JobError(_STAGE_AGENT, "set_hook_style: no recognized fields to change")
        new_hook = HookOverlay.model_validate(hook.model_copy(update=patch).model_dump())
        return edit.model_copy(
            update={"captions": edit.captions.model_copy(update={"hook": new_hook})}
        )

    try:
        _mutate(job_id, clip_id, fn)
    except (JobError, ValidationError, ValueError, TypeError) as e:
        return {"error": f"set_hook_style: {e}"}
    return {"ok": True, "summary": "hook style updated"}


def _t_list_presets(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Список доступных caption-пресетов (id + name) для apply_preset."""
    from app.editor.presets import list_presets

    return {"ok": True, "presets": [{"id": p.id, "name": p.name} for p in list_presets()]}


def _t_apply_preset(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Применить именованный caption-пресет (полный look) по id. Позицию субтитров не сбрасывает."""
    from app.editor.presets import apply_preset, get_preset

    pid = str(args.get("preset_id", "")).strip()
    if not pid:
        return {"error": "apply_preset requires preset_id (call list_presets for valid ids)"}
    preset = get_preset(pid)
    if preset is None:
        return {"error": f"unknown preset_id {pid!r} — call list_presets for valid ids"}

    def fn(edit: ClipEdit) -> ClipEdit:
        return apply_preset(edit, preset)

    try:
        _mutate(job_id, clip_id, fn)
    except JobError as e:
        return {"error": str(e)}
    return {"ok": True, "summary": f"applied preset {pid} ({preset.name})"}


def _t_set_aspect(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Сменить соотношение сторон выхода (9:16 / 1:1 / 4:5 / 16:9)."""
    ar = str(args.get("aspect", "")).strip()
    if ar not in _ALLOWED_ASPECTS:
        return {"error": f"aspect must be one of {', '.join(_ALLOWED_ASPECTS)}"}

    def fn(edit: ClipEdit) -> ClipEdit:
        return edit.model_copy(update={"aspect": ar})

    _mutate(job_id, clip_id, fn)
    return {"ok": True, "summary": f"aspect → {ar}"}


def _t_set_crop(job_id: str, clip_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Форсировать кадр на диапазоне source (Tight/Wide/Split/Auto; дефолт — весь клип)."""
    from app.editor.ops import clear_crop_overrides, set_crop_override

    mode = str(args.get("mode", "")).strip()
    if mode not in ("fill", "fit", "split", "auto"):
        return {"error": "set_crop mode must be one of fill|fit|split|auto"}
    edit0 = store.ensure_edit(job_id, clip_id)
    s0, e0 = _outer(edit0)
    try:
        ss = float(args.get("source_start", s0))
        se = float(args.get("source_end", e0))
    except (TypeError, ValueError):
        return {"error": "set_crop: source_start/source_end must be numbers"}
    if se <= ss:
        return {"error": "set_crop: source_end must be greater than source_start"}
    center = args.get("center")
    center_b = args.get("center_b")

    def fn(edit: ClipEdit) -> ClipEdit:
        if mode == "auto":
            return clear_crop_overrides(edit, ss, se)
        ov = CropOverride(
            source_start=ss,
            source_end=se,
            mode=mode,
            center=float(center) if center is not None else None,
            center_b=float(center_b) if center_b is not None else None,
        )
        return set_crop_override(edit, ov)

    try:
        _mutate(job_id, clip_id, fn)
    except (JobError, ValueError, TypeError) as e:
        return {"error": f"set_crop: {e}"}
    return {"ok": True, "summary": f"crop {_CROP_LABEL[mode]} on {ss:.1f}-{se:.1f}s"}


_DISPATCH = {
    "get_clip_state": _t_get_clip_state,
    "get_surrounding_transcript": _t_get_surrounding_transcript,
    "get_video_map": _t_get_video_map,
    "set_interval": _t_set_interval,
    "nudge_interval": _t_nudge,
    "trim_words": _t_trim_words,
    "add_section": _t_add_section,
    "extend_edge": _t_extend_edge,
    "regenerate_hook": _t_regenerate_hook,
    "set_hook_text": _t_set_hook_text,
    "set_caption_style": _t_set_caption_style,
    "set_hook_style": _t_set_hook_style,
    "list_presets": _t_list_presets,
    "apply_preset": _t_apply_preset,
    "set_aspect": _t_set_aspect,
    "set_crop": _t_set_crop,
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
