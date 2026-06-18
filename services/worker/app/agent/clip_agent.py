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

# Фолбэк-цепочка моделей чата: если primary (s.llm_model, прод = gemini-flash-latest) перегружен/
# недоступен, перебираем другие Flash-модели — цель «хоть кто-то ответит», а не падать. Берётся
# ТОЛЬКО как фолбэк (primary остаётся пиновкой из секрета LLM_MODEL). gemini-flash-latest тут даёт
# доступ к самой свежей Flash, когда конкретная версия временно лежит.
_AGENT_FALLBACK_MODELS = ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite")

# Глобально-перманентные коды Gemini: фолбэк на ДРУГУЮ модель их не вылечит (битый ключ/доступ/
# схема) → роняем сразу с корнем (правило №8, не маскируем бэкоффом). 404 сюда НЕ входит — «такой
# модели нет» лечится переходом на следующую модель цепочки.
_GLOBAL_PERMANENT_CODES = frozenset({400, 401, 403, 422})


def _model_chain(
    primary: str, fallbacks: tuple[str, ...], *, prefer: str | None = None
) -> list[str]:
    """PURE. Порядок моделей: prefer (уже сработавшая) → primary → фолбэки, без дублей."""
    chain: list[str] = []
    for m in (prefer, primary, *fallbacks):
        if m and m not in chain:
            chain.append(m)
    return chain


DEFAULT_AGENT_PROMPT = """\
You are Quip's in-editor clip assistant. You refine ONE short clip by calling tools that change its
timing (set_interval/nudge_interval) or its on-screen hook (regenerate_hook/set_hook_text), then
call request_render. You CANNOT change subtitles or framing (say so if asked). You are NOT a general
chatbot — decline anything unrelated to this clip in one sentence. Be concise; give one short
sentence of reasoning before each tool call.
LANGUAGE: talk to the user in the USER's language. But on-screen text (the hook) MUST be written in
the clip's TRANSCRIPTION language (the `language` in the context), NOT the chat language — if the
user dictates exact hook words in another language, translate their wording into the transcription
language before calling set_hook_text. The video is in that language; a hook in another language
looks broken.
"""

