"""W3: связка агент-лупа с реальным Gemini (function-calling) и persistence.

`run_clip_agent(run_id)` — точка входа фон-таска: грузит run, собирает контекст клипа, гоняет
`run_agent_loop` с реальным Gemini-`model_turn`, пишет события в `runs_store`. Сетевой Gemini —
тонкая обёртка; парсинг ответа (`parse_model_response`) — pure, под тестом. Биллинг: НЕ списываем
минуты (агент-путь). Отмена (InputCancellation = BaseException) пробрасывается → run уже cancelled.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from app.agent import runs_store, tools
from app.agent.loop import ModelTurn, TextReply, ToolCall, run_agent_loop
from app.config import get_settings
from app.errors import JobError
from app.models import AgentEvent

AGENT_MAX_STEPS = 8
_STAGE = "agent"
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "agent_clip_editor.v1.txt"

DEFAULT_AGENT_PROMPT = """\
You are Quip's in-editor clip assistant. You refine ONE short clip by calling tools that change its
timing (set_interval/nudge_interval) or its on-screen hook (regenerate_hook/set_hook_text), then
call request_render. You CANNOT change subtitles or framing (say so if asked). You are NOT a general
chatbot — decline anything unrelated to this clip in one sentence. Be concise; reply in the user's
language; give one short sentence of reasoning before each tool call.
"""

# Gemini function declarations (схема тулзов). Имена ⇄ app.agent.tools._DISPATCH.
_FN_DECLS: list[dict[str, Any]] = [
    {
        "name": "get_clip_state",
        "description": "Read the current clip interval, length, transcript, hook and limits.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "set_interval",
        "description": "Set the clip window to [start_sec, end_sec] in SOURCE seconds. Clamped to "
        "source bounds and to the min/max clip length.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_sec": {"type": "number"},
                "end_sec": {"type": "number"},
            },
            "required": ["start_sec", "end_sec"],
        },
    },
    {
        "name": "nudge_interval",
        "description": "Move one edge of the clip by delta_sec (negative = earlier). edge is "
        "'start' or 'end'.",
        "parameters": {
            "type": "object",
            "properties": {
                "edge": {"type": "string", "enum": ["start", "end"]},
                "delta_sec": {"type": "number"},
            },
            "required": ["edge", "delta_sec"],
        },
    },
    {
        "name": "regenerate_hook",
        "description": "Rewrite the on-screen hook for the current clip in a fresh style. Optional "
        "style_hint like 'shock', 'pov', 'shorter'.",
        "parameters": {
            "type": "object",
            "properties": {"style_hint": {"type": "string"}},
        },
    },
    {
        "name": "set_hook_text",
        "description": "Set the exact hook text (use when the user dictates the words).",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "request_render",
        "description": "Re-render the clip so the user sees the latest edits. Call after changing "
        "timing or hook.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def load_agent_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return DEFAULT_AGENT_PROMPT


def build_system_prompt(ctx: dict[str, Any]) -> str:
    """Системный промпт + контекст клипа (агент не обязан звать get_clip_state первым)."""
    return (
        f"{load_agent_prompt()}\n\n"
        f"CURRENT CLIP CONTEXT:\n"
        f"- interval (source seconds): {ctx['interval'][0]}–{ctx['interval'][1]} "
        f"(length {ctx['clip_seconds']}s)\n"
        f"- source length: {ctx['source_seconds']}s; allowed clip length: "
        f"{ctx['min_clip_seconds']}–{ctx['max_clip_seconds']}s\n"
        f"- language: {ctx['language']}\n"
        f"- current hook: {ctx['hook']!r}\n"
        f"- clip transcript: {ctx['transcript']}\n"
    )


def parse_model_response(parts: Any) -> ModelTurn:
    """PURE. Части ответа Gemini → ход агента. function_call → ToolCall (текст до него = rationale);
    иначе текст → TextReply. Защита от пустого: TextReply('')."""
    rationale = ""
    for p in parts or []:
        fc = getattr(p, "function_call", None)
        if fc is not None:
            args = dict(getattr(fc, "args", None) or {})
            return ToolCall(name=fc.name, args=args, rationale=rationale.strip())
        txt = getattr(p, "text", None)
        if txt:
            rationale += txt
    return TextReply(text=rationale.strip())


def _gemini_turn(system_prompt: str) -> Any:
    """Построить model_turn(history) поверх Gemini function-calling (с ретраями транзиентных)."""
    from google import genai
    from google.genai import types

    from app.pipeline.stage2_select import _MAX_ATTEMPTS, is_transient_gemini_error

    s = get_settings()
    if s.gemini_api_key is None:
        raise JobError(_STAGE, "нет GEMINI_API_KEY")
    client = genai.Client(api_key=s.gemini_api_key)
    # SDK коерсит dict→FunctionDeclaration в рантайме; типы строгие → cast(Any).
    fn_decls = cast(Any, _FN_DECLS)
    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=fn_decls)],
        temperature=0.4,
        max_output_tokens=1024,
    )

    # СОСТОЯНИЕ диалога — НАТИВНЫЕ Gemini Content между ходами. Критично: Content модели с
    # function_call несёт thought_signature (Gemini 2.5+), и её НЕЛЬЗЯ терять при следующем ходе
    # (иначе 400 INVALID_ARGUMENT). Поэтому echo'им РОВНО тот Content, что вернула модель, а не
    # реконструируем из имени/аргументов. Абстрактную историю лупа используем лишь чтобы понять,
    # сколько НОВЫХ tool-результатов добавить.
    contents: list[Any] = []
    pending_model_content: Any = None
    consumed_tools = 0

    def turn(history: list[dict[str, Any]]) -> ModelTurn:
        nonlocal contents, pending_model_content, consumed_tools
        if not contents:
            contents.append(types.Content(role="user", parts=[types.Part(text=history[0]["text"])]))
        tool_entries = [h for h in history if h["role"] == "tool"]
        while consumed_tools < len(tool_entries):
            te = tool_entries[consumed_tools]
            if pending_model_content is not None:
                contents.append(pending_model_content)  # function_call С thought_signature
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=te["name"], response=te["result"]
                            )
                        )
                    ],
                )
            )
            consumed_tools += 1

        last: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = client.models.generate_content(
                    model=s.llm_model, contents=contents, config=cfg
                )
                candidates = resp.candidates or []
                cand = candidates[0] if candidates else None
                pending_model_content = cand.content if cand else None  # сохранить для эха
                parts = cand.content.parts if cand and cand.content else []
                return parse_model_response(parts)
            except Exception as e:  # noqa: BLE001
                last = e
                if not is_transient_gemini_error(e):
                    raise JobError(_STAGE, f"Gemini: неретраябельная ошибка: {e}") from e
                if attempt < _MAX_ATTEMPTS - 1:
                    time.sleep(min(2**attempt, 30))
        raise JobError(_STAGE, f"Gemini недоступен после всех попыток: {last}")

    return turn


def run_clip_agent(run_id: str) -> None:
    """Фон-точка входа: прогнать агента для run_id. Биллинг не трогаем (минуты не списываем)."""
    run = runs_store.get_run(run_id)
    if run is None:
        return
    job_id, clip_id = run["job_id"], run["clip_id"]
    user_msg = next((e["text"] for e in run["events"] if e["role"] == "user"), "")

    def emit(ev: AgentEvent) -> None:
        runs_store.append_event(run_id, ev.model_dump())

    def apply(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return tools.apply_tool(name, args, job_id=job_id, clip_id=clip_id)

    try:
        ctx = tools.clip_state(job_id, clip_id)
        turn = _gemini_turn(build_system_prompt(ctx))
        run_agent_loop(
            user_msg,
            model_turn=turn,
            apply_tool=apply,
            emit=emit,
            max_steps=AGENT_MAX_STEPS,
            emit_user=False,  # user-событие уже записал эндпоинт до спавна
        )
        runs_store.set_status(run_id, "done")
    except JobError as e:
        emit(AgentEvent(role="error", text=str(e)))
        runs_store.set_status(run_id, "failed", str(e))
    except Exception as e:  # noqa: BLE001 — любой сбой → видимый failed (правило №8)
        emit(AgentEvent(role="error", text=f"unexpected: {e}"))
        runs_store.set_status(run_id, "failed", f"unexpected: {e}")
    # BaseException (InputCancellation от Stop) НЕ ловим → пробрасывается; run уже cancelled.
