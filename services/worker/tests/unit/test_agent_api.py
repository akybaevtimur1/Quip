"""W3: эндпоинты агент-чата (start/active/get/cancel) на tmp-store, фон-джоб замокан."""

from __future__ import annotations

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
        json.dumps([Segment(start=0.0, end=30.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    (d / "transcript.json").write_text(
        Transcript(
            language="ru", duration=60.0, words=[Word(text="a", start=0.0, end=0.4)]
        ).model_dump_json(),
        encoding="utf-8",
    )
    import app.main as main

    # фон-джоб не должен дёргать реальный Gemini в тесте — гасим bg.
    monkeypatch.setattr(main, "_run_agent_bg", lambda run_id: None)
    return TestClient(main.app), job


def test_agent_start_creates_running_run_with_user_event(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.post(f"/jobs/{job}/clips/clip_01/agent/start", json={"message": "сдвинь начало"})
    assert r.status_code == 200
    run = r.json()
    assert run["status"] == "running"
    assert run["events"][0]["role"] == "user"
    assert run["events"][0]["text"] == "сдвинь начало"
    assert "function_call_id" not in run  # внутреннее поле не светим


def test_agent_start_empty_message_400(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.post(f"/jobs/{job}/clips/clip_01/agent/start", json={"message": "   "})
    assert r.status_code == 400


def test_agent_start_is_idempotent_one_run_per_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r1 = client.post(f"/jobs/{job}/clips/clip_01/agent/start", json={"message": "a"})
    r2 = client.post(f"/jobs/{job}/clips/clip_01/agent/start", json={"message": "b"})
    assert r1.json()["run_id"] == r2.json()["run_id"]  # второй старт вернул тот же активный run


def test_agent_get_and_active(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    run_id = client.post(f"/jobs/{job}/clips/clip_01/agent/start", json={"message": "a"}).json()[
        "run_id"
    ]
    g = client.get(f"/jobs/{job}/clips/clip_01/agent/{run_id}")
    assert g.status_code == 200 and g.json()["run_id"] == run_id
    active = client.get(f"/jobs/{job}/clips/clip_01/agent/active")
    assert active.json()["run_id"] == run_id


def test_agent_get_unknown_404(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    assert client.get(f"/jobs/{job}/clips/clip_01/agent/ar_nope").status_code == 404


def test_agent_cancel_sets_cancelled(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    run_id = client.post(f"/jobs/{job}/clips/clip_01/agent/start", json={"message": "a"}).json()[
        "run_id"
    ]
    c = client.post(f"/jobs/{job}/clips/clip_01/agent/{run_id}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    # активного больше нет
    assert client.get(f"/jobs/{job}/clips/clip_01/agent/active").json() is None
    # повторная отмена идемпотентна
    assert (
        client.post(f"/jobs/{job}/clips/clip_01/agent/{run_id}/cancel").json()["status"]
        == "cancelled"
    )
