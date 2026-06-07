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
from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.errors import JobError
from app.models import ClipType, Segment, Transcript, Word

_STAGE = "select"
_MAX_ATTEMPTS = 4  # ретраи транзиентных 429/503 (free-tier перегрузки), бэк-офф 1/2/4с

# ─────────────────────────── pure-постобработка (unit-тесты) ───────────────────────────

_SENT_END = (".", "!", "?")


def clamp_score(x: float) -> float:
    """Клип score в [0,1] (JSON-schema не гарантирует диапазон — клиппим сами)."""
    return max(0.0, min(1.0, x))


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


def snap_start_index(words: list[Word], start_idx: int, max_extend: int = 5) -> int:
    """Сдвинуть начало к началу предложения (после ближайшего .?! назад, в пределах окна)."""
    if start_idx <= 0:
        return 0
    for k in range(1, max_extend + 1):
        p = start_idx - k
        if p < 0:
            return 0
        if _is_sentence_end(words[p].text):
            return p + 1
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
) -> list[Segment]:
    """Сырые сегменты LLM → валидные Segment: snap, маппинг в секунды, длительность-гейт,
    клиппинг score, валидация type, анти-overlap. Битый/невалидный сегмент пропускаем
    (quality over quantity), а не роняем весь прогон.
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
        si = snap_start_index(words, si)
        ei = snap_end_index(words, ei)
        try:
            start, end = indices_to_times(words, si, ei)
        except JobError:
            continue
        if not (min_sec <= end - start <= max_sec):
            continue
        candidates.append(
            Segment(start=start, end=end, reason=reason, score=score, type=ClipType(typ))
        )
    return resolve_overlaps(candidates)


# ─────────────────────────── промпт + structured output (Gemini) ───────────────────────────

SYSTEM_PROMPT = """\
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
- Quality over quantity: pick only genuinely strong moments. Fewer great clips beat many weak ones.
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


def build_user_prompt(title: str, transcript: Transcript, indexed: str) -> str:
    return (
        f"Video title: {title}\n"
        f"Language: {transcript.language}  Duration: {transcript.duration:.0f}s  "
        f"Words: {len(transcript.words)}\n\n"
        f"Word-indexed transcript (each line starts with the index of its first word):\n"
        f"{indexed}\n\n"
        f"Select the best non-overlapping moments as word index ranges."
    )


def select_segments(
    transcript: Transcript, title: str, *, usage_sink: dict[str, int] | None = None
) -> list[Segment]:
    """Gemini structured output → сырые сегменты → постобработка → list[Segment].

    usage_sink (опц.) заполняется токенами (prompt/output/thoughts) для лога стоимости.
    """
    from google import genai
    from google.genai import types

    s = get_settings()
    key = s.gemini_api_key
    if key is None:
        raise JobError(_STAGE, "нет GEMINI_API_KEY (LLM_PROVIDER=gemini)")

    client = genai.Client(api_key=key)
    indexed = build_indexed_transcript(transcript.words)
    user_prompt = build_user_prompt(title, transcript, indexed)
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=_LlmSelection,
        max_output_tokens=s.llm_max_output_tokens,
    )

    # Ретраи транзиентных ошибок (free-tier 429/503). Без тихого фолбэка: исчерпали → JobError.
    resp: Any = None
    last_err: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = client.models.generate_content(
                model=s.llm_model, contents=user_prompt, config=cfg
            )
            break
        except Exception as e:  # SDK кидает разные типы (ServerError/ClientError) — оборачиваем
            last_err = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)
    if resp is None:
        raise JobError(_STAGE, f"Gemini недоступен после {_MAX_ATTEMPTS} попыток: {last_err}")

    if usage_sink is not None and resp.usage_metadata is not None:
        um = resp.usage_metadata
        usage_sink["prompt"] = um.prompt_token_count or 0
        usage_sink["output"] = um.candidates_token_count or 0
        usage_sink["thoughts"] = getattr(um, "thoughts_token_count", 0) or 0

    text = resp.text
    if not text:
        raise JobError(_STAGE, "Gemini вернул пустой ответ")
    try:
        raw = json.loads(text).get("segments", [])
    except json.JSONDecodeError as e:
        raise JobError(_STAGE, f"Gemini вернул не-JSON: {e}") from e

    return postprocess(raw, transcript.words, min_sec=s.clip_min_sec, max_sec=s.clip_max_sec)


def select_to_file(transcript: Transcript, title: str, out_path: Any) -> list[Segment]:
    """select_segments + запись segments.json. Возвращает list[Segment]."""
    from pathlib import Path

    segments = select_segments(transcript, title)
    payload = [s.model_dump() for s in segments]
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return segments
