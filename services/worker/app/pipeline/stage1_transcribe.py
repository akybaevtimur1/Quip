"""Stage 1 (Transcribe): source.wav → transcript.json (Transcript, word-level, секунды).

Провайдеры взаимозаменяемы (Deepgram/Groq) — downstream видит только Transcript.
Deepgram отдаёт СЕКУНДЫ с diarization; Groq — секунды без diarization.

Маршрутизация:
  language=kk (казахский) + TRANSCRIPTION_PROVIDER=deepgram → авто-переключение на Groq,
  т.к. Deepgram возвращает HTTP 400 для kk. Другие языки → Deepgram (авто-детект).
  TRANSCRIPTION_PROVIDER=groq → Groq для ВСЕХ языков (ручное переключение).

Границы: deepgram_to_transcript / groq_to_transcript — pure (ответ → Transcript),
покрыты unit-тестами. Сетевые вызовы (call_deepgram / call_groq) — тонкие обёртки
над REST; при сбое кидают JobError (правило №8).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.errors import JobError
from app.models import Transcript, Word

_STAGE = "transcribe"
_DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Deepgram Nova-3 pre-recorded, pay-as-you-go.
DEEPGRAM_NOVA_USD_PER_MIN = 0.0043  # ≈$0.258/hr

# Groq Whisper, pay-as-you-go (cheaper than Deepgram for supported languages).
GROQ_TURBO_USD_PER_MIN = 0.000667  # whisper-large-v3-turbo: $0.04/hr
GROQ_LARGE_USD_PER_MIN = 0.00185  # whisper-large-v3: $0.111/hr

# Languages that Deepgram doesn't support (returns HTTP 400) → auto-route to Groq.
# kk = Kazakh: misidentified as Turkish or returns 0 words on auto-detect.
DEEPGRAM_UNSUPPORTED: frozenset[str] = frozenset({"kk"})


# ─────────────────────────── pure-нормализация (unit-тесты) ───────────────────────────


def deepgram_to_transcript(resp: dict[str, Any], *, default_language: str = "en") -> Transcript:
    """Сырой ответ Deepgram REST → Transcript (секунды, punctuated_word, сортировка по start).

    JobError при неожиданной структуре или нуле слов.
    """
    try:
        channel = resp["results"]["channels"][0]
        raw_words = channel["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError) as e:
        raise JobError(_STAGE, f"unexpected Deepgram response structure: {e}") from e

    words: list[Word] = []
    for w in raw_words:
        try:
            text = w.get("punctuated_word") or w["word"]
            start = float(w["start"])
            end = float(w["end"])
        except (KeyError, TypeError, ValueError) as e:
            raise JobError(_STAGE, f"malformed word in Deepgram response: {e}") from e
        conf = w.get("confidence")
        spk = w.get("speaker")
        words.append(
            Word(
                text=text,
                start=start,
                end=end,
                confidence=float(conf) if conf is not None else None,
                speaker=int(spk) if spk is not None else None,
            )
        )
    if not words:
        raise JobError(_STAGE, "Deepgram returned 0 words")
    words.sort(key=lambda x: x.start)

    language: str = channel.get("detected_language") or default_language
    raw_dur = (resp.get("metadata") or {}).get("duration")
    if raw_dur is None:
        raise JobError(_STAGE, "Deepgram did not return metadata.duration")
    try:
        duration = float(raw_dur)
    except (TypeError, ValueError) as e:
        raise JobError(_STAGE, f"malformed metadata.duration {raw_dur!r}: {e}") from e
    return Transcript(language=language, duration=duration, words=words)


def groq_to_transcript(resp: dict[str, Any], *, default_language: str = "kk") -> Transcript:
    """Groq verbose_json → Transcript (секунды, сортировка по start).

    Groq отдаёт секунды (как Deepgram). Нет confidence и diarization — Whisper не поддерживает.
    `language` в ответе — полное английское слово ("Kazakh"), используем default_language (ISO-код).
    JobError при неожиданной структуре или нуле слов.
    """
    try:
        raw_words = resp.get("words") or []
        raw_dur = resp.get("duration")
    except (KeyError, TypeError) as e:
        raise JobError(_STAGE, f"unexpected Groq response structure: {e}") from e

    if raw_dur is None:
        raise JobError(_STAGE, "Groq did not return duration")

    words: list[Word] = []
    for w in raw_words:
        try:
            text = w["word"]
            start = float(w["start"])
            end = float(w["end"])
        except (KeyError, TypeError, ValueError) as e:
            raise JobError(_STAGE, f"malformed word in Groq response: {e}") from e
        words.append(Word(text=text, start=start, end=end))

    if not words:
        raise JobError(_STAGE, "Groq returned 0 words")
    words.sort(key=lambda x: x.start)
    return Transcript(language=default_language, duration=float(raw_dur), words=words)


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
        # D2: диаризация ВКЛ → per-word speaker. Нужна, чтобы конец клипа не захватывал реплику
        # ДРУГОГО спикера (snap_end_index учитывает смену спикера). Включено в Nova-3 без доп.цены.
        "diarize": "true",
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
            # write=None: без лимита на upload (3h WAV ≈ 350МБ). read=600: длинное аудио Deepgram
            # обрабатывает дольше — 300s мог преждевременно оборвать обработку 3-часовика.
            timeout=httpx.Timeout(connect=30.0, write=None, read=600.0, pool=5.0),
        )
    except httpx.HTTPError as e:
        raise JobError(_STAGE, f"Deepgram network error: {e}") from e
    if r.status_code != 200:
        raise JobError(_STAGE, f"Deepgram HTTP {r.status_code}: {r.text[:300]}")
    data: dict[str, Any] = r.json()
    return data


# ─────────────────────────── провайдер Groq/Whisper (REST через httpx) ───────────────────────────


def _prepare_audio_for_groq(wav: Path) -> tuple[bytes, str, str]:
    """WAV → (bytes, filename, mime). Компрессирует в MP3 если WAV > 90 МБ (лимит Groq 100 МБ)."""
    if wav.stat().st_size <= 90 * 1024 * 1024:
        return wav.read_bytes(), "audio.wav", "audio/wav"

    # WAV > 90 МБ (> ~47 мин при 16kHz mono) → сжать в MP3 32kbps через ffmpeg.
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
        mp3_path = Path(tf.name)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(wav),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-ab",
                "32k",
                str(mp3_path),
            ],
            capture_output=True,
            check=True,
        )
        return mp3_path.read_bytes(), "audio.mp3", "audio/mpeg"
    except subprocess.CalledProcessError as e:
        raise JobError(_STAGE, f"ffmpeg compress for Groq failed: {e.stderr.decode()[:200]}") from e
    finally:
        mp3_path.unlink(missing_ok=True)


def call_groq(wav: Path, *, api_key: str, model: str, language: str) -> dict[str, Any]:
    """POST audio в Groq Whisper (OpenAI-совместимый REST). Возвращает verbose_json.

    language: ISO-код (kk, ru, en…) — всегда явный (Groq-путь = у нас всегда есть хинт).
    """
    audio_bytes, filename, mime = _prepare_audio_for_groq(wav)
    try:
        r = httpx.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": model,
                "language": language,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
            },
            files={"file": (filename, audio_bytes, mime)},
            timeout=httpx.Timeout(connect=30.0, write=None, read=300.0, pool=5.0),
        )
    except httpx.HTTPError as e:
        raise JobError(_STAGE, f"Groq network error: {e}") from e
    if r.status_code != 200:
        raise JobError(_STAGE, f"Groq HTTP {r.status_code}: {r.text[:300]}")
    data: dict[str, Any] = r.json()
    return data


# ─────────────────────────── dispatch + запись артефакта ───────────────────────────


def transcribe(wav: Path, *, language: str | None = None) -> Transcript:
    """Транскрибировать wav → Transcript.

    language — ISO-код языка пользователя (опц.):
      - kk (казахский): авто-роутинг на Groq (Deepgram вернёт HTTP 400).
      - Другие / None: Deepgram с авто-детектом или явным хинтом.
      - TRANSCRIPTION_PROVIDER=groq: всегда Groq вне зависимости от языка.
    """
    if not wav.exists():
        raise JobError(_STAGE, f"no input wav: {wav}")
    s = get_settings()
    provider = s.transcription_provider

    # Авто-роутинг: языки, не поддерживаемые Deepgram → Groq (если ключ задан).
    if language in DEEPGRAM_UNSUPPORTED and provider == "deepgram":
        if not s.groq_api_key:
            raise JobError(
                _STAGE,
                f"language '{language}' is not supported by Deepgram; "
                "set GROQ_API_KEY to enable Groq transcription for this language",
            )
        provider = "groq"

    if provider == "groq":
        key = s.groq_api_key
        if key is None:
            raise JobError(_STAGE, "GROQ_API_KEY is not set")
        resp = call_groq(wav, api_key=key, model=s.groq_model, language=language or "kk")
        return groq_to_transcript(resp, default_language=language or "kk")

    if provider == "deepgram":
        key = s.deepgram_api_key
        if key is None:
            raise JobError(_STAGE, "DEEPGRAM_API_KEY is not set")
        resp = call_deepgram(wav, api_key=key, model=s.deepgram_model, language=language)
        return deepgram_to_transcript(resp, default_language=language or "en")

    raise JobError(_STAGE, f"provider {provider} is not implemented yet")


def transcribe_to_file(wav: Path, out_path: Path, *, language: str | None = None) -> Transcript:
    """transcribe(wav) + запись transcript.json. Возвращает Transcript."""
    t = transcribe(wav, language=language)
    out_path.write_text(t.model_dump_json(indent=2), encoding="utf-8")
    return t