# Gemini function declarations (схема тулзов). Имена ⇄ app.agent.tools._DISPATCH.
_FN_DECLS: list[dict[str, Any]] = [
    {
        "name": "get_clip_state",
        "description": "Read the current clip interval, length, transcript, hook and limits.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_surrounding_transcript",
        "description": "Read the transcript AROUND the current clip (before and after it) with "
        "SOURCE-second timestamps, so you can analyze context and choose clean cut points on "
        "sentence boundaries before calling set_interval. Optional seconds_around (default 30, "
        "capped) widens the window on each side.",
        "parameters": {
            "type": "object",
            "properties": {"seconds_around": {"type": "number"}},
        },
    },
    {
        "name": "get_video_map",
        "description": "Read a compact overview of the WHOLE source video: a narrative summary and "
        "chapter list (with time ranges, titles, summaries, and key moment labels). Use this "
        "when the user asks to rewrite the hook considering the full video, or to understand "
        "where this clip sits in the overall context. No parameters required.",
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
        "description": "Set the exact on-screen hook text (use when the user dictates the words). "
        "The text MUST be in the clip's TRANSCRIPTION language (the 'language' in the context), "
        "NOT the user's chat language — if the user dictates the hook in another language, "
        "translate their wording into the transcription language before passing it here.",
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
    {
        "name": "respond_to_user",
        "description": "Deliver your FINAL reply to the user (or ask a clarifying question). Call "
        "this exactly once when you are done — it ENDS your turn and is the ONLY way your words "
        "reach the user. Reply in the user's language.",
        "parameters": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
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
    """PURE. Части ответа Gemini → ход агента.

    function_call → ToolCall (предшествующий текст = rationale для ленты thinking). Иначе TextReply,
    но финальным ОТВЕТОМ считаем ТОЛЬКО НЕ-thought текст: «мысли» (part.thought=True, Gemini 2.5)
    идут в rationale и НИКОГДА не выдаются за ответ (чинит «случайная мысль как ответ»). Чистая
    мысль без вызова → TextReply('') (луп завершит нейтрально, не покажет мысль ответом).
    В режиме function-calling ANY текста почти нет → финал идёт через respond_to_user.
    """
    rationale = ""
    answer = ""
    fc = None
    for p in parts or []:
        f = getattr(p, "function_call", None)
        if f is not None and fc is None:
            fc = f
            continue
        txt = getattr(p, "text", None)
        if not txt:
            continue
        if getattr(p, "thought", False):
            rationale += txt
        else:
            answer += txt
    if fc is not None:
        args = dict(getattr(fc, "args", None) or {})
        return ToolCall(name=fc.name, args=args, rationale=(rationale + answer).strip())
    return TextReply(text=answer.strip())


def _gemini_turn(system_prompt: str, prior_turns: list[dict[str, Any]] | None = None) -> Any:
    """Построить model_turn(history) поверх Gemini function-calling (с ретраями транзиентных).

    prior_turns (опц.) — прошлая беседа клипа ({role:'user'|'model', text}) → засевается в contents
    ПЕРЕД текущим сообщением (память агента, #1). Только ТЕКСТ (без function_call) → не несёт
    thought_signature → echo-логика текущих tool-вызовов не затрагивается.
    """
    from google import genai
    from google.genai import types

    from app.pipeline.stage2_select import _MAX_ATTEMPTS, is_transient_gemini_error

    s = get_settings()
    if s.gemini_api_key is None:
        raise JobError(_STAGE, "GEMINI_API_KEY is not set")
    client = genai.Client(api_key=s.gemini_api_key)
    # SDK коерсит dict→FunctionDeclaration в рантайме; типы строгие → cast(Any).
    fn_decls = cast(Any, _FN_DECLS)
    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=fn_decls)],
        # ANY: модель ОБЯЗАНА вызывать тул каждый ход → свободный текст-«мысль» не принимается за
        # ответ (стабильный флоу). Финальный ответ доставляется ТОЛЬКО через respond_to_user.
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY
            )
        ),
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
    # прилипаем к первой заработавшей модели (меньше скачков между ходами → стабильнее)
    chosen_model: str | None = None

    def _generate(contents_: list[Any]) -> Any:
        """Сгенерировать ответ, перебирая цепочку моделей с ретраями транзиентных ошибок.

        Цель — «хоть кто-то ответит»: primary перегружен/недоступен (429/503/таймаут) → ретраи с
        бэкоффом, затем следующая модель цепочки. 404 «модели нет» → сразу следующая. Глобально-
        перманентная ошибка (битый ключ/доступ/схема: 400/401/403/422) фолбэком не лечится →
        роняем сразу (правило №8). Прилипаем к сработавшей модели — меньше скачков между ходами.
        """
        nonlocal chosen_model
        last: Exception | None = None
        for model in _model_chain(s.llm_model, _AGENT_FALLBACK_MODELS, prefer=chosen_model):
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    resp = client.models.generate_content(
                        model=model, contents=contents_, config=cfg
                    )
                    chosen_model = model
                    return resp
                except Exception as e:  # noqa: BLE001
                    last = e
                    if getattr(e, "code", None) in _GLOBAL_PERMANENT_CODES:
                        raise JobError(_STAGE, f"Gemini: non-retryable error: {e}") from e
                    if not is_transient_gemini_error(e):
                        break  # перманентно для ЭТОЙ модели (напр. 404) → следующая модель
                    if attempt < _MAX_ATTEMPTS - 1:
                        time.sleep(min(2**attempt, 30))
        raise JobError(_STAGE, f"Gemini unavailable after all models/attempts: {last}")

    def turn(history: list[dict[str, Any]]) -> ModelTurn:
        nonlocal contents, pending_model_content, consumed_tools
        if not contents:
            for pt in prior_turns or []:
                role = "model" if pt.get("role") == "model" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=pt["text"])]))
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

        resp = _generate(contents)
        candidates = resp.candidates or []
        cand = candidates[0] if candidates else None
        pending_model_content = cand.content if cand else None  # сохранить для эха
        parts = cand.content.parts if cand and cand.content else []
        return parse_model_response(parts)

    return turn


_PRIOR_TURNS_CAP = 16  # сколько прошлых реплик беседы держим в памяти модели (кап против блоата)


def _prior_turns(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """PURE. Прошлая беседа клипа для памяти модели: пары (user→user, agent→model) ДО ПОСЛЕДНЕГО
    user-события (= текущий запрос). thinking/action/error НЕ шлём (внутреннее; tool-вызовы прошлых
    ранов несут thought_signature, непереиспользуемый между генерациями). Кап последних N реплик."""
    last_user = max((i for i, e in enumerate(events) if e.get("role") == "user"), default=-1)
    out: list[dict[str, Any]] = []
    for e in events[:last_user]:
        if e.get("role") == "user":
            out.append({"role": "user", "text": e.get("text", "")})
        elif e.get("role") == "agent":
            out.append({"role": "model", "text": e.get("text", "")})
    return out[-_PRIOR_TURNS_CAP:]


def run_clip_agent(run_id: str) -> None:
    """Фон-точка входа: прогнать агента для run_id. Биллинг не трогаем (минуты не списываем)."""
    run = runs_store.get_run(run_id)
    if run is None:
        return
    job_id, clip_id = run["job_id"], run["clip_id"]
    events = run["events"]
    # Текущий запрос = ПОСЛЕДНЕЕ user-событие: ленту нового рана засеяли прошлой беседой (см.
    # agent_start), поэтому текущее сообщение — последнее, а не первое.
    user_msgs = [e["text"] for e in events if e.get("role") == "user"]
    user_msg = user_msgs[-1] if user_msgs else ""
    prior = _prior_turns(events)

    def emit(ev: AgentEvent) -> None:
        runs_store.append_event(run_id, ev.model_dump())

    def apply(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return tools.apply_tool(name, args, job_id=job_id, clip_id=clip_id)

    try:
        ctx = tools.clip_state(job_id, clip_id)
        turn = _gemini_turn(build_system_prompt(ctx), prior)
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
