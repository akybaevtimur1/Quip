"""AI-карта видео (editor v3): транскрипт → главы с описаниями (Gemini, кэш на диске).

Граница: PURE-постобработка (postprocess_chapters) тестируется юнитами; сетевой вызов —
тонкая обёртка поверх stage2_select.call_gemini_structured (общие ретраи/fallback).
Кэш: data/<job>/chapters.json (ChaptersData) — генерация платится один раз (~$0.01-0.03).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from app.errors import JobError
from app.models import Chapter, ChaptersData, Word
from app.pipeline.stage2_select import build_indexed_transcript, call_gemini_structured

_STAGE = "chapters"
MIN_CHAPTER_SEC = 2.0

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "describe_chapters.v1.txt"

DEFAULT_SYSTEM_PROMPT = """\
You are mapping a long video for an editor UI. Split the ENTIRE transcript into
consecutive chapters (8-25 depending on length). Every part of the video belongs to
exactly one chapter — no gaps, no overlaps. For each chapter give a short punchy title
(<=6 words, in the language of the transcript) and a 1-2 sentence summary of what
actually happens there (concrete, not generic). Use word indices from the numbered
transcript for boundaries.
"""


def load_chapters_prompt() -> str:
    """Системный промпт из prompts/describe_chapters.v1.txt; fallback — дефолт выше."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return DEFAULT_SYSTEM_PROMPT


# ─────────────────────────── PURE ───────────────────────────


def postprocess_chapters(raw: list[Chapter], duration: float) -> list[Chapter]:
    """Сырые главы LLM → валидные: кламп в [0,duration], сортировка, выкидывание
    мусора (<MIN_CHAPTER_SEC или start>=end), непрерывное покрытие (дыра → тянем
    предыдущую; перекрытие → режем текущую), последняя глава дотягивается до конца.
    """
    valid: list[Chapter] = []
    for ch in raw:
        s = max(0.0, min(ch.start, duration))
        e = max(0.0, min(ch.end, duration))
        if e - s >= MIN_CHAPTER_SEC:
            valid.append(
                Chapter(start=s, end=e, title=ch.title.strip(), summary=ch.summary.strip())
            )
    valid.sort(key=lambda c: c.start)

    out: list[Chapter] = []
    for ch in valid:
        if out:
            prev = out[-1]
            if ch.start < prev.end:
                ch = Chapter(start=prev.end, end=ch.end, title=ch.title, summary=ch.summary)
                if ch.end - ch.start < MIN_CHAPTER_SEC:
                    continue
            elif ch.start > prev.end:
                out[-1] = Chapter(
                    start=prev.start, end=ch.start, title=prev.title, summary=prev.summary
                )
        out.append(ch)
    if out:
        last = out[-1]
        out[-1] = Chapter(start=last.start, end=duration, title=last.title, summary=last.summary)
    return out


# ─────────────────────────── Gemini I/O ───────────────────────────


class _LlmChapter(BaseModel):
    start_word_index: int
    end_word_index: int
    title: str
    summary: str


class _LlmChapters(BaseModel):
    chapters: list[_LlmChapter]


def generate_chapters(
    words: list[Word],
    duration: float,
    language: str,
    *,
    usage_sink: dict[str, int] | None = None,
) -> list[Chapter]:
    """Gemini → главы по индексам слов → секунды → postprocess_chapters."""
    indexed = build_indexed_transcript(words)
    user_prompt = (
        f"Language: {language}  Duration: {duration:.0f}s  Words: {len(words)}\n\n"
        f"Word-indexed transcript (each line starts with the index of its first word):\n"
        f"{indexed}\n\n"
        f"Split the ENTIRE video into consecutive chapters covering everything."
    )
    text = call_gemini_structured(
        user_prompt,
        system_prompt=load_chapters_prompt(),
        response_schema=_LlmChapters,
        stage=_STAGE,
        usage_sink=usage_sink,
    )
    try:
        raw_items = json.loads(text).get("chapters", [])
    except json.JSONDecodeError as e:
        raise JobError(_STAGE, f"Gemini returned non-JSON: {e}") from e

    n = len(words)
    raw: list[Chapter] = []
    for item in raw_items:
        try:
            si = max(0, min(int(item["start_word_index"]), n - 1))
            ei = max(0, min(int(item["end_word_index"]), n - 1))
            raw.append(
                Chapter(
                    start=words[si].start,
                    end=words[ei].end,
                    title=str(item.get("title", "")).strip(),
                    summary=str(item.get("summary", "")).strip(),
                )
            )
        except (KeyError, TypeError, ValueError, IndexError):
            continue  # битую главу пропускаем, не роняя карту целиком
    return postprocess_chapters(raw, duration)


# ─────────────────────────── кэш chapters.json ───────────────────────────


def chapters_path(job_dir: Path) -> Path:
    return job_dir / "chapters.json"


def load_chapters(job_dir: Path) -> ChaptersData | None:
    """Прочитать кэш; None если файла нет (генерация ещё не стартовала)."""
    p = chapters_path(job_dir)
    if not p.exists():
        return None
    return ChaptersData.model_validate_json(p.read_text(encoding="utf-8"))


def save_chapters(job_dir: Path, data: ChaptersData) -> None:
    chapters_path(job_dir).write_text(
        data.model_dump_json(indent=2), encoding="utf-8", newline="\n"
    )
