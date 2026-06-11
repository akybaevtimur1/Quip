"""Stage 2 (Select): transcript.json → segments.json (list[Segment]). ГЛАВНЫЙ GATE КАЧЕСТВА.

LLM (Gemini, structured output) возвращает ИНДЕКСЫ СЛОВ (не секунды — снимает класс
ошибок «придуманный таймкод»). Точные секунды берём детерминированно из words[idx].

Границы: вся баг-опасная математика (snap-to-sentence, маппинг индексов→секунды,
длительность-гейт, анти-overlap, клиппинг score) — pure-функции с unit-тестами.
Сетевой вызов Gemini — тонкая обёртка (ленивый импорт SDK), JobError при сбое (правило №8).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.errors import JobError
from app.models import ClipType, Segment, Transcript, Word

_STAGE = "select"
_MAX_ATTEMPTS = 7  # попытки на primary модели; backoff min(2^n, 30)с ≈ 1 мин ожидания
# При устойчивых 503 primary пробуем другие эндпоинты Gemini (разная нагрузка)
_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")

# ─────────────────────────── pure-постобработка (unit-тесты) ───────────────────────────

_SENT_END = (".", "!", "?")


def clamp_score(x: float) -> float:
    """Клип score в [0,1] (JSON-schema не гарантирует диапазон — клиппим сами)."""
    return max(0.0, min(1.0, x))


def resolve_max_clips(requested: int | None, default: int, *, lo: int = 1, hi: int = 12) -> int:
    """Сколько кандидатов отдавать: запрос юзера (степпер) > дефолт; кламп в [lo,hi]."""
    n = default if requested is None else requested
    return max(lo, min(hi, n))


def _is_sentence_end(text: str) -> bool:
    return text.strip().rstrip("\"'»").endswith(_SENT_END)


def snap_end_index(words: list[Word], end_idx: int, max_extend: int = 5) -> int:
    """Конец → ближайшее слово на .?! в окне +max_extend (иначе без изменений)."""
    if _is_sentence_end(words[end_idx].text):
        return end_idx
    for k in range(1, max_extend + 1):
        j = end_idx + k
        if j >= len(words):
            break
        if _is_sentence_end(words[j].text):
            return j
    return end_idx


def snap_start_index(
    words: list[Word], start_idx: int, max_extend: int = 5, max_fwd: int = 4
) -> int:
    """Начало клипа → к ГРАНИЦЕ предложения (clean start). Три уровня, backward-first:

    1) предыдущее слово уже завершило предложение → старт чистый, не трогаем
       (так СОХРАНЯЕМ короткие предложения-хуки);
    2) иначе назад к началу текущего предложения (после ближайшего .?! в окне max_extend) —
       включаем зачин мысли;
    3) если начало предложения недостижимо назад → старт сидит в ХВОСТЕ предложения
       (баг «Антимошенника»: первое слово — конец прошлой мысли) → уходим вперёд к началу
       следующего предложения (ближайший .?! в окне max_fwd).
    """
    if start_idx <= 0:
        return 0
    if _is_sentence_end(words[start_idx - 1].text):
        return start_idx
    for k in range(1, max_extend + 1):
        p = start_idx - k
        if p < 0:
            return 0
        if _is_sentence_end(words[p].text):
            return p + 1
    for k in range(max_fwd + 1):
        j = start_idx + k
        if j >= len(words) - 1:
            break
        if _is_sentence_end(words[j].text):
            return j + 1
    return start_idx


def indices_to_times(words: list[Word], start_idx: int, end_idx: int) -> tuple[float, float]:
    """Индексы слов → (start_sec, end_sec). JobError при выходе за диапазон или start>end."""
    n = len(words)
    if not (0 <= start_idx < n and 0 <= end_idx < n):
        raise JobError(_STAGE, f"индекс вне диапазона: start={start_idx}, end={end_idx}, n={n}")
    if start_idx > end_idx:
        raise JobError(_STAGE, f"start_word_index > end_word_index: {start_idx} > {end_idx}")
    return words[start_idx].start, words[end_idx].end


def resolve_overlaps(segments: list[Segment]) -> list[Segment]:
    """Жадно по убыванию score берём непересекающиеся сегменты; результат сортируем по start."""
    chosen: list[Segment] = []
    for seg in sorted(segments, key=lambda s: s.score, reverse=True):
        if all(seg.end <= c.start or seg.start >= c.end for c in chosen):
            chosen.append(seg)
    chosen.sort(key=lambda s: s.start)
    return chosen


def postprocess(
    raw: list[dict[str, Any]],
    words: list[Word],
    *,
    min_sec: float = 15.0,
    max_sec: float = 60.0,
    max_clips: int = 8,
) -> list[Segment]:
    """Сырые сегменты LLM → валидные Segment: snap, маппинг в секунды, длительность-гейт,
    клиппинг score, валидация type, анти-overlap, обрезка до max_clips (топ по score).
    Битый/невалидный сегмент пропускаем, а не роняем весь прогон.
    """
    valid_types = {t.value for t in ClipType}
    candidates: list[Segment] = []
    for item in raw:
        try:
            si = int(item["start_word_index"])
            ei = int(item["end_word_index"])
            typ = str(item["type"])
            reason = str(item.get("reason", "")).strip()
            score = clamp_score(float(item.get("score", 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
        if typ not in valid_types:
            continue
        try:
            si = snap_start_index(words, si)
            ei = snap_end_index(words, ei)
            start, end = indices_to_times(words, si, ei)
        except (JobError, IndexError):
            continue
        if not (min_sec <= end - start <= max_sec):
            continue
        candidates.append(
            Segment(start=start, end=end, reason=reason, score=score, type=ClipType(typ))
        )
    chosen = resolve_overlaps(candidates)
    if len(chosen) > max_clips:
        top = sorted(chosen, key=lambda s: s.score, reverse=True)[:max_clips]
        chosen = sorted(top, key=lambda s: s.start)
    return chosen


# ─────────────────────────── промпт + structured output (Gemini) ───────────────────────────

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "select_moments.v1.txt"


def load_system_prompt() -> str:
    """Системный промпт из prompts/select_moments.v1.txt (его и крутим). Fallback — дефолт ниже."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return DEFAULT_SYSTEM_PROMPT


