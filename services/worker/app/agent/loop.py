"""W3: чистый control-flow агент-лупа (инъекция зависимостей → детерминированные тесты).

Реальные Gemini/БД подключаются в тонкой обёртке (`clip_agent.py`). Здесь — ТОЛЬКО логика:
выполнить тул → записать событие → повторить, остановиться на тексте модели или на hard-cap шагов.
Ошибка тула НЕ роняет луп (правило №8: возвращается модели как результат → она исправляется).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.models import AgentEvent

# Финал при достижении лимита шагов — не молча обрываем, а честно сообщаем (правило №8).
STEP_CAP_MESSAGE = "Остановился на лимите шагов. Уточни, что ещё поправить."

# Явный «финиш»-тул: модель доставляет финальный ответ ТОЛЬКО через него (Gemini в режиме
# function-calling ANY всегда зовёт тул → свободный текст-«мысль» больше НЕ принимается за ответ;
# это чинит «выбрал свою мысль рандомную как за ответ»). Имя ⇄ clip_agent._FN_DECLS / промпт.
FINISH_TOOL = "respond_to_user"


@dataclass
class ToolCall:
    """Ход модели: вызвать тул. `rationale` — короткая мысль (для ленты thinking)."""

    name: str
    args: dict[str, Any]
    rationale: str = ""


@dataclass
class TextReply:
    """Ход модели: финальный/уточняющий текст юзеру (завершает прогон)."""

    text: str


ModelTurn = ToolCall | TextReply


def run_agent_loop(
    user_message: str,
    *,
    model_turn: Callable[[list[dict[str, Any]]], ModelTurn],
    apply_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    emit: Callable[[AgentEvent], None],
    max_steps: int = 8,
    emit_user: bool = True,
) -> None:
    """Прогнать один запрос юзера через агент-луп.

    model_turn(history) → следующий ход (ToolCall|TextReply). apply_tool(name,args) → результат-дикт
    (`summary`/`before`/`after` для ленты; `error` если тул не смог — НЕ исключение). emit(event) —
    сток событий (инкрементальная запись в agent_run). max_steps — hard-cap против петель.
    emit_user=False, если user-событие уже записано вызывателем (эндпоинт до спавна).
    """
    if emit_user:
        emit(AgentEvent(role="user", text=user_message))
    history: list[dict[str, Any]] = [{"role": "user", "text": user_message}]

    for _ in range(max_steps):
        turn = model_turn(history)
        if isinstance(turn, TextReply):
            # Фолбэк: модель вернула свободный текст (в режиме ANY быть не должно). Пустой текст
            # (одна «мысль» без ответа) НЕ выдаём за ответ — мягко завершаем нейтрально.
            emit(AgentEvent(role="agent", text=turn.text or "Готово."))
            history.append({"role": "model", "text": turn.text})
            return
        # Финиш-тул: модель доставила финальный ответ → показываем мысль (если есть) + ответ, конец.
        if turn.name == FINISH_TOOL:
            if turn.rationale:
                emit(AgentEvent(role="thinking", text=turn.rationale))
            msg = str(turn.args.get("message") or "").strip() or "Готово."
            emit(AgentEvent(role="agent", text=msg))
            history.append({"role": "model", "text": msg})
            return
        # ToolCall: опц. мысль → выполнить → записать действие → вернуть результат модели.
        if turn.rationale:
            emit(AgentEvent(role="thinking", text=turn.rationale))
        result = apply_tool(turn.name, turn.args)
        summary = str(result.get("summary") or result.get("error") or turn.name)
        emit(
            AgentEvent(
                role="action",
                text=summary,
                action_kind=turn.name,
                before=result.get("before"),
                after=result.get("after"),
            )
        )
        history.append({"role": "tool", "name": turn.name, "args": turn.args, "result": result})

    emit(AgentEvent(role="agent", text=STEP_CAP_MESSAGE))
