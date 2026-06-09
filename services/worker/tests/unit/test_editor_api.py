import json

from fastapi.testclient import TestClient

from app import db
from app.editor import store
from app.models import Segment, Transcript, Word


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobA"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    (d / "segments.json").write_text(
        json.dumps([Segment(start=0.0, end=3.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    words = [
        Word(text="a", start=0.0, end=0.4),
        Word(text="b", start=0.4, end=0.8),
        Word(text="c", start=1.0, end=1.4),
    ]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    from app.main import app

    return TestClient(app), job


def test_get_edit_creates_default(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_01/edit")
    assert r.status_code == 200
    edit = r.json()
    assert edit["version"] == 1 and len(edit["source_intervals"]) == 1


def test_trim_makes_hole_and_optimistic_lock(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [1]}
    )
    assert r.status_code == 200
    assert len(r.json()["source_intervals"]) == 2  # hole punched
    stale = client.post(
        f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [0]}
    )
    assert stale.status_code == 409  # stale version


def test_get_edit_404_for_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/edit")
    assert r.status_code == 404