DEFAULT_SYSTEM_PROMPT = """\
You are an expert short-form video editor. You receive a word-indexed transcript of a \
single-speaker video and must select the BEST standalone moments to cut into vertical clips.

Return moments as word index ranges. For each moment choose a `type`:
- hook: a strong opening — a question, bold claim, conflict, or number in the first seconds.
- emotional_peak: a moment of high emotion, tension, or surprise.
- complete_thought: a self-contained idea that makes sense without surrounding context.
- strong_quote: a quotable, punchy line.

HARD RULES:
- Each moment MUST be a complete thought: clean start (begin a sentence), clean ending.
- Target 15-60 seconds (sweet spot 20-45s). Do NOT pick moments shorter than ~15s.
- Moments MUST NOT overlap.
- `reason` must be CONCRETE and specific to THIS moment (why it works), not generic.
- High bar, but surface ALL genuinely strong standalone moments — never pad to hit a number.
- `score` in [0,1] = your confidence this clip will perform standalone.
- Use ONLY word indices that exist in the transcript.
"""


class _LlmSegment(BaseModel):
    start_word_index: int
    end_word_index: int
    reason: str
    score: float
    type: ClipType


class _LlmSelection(BaseModel):
    segments: list[_LlmSegment]


def build_indexed_transcript(words: list[Word], per_line: int = 10) -> str:
    """Пронумерованный по словам транскрипт: каждая строка начинается с [индекс первого слова]."""
    lines: list[str] = []
    for i in range(0, len(words), per_line):
        chunk = " ".join(w.text for w in words[i : i + per_line])
        lines.append(f"[{i}] {chunk}")
    return "\n".join(lines)


