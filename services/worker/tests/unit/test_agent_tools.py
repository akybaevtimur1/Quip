"""W3: тулзы агента — pure (compute_nudge) + интеграция диспетчера на tmp-store."""

from __future__ import annotations

import json

import pytest

from app import db
from app.agent import tools
from app.agent.tools import apply_tool, compute_nudge
from app.editor import store
from app.models import Segment, SourceKind, Transcript, Word
from app.pipeline.stage0_import import SourceMeta


class TestComputeNudge:
    def test_move_start_earlier(self) -> None:
        assert compute_nudge(10.0, 40.0, "start", -3.0) == (7.0, 40.0)

    def test_move_end_later(self) -> None:
        assert compute_nudge(10.0, 40.0, "end", 5.0) == (10.0, 45.0)

    def test_bad_edge_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_nudge(10.0, 40.0, "middle", 1.0)


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobA"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    # клип 0..50с из сегмента; источник 120с
    (d / "segments.json").write_text(
        json.dumps([Segment(start=0.0, end=50.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    words = [Word(text=f"w{i}", start=float(i), end=float(i) + 0.8) for i in range(60)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=120.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    (d / "meta.json").write_text(
        SourceMeta(
            job_id=job, source=SourceKind.upload, url=None, title="t",
            duration=120.0, fps=30.0, width=1920, height=1080,
        ).model_dump_json(),
        encoding="utf-8",
    )  # fmt: skip
    return job


def test_get_clip_state_returns_context(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True
    assert r["interval"] == [0.0, 50.0]
    assert r["source_seconds"] == 120.0
    assert r["language"] == "ru"
    assert "w0" in r["transcript"]


def test_set_interval_applies_and_reports(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool(
        "set_interval", {"start_sec": 10.0, "end_sec": 40.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert r["after"] == "10.0-40.0s"
    state = apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")
    assert state["interval"] == [10.0, 40.0]


def test_set_interval_clamps_beyond_source(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    # конец за пределами источника (120с) → кламп
    r = apply_tool(
        "set_interval", {"start_sec": 100.0, "end_sec": 200.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert "clamped" in r["summary"]


def test_set_interval_bad_args_returns_error(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("set_interval", {"start_sec": "x"}, job_id=job, clip_id="clip_01")
    assert "error" in r


def test_nudge_moves_edge(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool(
        "nudge_interval", {"edge": "end", "delta_sec": -10.0}, job_id=job, clip_id="clip_01"
    )
    assert r["ok"] is True
    assert apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")["interval"] == [
        0.0,
        40.0,
    ]


def test_regenerate_hook_uses_gemini_and_saves(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    from app.editor import hook_ops

    monkeypatch.setattr(hook_ops, "regenerate_hook", lambda *a, **k: ("Новый хук", "shock"))
    r = apply_tool("regenerate_hook", {"style_hint": "шок"}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True and r["after"] == "Новый хук"
    assert apply_tool("get_clip_state", {}, job_id=job, clip_id="clip_01")["hook"] == "Новый хук"


def test_set_hook_text(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("set_hook_text", {"text": "  Ручной хук "}, job_id=job, clip_id="clip_01")
    assert r["after"] == "Ручной хук"


def test_request_render_triggers_render(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    called: list = []
    monkeypatch.setattr(tools, "_t_request_render", tools._t_request_render)  # keep
    import app.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "render_clip_edit_job", lambda j, c: called.append((j, c)))
    monkeypatch.setattr(db, "set_render_status", lambda *a, **k: None)
    r = apply_tool("request_render", {}, job_id=job, clip_id="clip_01")
    assert r["ok"] is True and called == [(job, "clip_01")]


def test_unknown_tool_returns_error(monkeypatch, tmp_path):
    job = _setup(monkeypatch, tmp_path)
    r = apply_tool("delete_everything", {}, job_id=job, clip_id="clip_01")
    assert "error" in r and "unknown" in r["error"]
