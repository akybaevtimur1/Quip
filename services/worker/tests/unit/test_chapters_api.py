"""GET /jobs/{job}/chapters: pending → фон-генерация → done; 404 без транскрипта."""

import json

from fastapi.testclient import TestClient

from app import db
from app.editor import store
from app.editor.chapters import save_chapters
from app.models import Chapter, ChaptersData, Transcript, Word


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobA"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    words = [Word(text="a", start=0.0, end=0.4), Word(text="b.", start=0.4, end=0.8)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    from app.main import app

    return TestClient(app), job, d


def test_chapters_starts_pending_and_schedules_bg(monkeypatch, tmp_path):
    from app import tasks

    called: dict[str, str] = {}
    monkeypatch.setattr(tasks, "generate_chapters_job", lambda j: called.setdefault("job", j))
    client, job, d = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/chapters")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert called["job"] == job
    # pending уже записан на диск → повторный GET НЕ стартует вторую генерацию
    called.clear()
    r2 = client.get(f"/jobs/{job}/chapters")
    assert r2.json()["status"] == "pending"
    assert called == {}


def test_chapters_done_served_from_cache(monkeypatch, tmp_path):
    client, job, d = _client(monkeypatch, tmp_path)
    save_chapters(
        d,
        ChaptersData(
            status="done",
            chapters=[Chapter(start=0.0, end=3.0, title="Интро", summary="Начало")],
        ),
    )
    r = client.get(f"/jobs/{job}/chapters")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["chapters"][0]["title"] == "Интро"


def test_chapters_failed_state_served_as_is(monkeypatch, tmp_path):
    client, job, d = _client(monkeypatch, tmp_path)
    save_chapters(d, ChaptersData(status="failed", error="квота Gemini исчерпана"))
    r = client.get(f"/jobs/{job}/chapters")
    assert r.json()["status"] == "failed"
    assert "квота" in r.json()["error"]


def test_chapters_retry_reruns_failed(monkeypatch, tmp_path):
    # T4 #9: retry=true по failed перезапускает генерацию (failed → pending + фон-таск)
    from app import tasks

    called: dict[str, str] = {}
    monkeypatch.setattr(tasks, "generate_chapters_job", lambda j: called.setdefault("job", j))
    client, job, d = _client(monkeypatch, tmp_path)
    save_chapters(d, ChaptersData(status="failed", error="квота Gemini"))
    r = client.get(f"/jobs/{job}/chapters?retry=true")
    assert r.json()["status"] == "pending"
    assert called["job"] == job


def test_chapters_retry_ignored_on_done(monkeypatch, tmp_path):
    # retry на done НЕ дёргает повторную генерацию (главы уже есть)
    from app import tasks

    called: dict[str, str] = {}
    monkeypatch.setattr(tasks, "generate_chapters_job", lambda j: called.setdefault("job", j))
    client, job, d = _client(monkeypatch, tmp_path)
    save_chapters(
        d, ChaptersData(status="done", chapters=[Chapter(start=0, end=3, title="T", summary="S")])
    )
    r = client.get(f"/jobs/{job}/chapters?retry=true")
    assert r.json()["status"] == "done"
    assert called == {}


def test_chapters_404_without_transcript(monkeypatch, tmp_path):
    client, job, d = _client(monkeypatch, tmp_path)
    (d / "transcript.json").unlink()
    r = client.get(f"/jobs/{job}/chapters")
    assert r.status_code == 404


def test_generate_chapters_job_writes_done(monkeypatch, tmp_path):
    """Фон-таск: успех → chapters.json done; генератор замокан (без сети)."""
    from app import tasks
    from app.editor import chapters as chmod

    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(tasks, "DATA_ROOT", tmp_path / "data", raising=False)
    d = tmp_path / "data" / "jobB"
    d.mkdir(parents=True)
    words = [Word(text="a", start=0.0, end=0.4), Word(text="b.", start=0.4, end=2.5)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chmod,
        "generate_chapters",
        lambda w, dur, lang, usage_sink=None: [Chapter(start=0.0, end=3.0, title="T", summary="S")],
    )
    tasks.generate_chapters_job("jobB")
    data = json.loads((d / "chapters.json").read_text(encoding="utf-8"))
    assert data["status"] == "done"
    assert data["chapters"][0]["title"] == "T"


def test_generate_chapters_job_writes_failed(monkeypatch, tmp_path):
    from app import tasks
    from app.editor import chapters as chmod
    from app.errors import JobError

    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    d = tmp_path / "data" / "jobC"
    d.mkdir(parents=True)
    words = [Word(text="a", start=0.0, end=0.4)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(),
        encoding="utf-8",
    )

    def boom(w, dur, lang, usage_sink=None):
        raise JobError("chapters", "квота")

    monkeypatch.setattr(chmod, "generate_chapters", boom)
    tasks.generate_chapters_job("jobC")
    data = json.loads((d / "chapters.json").read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert "квота" in data["error"]
