"""W3: control-flow агент-лупа (чистая логика, инъекция зависимостей).

Скриптуем ответы «модели» и проверяем: выполнение тулзов, запись событий,
остановку на тексте, hard-cap шагов, проброс ошибки тула обратно модели.
"""

from __future__ import annotations

from app.agent.loop import FINISH_TOOL, TextReply, ToolCall, run_agent_loop
from app.models import AgentEvent


def _runner(turns: list[object]):
    """model_turn, отдающий заранее заготовленные ходы по очереди."""
    seq = iter(turns)

    def model_turn(history: list[dict]) -> object:
        return next(seq)

    return model_turn


def test_text_reply_ends_run_without_tools() -> None:
    events: list[AgentEvent] = []
    calls: list[tuple] = []
    run_agent_loop(
        "сделай хук покороче",
        model_turn=_runner([TextReply("Готово, глянь")]),
        apply_tool=lambda n, a: calls.append((n, a)) or {},
        emit=events.append,
        max_steps=8,
    )
    roles = [e.role for e in events]
    assert roles == ["user", "agent"]
    assert events[0].text == "сделай хук покороче"
    assert events[-1].text == "Готово, глянь"
    assert calls == []  # тулзы не дёргались


def test_tool_call_then_text() -> None:
    events: list[AgentEvent] = []
    applied: list[tuple] = []

    def apply(name: str, args: dict) -> dict:
        applied.append((name, args))
        return {"ok": True, "summary": "start 12.4→9.0s"}

    run_agent_loop(
        "начни раньше",
        model_turn=_runner(
            [
                ToolCall(
                    "set_interval", {"start_sec": 9.0, "end_sec": 30.0}, rationale="двигаю старт"
                ),
                TextReply("Сдвинул начало"),
            ]
        ),
        apply_tool=apply,
        emit=events.append,
        max_steps=8,
    )
    roles = [e.role for e in events]
    assert roles == ["user", "thinking", "action", "agent"]
    assert applied == [("set_interval", {"start_sec": 9.0, "end_sec": 30.0})]
    action = next(e for e in events if e.role == "action")
    assert action.action_kind == "set_interval"


def test_thinking_skipped_when_no_rationale() -> None:
    events: list[AgentEvent] = []
    run_agent_loop(
        "x",
        model_turn=_runner([ToolCall("regenerate_hook", {}), TextReply("ok")]),
        apply_tool=lambda n, a: {"ok": True},
        emit=events.append,
        max_steps=8,
    )
    assert [e.role for e in events] == ["user", "action", "agent"]


def test_step_cap_finalizes_with_message() -> None:
    events: list[AgentEvent] = []
    # модель бесконечно зовёт тул → должны остановиться на max_steps и финализировать
    always_tool = _runner([ToolCall("nudge_interval", {"edge": "end", "delta_sec": 1.0})] * 50)
    run_agent_loop(
        "крути бесконечно",
        model_turn=always_tool,
        apply_tool=lambda n, a: {"ok": True},
        emit=events.append,
        max_steps=3,
    )
    actions = [e for e in events if e.role == "action"]
    assert len(actions) == 3  # не больше cap
    assert events[-1].role == "agent"  # финальное сообщение есть


def test_finish_tool_delivers_answer_and_ends() -> None:
    events: list[AgentEvent] = []
    applied: list[tuple] = []
    run_agent_loop(
        "обрежь нормально",
        model_turn=_runner(
            [
                ToolCall("set_interval", {"start_sec": 9.0, "end_sec": 30.0}, rationale="режу"),
                ToolCall(FINISH_TOOL, {"message": "Готово — глянь превью"}, rationale="готов"),
            ]
        ),
        apply_tool=lambda n, a: applied.append((n, a)) or {"ok": True, "summary": "ok"},
        emit=events.append,
        max_steps=8,
    )
    # respond_to_user НЕ исполняется как обычный тул → его нет в applied
    assert applied == [("set_interval", {"start_sec": 9.0, "end_sec": 30.0})]
    assert events[-1].role == "agent"
    assert events[-1].text == "Готово — глянь превью"


def test_empty_text_reply_does_not_show_a_bare_thought() -> None:
    events: list[AgentEvent] = []
    run_agent_loop(
        "x",
        model_turn=_runner([TextReply("")]),  # «мысль» без ответа → пусто
        apply_tool=lambda n, a: {},
        emit=events.append,
        max_steps=8,
    )
    assert events[-1].role == "agent"
    assert events[-1].text == "Готово."  # нейтральный финал, НЕ пустой пузырь/мысль


def test_tool_error_is_fed_back_and_loop_continues() -> None:
    events: list[AgentEvent] = []
    seen_results: list[dict] = []

    def model_turn(history: list[dict]) -> object:
        # второй ход модель делает после того, как увидела результат тула в истории
        if not any(h.get("role") == "tool" for h in history):
            return ToolCall("set_interval", {"start_sec": 30.0, "end_sec": 9.0})  # невалидно
        seen_results.append(history[-1])
        return TextReply("Поправил, начало должно быть раньше конца")

    def apply(name: str, args: dict) -> dict:
        return {"error": "start > end"}  # диспетчер вернул ошибку (не падаем)

    run_agent_loop("сломай", model_turn=model_turn, apply_tool=apply, emit=events.append)
    # ошибка тула пробросилась в историю → модель увидела и исправилась текстом
    assert seen_results and seen_results[0]["role"] == "tool"
    assert "error" in str(seen_results[0])
    assert events[-1].role == "agent"