def build_user_prompt(title: str, transcript: Transcript, indexed: str, max_clips: int = 8) -> str:
    return (
        f"Video title: {title}\n"
        f"Language: {transcript.language}  Duration: {transcript.duration:.0f}s  "
        f"Words: {len(transcript.words)}\n\n"
        f"Word-indexed transcript (each line starts with the index of its first word):\n"
        f"{indexed}\n\n"
        f"Surface up to {max_clips} of the strongest non-overlapping moments as word index "
        f"ranges. Include every genuinely strong standalone moment (the user will choose among "
        f"them) — do NOT artificially limit to a few; but never pad with weak ones."
    )


def call_gemini_structured(
    user_prompt: str,
    *,
    system_prompt: str,
    response_schema: type[BaseModel],
    stage: str = _STAGE,
    usage_sink: dict[str, int] | None = None,
) -> str:
    """Вызов Gemini structured output с ретраями → сырой JSON-текст ответа.

    Общая обвязка для select_segments и generate_chapters (editor v3):
    ретраи транзиентных ошибок (free-tier 429/503), backoff capped 30с;
    primary устойчиво падает → fallback-модели (разная нагрузка).
    usage_sink (опц.) заполняется токенами prompt/output/thoughts для лога стоимости.
    """
    from google import genai
    from google.genai import types

    s = get_settings()
    key = s.gemini_api_key
    if key is None:
        raise JobError(stage, "нет GEMINI_API_KEY (LLM_PROVIDER=gemini)")

    client = genai.Client(api_key=key)
    cfg = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=response_schema,
        max_output_tokens=s.llm_max_output_tokens,
    )

    resp: Any = None
    last_err: Exception | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = client.models.generate_content(
                model=s.llm_model, contents=user_prompt, config=cfg
            )
            break
        except Exception as e:
            last_err = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(min(2**attempt, 30))

    if resp is None:
        for fb_model in _FALLBACK_MODELS:
            for attempt in range(3):
                try:
                    resp = client.models.generate_content(
                        model=fb_model, contents=user_prompt, config=cfg
                    )
                    break
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        time.sleep(min(2**attempt, 30))
            if resp is not None:
                break

    if resp is None:
        raise JobError(stage, f"Gemini недоступен после всех попыток: {last_err}")

    if usage_sink is not None and resp.usage_metadata is not None:
        um = resp.usage_metadata
        usage_sink["prompt"] = um.prompt_token_count or 0
        usage_sink["output"] = um.candidates_token_count or 0
        usage_sink["thoughts"] = getattr(um, "thoughts_token_count", 0) or 0

    text = resp.text
    if not text:
        raise JobError(stage, "Gemini вернул пустой ответ")
    return str(text)


def select_segments(
    transcript: Transcript,
    title: str,
    *,
    max_clips: int | None = None,
    usage_sink: dict[str, int] | None = None,
) -> list[Segment]:
    """Gemini structured output → сырые сегменты → постобработка → list[Segment].

    max_clips (опц.) — запрошенное юзером число клипов (UI-степпер); None → дефолт из настроек.
    usage_sink (опц.) заполняется токенами (prompt/output/thoughts) для лога стоимости.
    """
    s = get_settings()
    n_clips = resolve_max_clips(max_clips, s.max_clips)
    indexed = build_indexed_transcript(transcript.words)
    user_prompt = build_user_prompt(title, transcript, indexed, n_clips)

    text = call_gemini_structured(
        user_prompt,
        system_prompt=load_system_prompt(),
        response_schema=_LlmSelection,
        stage=_STAGE,
        usage_sink=usage_sink,
    )
    try:
        raw = json.loads(text).get("segments", [])
    except json.JSONDecodeError as e:
        raise JobError(_STAGE, f"Gemini вернул не-JSON: {e}") from e

    return postprocess(
        raw, transcript.words, min_sec=s.clip_min_sec, max_sec=s.clip_max_sec, max_clips=n_clips
    )


def select_to_file(transcript: Transcript, title: str, out_path: Any) -> list[Segment]:
    """select_segments + запись segments.json. Возвращает list[Segment]."""
    from pathlib import Path

    segments = select_segments(transcript, title)
    payload = [s.model_dump() for s in segments]
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return segments
