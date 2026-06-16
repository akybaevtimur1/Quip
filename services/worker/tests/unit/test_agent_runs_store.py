"""W3: persistence agent_runs (локальный SQLite-режим)."""

from __future__ import annotations

from app import db
from app.agent import runs_store as rs


def _init(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    db.init_db()


def test_create_get_append_and_status(monkeypatch, tmp_path):
    _init(monkeypatch, tmp_path)
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", "user_1")
    run = rs.get_run(rid)
    assert run is not None
    assert run["status"] == "running" and run["events"] == [] and run["cancellable"] is True

    rs.append_event(rid, {"role": "user", "text": "сдвинь начало"})
    rs.append_event(rid, {"role": "action", "text": "start 12→9", "action_kind": "set_interval"})
    run = rs.get_run(rid)
    assert [e["role"] for e in run["events"]] == ["user", "action"]

    rs.set_status(rid, "done")
    run = rs.get_run(rid)
    assert run["status"] == "done" and run["cancellable"] is False


def test_set_cancelled_guard(monkeypatch, tmp_path):
    _init(monkeypatch, tmp_path)
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", None)
    assert rs.set_cancelled(rid) is True  # running → cancelled
    assert rs.get_run(rid)["status"] == "cancelled"
    assert rs.set_cancelled(rid) is False  # уже терминал → не применилось (идемпотентно)


def test_running_run_idempotency(monkeypatch, tmp_path):
    _init(monkeypatch, tmp_path)
    assert rs.running_run("jobA", "clip_01") is None
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", None)
    active = rs.running_run("jobA", "clip_01")
    assert active is not None and active["run_id"] == rid
    rs.set_status(rid, "done")
    assert rs.running_run("jobA", "clip_01") is None  # завершён → не активен


def test_function_call_id_roundtrip(monkeypatch, tmp_path):
    _init(monkeypatch, tmp_path)
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", None)
    rs.set_function_call_id(rid, "fc_123")
    assert rs.get_run(rid)["function_call_id"] == "fc_123"
