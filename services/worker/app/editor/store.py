"""Персистентность ClipEdit: SQLite (локально) или Supabase clip_edits (cloud) — dual-mode.

Источник правды стейта правок — таблица clip_edits (через ``app.db``, которая сама роутит
SQLite/Postgres). Артефакты сегмента (segments/transcript) читаются через ``app.artifacts``
(disk-first, cloud-fallback). ensure_edit лениво создаёт дефолт; save_edit — атомарный
optimistic-lock (UPDATE ... WHERE version=expected; в cloud — PostgREST PATCH с тем же условием).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app import artifacts, db
from app.editor import style_prefs
from app.editor.defaults import default_clip_edit
from app.models import ClipEdit, Segment, Word
from app.run import DATA_ROOT as DATA_ROOT  # monkeypatch-able; explicit re-export для artifacts


class EditConflict(Exception):
    """Версия edit-state в запросе устарела (optimistic-lock)."""


def data_root() -> Path:
    """Текущий DATA_ROOT (читается в рантайме → переживает monkeypatch в тестах)."""
    return DATA_ROOT


def load_transcript_words(job_id: str) -> list[Word]:
    return artifacts.load_transcript_words(job_id)


def _edit_from_row(row: dict[str, Any] | None) -> ClipEdit | None:
    """Строка clip_edits → ClipEdit. cloud: jsonb-dict в ``edit``; local: строка в ``edit_json``."""
    if row is None:
        return None
    raw = row.get("edit")
    if raw is not None:
        return ClipEdit.model_validate(raw)
    ej = row.get("edit_json")
    return ClipEdit.model_validate_json(ej) if ej else None


def load_edit(job_id: str, clip_id: str) -> ClipEdit | None:
    return _edit_from_row(db.get_clip_edit_row(job_id, clip_id))


def save_edit(
    job_id: str, clip_id: str, edit: ClipEdit, *, expected_version: int | None
) -> ClipEdit:
    """Сохранить edit (инкремент version). EditConflict при несовпадении версии (атомарно)."""
    row = db.get_clip_edit_row(job_id, clip_id)
    current = row["version"] if row else None
    if current is None:
        saved = edit.model_copy(update={"version": 1})
        db.insert_clip_edit(job_id, clip_id, saved.model_dump(), saved.version)
        return saved
    if expected_version is not None and current != expected_version:
        raise EditConflict(f"version {expected_version} != current {current}")
    saved = edit.model_copy(update={"version": current + 1})
    ok = db.update_clip_edit_if_version(
        job_id,
        clip_id,
        saved.model_dump(),
        expected_version=current,
        new_version=saved.version,
    )
    if not ok:
        raise EditConflict(f"concurrent update on {job_id}/{clip_id}")
    return saved


def ensure_edit(job_id: str, clip_id: str) -> ClipEdit:
    """Загрузить edit, либо создать дефолт из сегмента (artifacts: disk-first / cloud)."""
    existing = load_edit(job_id, clip_id)
    if existing is not None:
        return existing
    segs = artifacts.load_segments_raw(job_id)
    idx = int(clip_id.split("_")[1]) - 1  # clip_01 → 0
    if idx < 0 or idx >= len(segs):
        raise KeyError(clip_id)
    seg = Segment.model_validate(segs[idx])
    # Domain 5: сидим из СОХРАНЁННОГО дефолт-стиля владельца джобы (если есть), иначе preset A.
    # Не критично для создания клипа: ошибка чтения/битый блоб → лог + фолбэк на preset A
    # (правило №8: явный фолбэк с логом, не тихий except: pass).
    pref_style = pref_highlight = None
    pref_hook_look: dict[str, Any] | None = None
    try:
        owner = db.get_job_owner(job_id)
        if owner:
            # Seed a NEW clip from the user's DEFAULT template (if they flagged one) — the
            # explicit "adapt to my style" path. No default flagged → None → preset_a.
            parsed = style_prefs.get_default_look(db.get_style_preference(owner))
            if parsed is not None:
                pref_style, pref_highlight, pref_hook_look = parsed
    except Exception as e:  # noqa: BLE001 — сидирование стиля не должно валить создание клипа
        print(f"[ensure_edit] WARN style-pref seed skipped for {job_id}/{clip_id}: {e}")
    edit = default_clip_edit(
        clip_id,
        seg,
        load_transcript_words(job_id),
        pref_style=pref_style,
        pref_highlight=pref_highlight,
        pref_hook_look=pref_hook_look,
    )
    return save_edit(job_id, clip_id, edit, expected_version=None)
