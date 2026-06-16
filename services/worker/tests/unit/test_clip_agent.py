"""W3: связка clip_agent — parse ответа (pure) + run_clip_agent (фейк Gemini, tmp store)."""

from __future__ import annotations

from app import db
from app.agent import clip_agent
from app.agent import runs_store as rs
from app.agent.clip_agent import parse_model_response, run_clip_agent
from app.agent.loop import TextReply, ToolCall
from app.errors import JobError


class _FC:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _Part:
    def __init__(self, text=None, function_call=None):
        self.text = text
        self.function_call = function_call


class TestParseModelResponse:
    def test_function_call_with_rationale(self):
        parts = [
            _Part(text="двигаю старт"),
            _Part(function_call=_FC("set_interval", {"start_sec": 9})),
        ]
        turn = parse_model_response(parts)
        assert isinstance(turn, ToolCall)
        assert turn.name == "set_interval" and turn.args == {"start_sec": 9}
        assert turn.rationale == "двигаю старт"

    def test_text_only_is_text_reply(self):
        turn = parse_model_response([_Part(text="готово, глянь")])
        assert isinstance(turn, TextReply) and turn.text == "готово, глянь"

    def test_empty_parts_is_empty_text(self):
        turn = parse_model_response([])
        assert isinstance(turn, TextReply) and turn.text == ""


def _init(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    db.init_db()


_CTX = {
    "interval": [0.0, 50.0], "clip_seconds": 50.0, "source_seconds": 120.0,
    "language": "ru", "transcript": "слова клипа", "hook": None,
    "min_clip_seconds": 15, "max_clip_seconds": 60,
}  # fmt: skip


def test_run_clip_agent_happy_path(monkeypatch, tmp_path):
    _init(monkeypatch, tmp_path)
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", "u")
    rs.append_event(rid, {"role": "user", "text": "сдвинь начало раньше"})

    monkeypatch.setattr(clip_agent.tools, "clip_state", lambda j, c: _CTX)
    monkeypatch.setattr(
        clip_agent.tools, "apply_tool", lambda n, a, **k: {"ok": True, "summary": "start→9"}
    )
    turns = iter(
        [
            ToolCall("set_interval", {"start_sec": 9.0, "end_sec": 40.0}, "двигаю"),
            TextReply("готово"),
        ]
    )
    monkeypatch.setattr(clip_agent, "_gemini_turn", lambda system: lambda history: next(turns))

    run_clip_agent(rid)

    run = rs.get_run(rid)
    assert run["status"] == "done"
    roles = [e["role"] for e in run["events"]]
    assert roles[0] == "user"  # emit_user=False → единственный user — заранее записанный
    assert "thinking" in roles and "action" in roles and roles[-1] == "agent"


def test_run_clip_agent_gemini_failure_marks_failed(monkeypatch, tmp_path):
    _init(monkeypatch, tmp_path)
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", "u")
    rs.append_event(rid, {"role": "user", "text": "x"})
    monkeypatch.setattr(clip_agent.tools, "clip_state", lambda j, c: _CTX)

    def _boom(system):
        raise JobError("agent", "Gemini недоступен")

    monkeypatch.setattr(clip_agent, "_gemini_turn", _boom)

    run_clip_agent(rid)

    run = rs.get_run(rid)
    assert run["status"] == "failed"
    assert run["error"] and "error" in [e["role"] for e in run["events"]]


def test_run_clip_agent_cancel_propagates(monkeypatch, tmp_path):
    # InputCancellation (BaseException) НЕ должна ловиться → пробрасывается, run не помечается done.
    _init(monkeypatch, tmp_path)
    rid = rs.new_run_id()
    rs.create_run(rid, "jobA", "clip_01", "u")
    rs.append_event(rid, {"role": "user", "text": "x"})
    monkeypatch.setattr(clip_agent.tools, "clip_state", lambda j, c: _CTX)

    class _Cancel(BaseException):
        pass

    def _cancel_turn(system):
        def turn(history):
            raise _Cancel()

        return turn

    monkeypatch.setattr(clip_agent, "_gemini_turn", _cancel_turn)

    raised = False
    try:
        run_clip_agent(rid)
    except _Cancel:
        raised = True
    assert raised  # пробросилось
    assert rs.get_run(rid)["status"] == "running"  # НЕ done/failed (отмену ставит эндпоинт)
