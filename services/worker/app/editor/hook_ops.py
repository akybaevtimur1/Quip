"""Регенерация хука клипа под текущий интервал (общее ядро — W4 endpoint + W3 агент-тул).

Не сохраняет: возвращает НОВЫЙ ClipEdit + текст хука, save делает вызыватель (optimistic-lock).
Меняет ТОЛЬКО hook.text (+enabled) — стиль/позиция хука (W5) и субтитры не тронуты.
"""

from __future__ import annotations

from app import artifacts
from app.editor.replies import clip_words
from app.errors import JobError
from app.models import ClipEdit, HookOverlay
from app.pipeline.stage2_select import regenerate_hook


def regenerate_hook_for_clip(
    job_id: str, edit: ClipEdit, *, style_hint: str | None = None
) -> tuple[ClipEdit, str]:
    """Узкий Gemini-реген хука под интервал `edit`. → (новый ClipEdit, hook_text). JobError, если
    в клипе нет слов (нечего хукать) или Gemini не смог."""
    tr = artifacts.load_transcript(job_id)
    cw = clip_words(tr.words, edit.source_intervals)
    if not cw:
        raise JobError("hook_regen", "clip has no words to base a hook on")
    clip_text = " ".join(w.text for _i, w in cw)
    duration = sum(iv.source_end - iv.source_start for iv in edit.source_intervals)
    hook_text, _style = regenerate_hook(
        clip_text, language=tr.language, duration=duration, style_hint=style_hint
    )
    cur = edit.captions.hook
    new_hook = (
        cur.model_copy(update={"text": hook_text, "enabled": True})
        if cur is not None
        else HookOverlay(text=hook_text, enabled=True)
    )
    new_track = edit.captions.model_copy(update={"hook": new_hook})
    return edit.model_copy(update={"captions": new_track}), hook_text
