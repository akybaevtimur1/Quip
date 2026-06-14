"""Stage 1 (Transcribe): source.wav → transcript.json (Transcript, word-level, секунды).

Провайдеры взаимозаменяемы (Deepgram/AssemblyAI) — downstream видит только Transcript.
Deepgram отдаёт СЕКУНДЫ; AssemblyAI — мс (делить на 1000) при реализации.

Границы: ``deepgram_to_transcript`` — pure (ответ → Transcript), покрыта unit-тестами.
Сетевой вызов (``call_deepgram``) — тонкая обёртка над стабильным REST ``/v1/listen``
(не генерёный SDK v7); при сбое кидает JobError (правило №8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.errors import JobError
from app.models import Transcript, Word

_STAGE = "transcribe"
_DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"

# Deepgram Nova pre-recorded, pay-as-you-go (≈$0.258/час). Для лога стоимости.
DEEPGRAM_NOVA_USD_PER_MIN = 0.0043


# ─────────────────────────── pure-нормализация (unit-тесты) ───────────────────────────


def deepgram_to_transcript(resp: dict[str, Any], *, default_language: str = "en") -> Transcript:
    """Сырой ответ Deepgram REST → Transcript (секунды, punctuated_word, сортировка по start).

    JobError при неожиданной структуре или нуле слов.
    """
    try:
        channel = resp["results"]["channels"][0]
        raw_words = channel["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError) as e:
        raise JobError(_STAGE, f"неожиданная структура ответа Deepgram: {e}") from e

    words: list[Word] = []
    for w in raw_words:
        try:
            text = w.get("punctuated_word") or w["word"]
            start = float(w["start"])
            end = float(w["end"])
        except (KeyError, TypeError, ValueError) as e:
            raise JobError(_STAGE, f"битое слово в ответе Deepgram: {e}") from e
        conf = w.get("confidence")
        words.append(
            Word(
                text=text,
                start=start,
                end=end,
                confidence=float(conf) if conf is not None else None,
            )
        )
    if not words:
        raise JobError(_STAGE, "Deepgram вернул 0 слов")
    words.sort(key=lambda x: x.start)

    language: str = channel.get("detected_language") or default_language
    raw_dur = (resp.get("metadata") or {}).get("duration")
    if raw_dur is None:
        # Раньше тут был тихий фолбэк 0.0 → стоимость в run.py = 0 (ломает учёт маржи,
        # правило №12) и проверки длины. Явный отказ (правило №8).
        raise JobError(_STAGE, "Deepgram не вернул metadata.duration")
    try:
        duration = float(raw_dur)
    except (TypeError, ValueError) as e:
        raise JobError(_STAGE, f"битая metadata.duration {raw_dur!r}: {e}") from e
    return Transcript(language=language, duration=duration, words=words)


# ─────────────────────────── провайдер Deepgram (REST через httpx) ───────────────────────────


def call_deepgram(
    wav: Path, *, api_key: str, model: str, language: str | None = None
) -> dict[str, Any]:
    """POST source.wav в Deepgram /v1/listen, вернуть сырой JSON. JobError при сбое/не-200.

    language=None → detect_language=true (авто-определение EN/RU/др.). Иначе фикс-язык.
    """
    params = {
        "model": model,
        "smart_format": "true",
        "punctuate": "true",
        "diarize": "false",
    }
    if language:
        params["language"] = language
    else:
        params["detect_language"] = "true"
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"}
    try:
        r = httpx.post(
            _DEEPGRAM_URL,
            params=params,
            headers=headers,
            content=wav.read_bytes(),
            # write=None: без лимита на upload (WAV может быть >100MB при медленном аплоаде)
            timeout=httpx.Timeout(connect=30.0, write=None, read=300.0, pool=5.0),
        )
    except httpx.HTTPError as e:
        raise JobError(_STAGE, f"сетевая ошибка Deepgram: {e}") from e
    if r.status_code != 200:
        raise JobError(_STAGE, f"Deepgram HTTP {r.status_code}: {r.text[:300]}")
    data: dict[str, Any] = r.json()
    return data


# ─────────────────────────── dispatch + запись артефакта ───────────────────────────


def transcribe(wav: Path) -> Transcript:
    """Транскрибировать wav выбранным провайдером (из настроек) → Transcript."""
    if not wav.exists():
        raise JobError(_STAGE, f"нет входного wav: {wav}")
    s = get_settings()
    if s.transcription_provider == "deepgram":
        key = s.deepgram_api_key
        if key is None:
            raise JobError(_STAGE, "нет DEEPGRAM_API_KEY")
        resp = call_deepgram(
            wav, api_key=key, model=s.deepgram_model
        )  # language=None → авто-детект
        return deepgram_to_transcript(resp, default_language="en")
    raise JobError(_STAGE, f"провайдер {s.transcription_provider} ещё не реализован")


def transcribe_to_file(wav: Path, out_path: Path) -> Transcript:
    """transcribe(wav) + запись transcript.json. Возвращает Transcript."""
    t = transcribe(wav)
    out_path.write_text(t.model_dump_json(indent=2), encoding="utf-8")
    return t
