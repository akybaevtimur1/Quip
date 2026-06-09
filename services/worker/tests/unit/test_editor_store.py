import json

import pytest

from app import db
from app.editor import store
from app.editor.store import EditConflict
from app.models import Segment, Transcript, Word


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobZ"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    seg = Segment(start=0.0, end=3.0, reason="r", score=0.5, type="hook")
    (d / "segments.json").write_text(json.dumps([seg.model_dump()]), encoding="utf-8")
    words = [Word(text="a", start=0.0, end=0.4), Word(text="b", start=0.4, end=0.8)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(), encoding="utf-8"
    )
    return job


def test_ensure_creates_default_then_loads(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    edit = store.ensure_edit(job, "clip_01")
    assert edit.version == 1 and len(edit.source_intervals) == 1
    again = store.load_edit(job, "clip_01")
    assert again is not None and again.version == 1


def test_save_bumps_version_and_optimistic_lock(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    edit = store.ensure_edit(job, "clip_01")  # version 1
    saved = store.save_edit(job, "clip_01", edit, expected_version=1)
    assert saved.version == 2
    with pytest.raises(EditConflict):
        store.save_edit(job, "clip_01", edit, expected_version=1)  # stale version


def test_load_transcript_words(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    words = store.load_transcript_words(job)
    assert [w.text for w in words] == ["a", "b"]
