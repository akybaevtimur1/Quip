"""Персистентность ClipEdit (спека §10): SQLite (источник правды) + edit.json зеркало.

ensure_edit лениво создаёт дефолт из segments.json+transcript.json. save_edit — optimistic-lock.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import db
from app.editor.defaults import default_clip_edit
from app.models import ClipEdit, Segment, Transcript, Word
from app.run import DATA_ROOT  # monkeypatch-able at module level


class EditConflict(Exception):
    """Версия edit-state в запросе устарела (optimistic-lock)."""


def _mirror_path(job_id: str, clip_id: str) -> Path:
    return DATA_ROOT / job_id / "clips" / clip_id / "edit.json"


def load_transcript_words(job_id: str) -> list[Word]:
    tr = Transcript.model_validate_json((DATA_ROOT / job_id / "transcript.json").read_text("utf-8"))
    return tr.words


def load_edit(job_id: str, clip_id: str) -> ClipEdit | None:
    row = db.get_clip_edit_row(job_id, clip_id)
    if row is None or not row.get("edit_json"):
        return None
    return ClipEdit.model_validate_json(row["edit_json"])


def save_edit(
    job_id: str, clip_id: str, edit: ClipEdit, *, expected_version: int | None
) -> ClipEdit:
    """Сохранить edit (инкремент version). EditConflict при несовпадении версии."""
    row = db.get_clip_edit_row(job_id, clip_id)
    current = row["version"] if row else None
    if expected_version is not None and current is not None and current != expected_version:
        raise EditConflict(f"version {expected_version} != current {current}")
    saved = edit.model_copy(update={"version": (current or 0) + 1})
    payload = saved.model_dump_json()
    db.put_clip_edit(job_id, clip_id, payload, saved.version)
    mirror = _mirror_path(job_id, clip_id)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(payload, encoding="utf-8")
    return saved


def ensure_edit(job_id: str, clip_id: str) -> ClipEdit:
    """Загрузить edit, либо создать дефолт из сегмента (segments.json + transcript.json)."""
    existing = load_edit(job_id, clip_id)
    if existing is not None:
        return existing
    out = DATA_ROOT / job_id
    segs = json.loads((out / "segments.json").read_text(encoding="utf-8"))
    idx = int(clip_id.split("_")[1]) - 1  # clip_01 → 0
    if idx < 0 or idx >= len(segs):
        raise KeyError(clip_id)
    seg = Segment.model_validate(segs[idx])
    edit = default_clip_edit(clip_id, seg, load_transcript_words(job_id))
    return save_edit(job_id, clip_id, edit, expected_version=None)
