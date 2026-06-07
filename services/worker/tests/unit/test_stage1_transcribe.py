"""Тесты pure-нормализации Stage 1: ответ Deepgram REST → Transcript.

Багоопасное место — единицы времени (секунды, не мс), выбор punctuated_word и
сортировка слов. Синтетическая фикстура повторяет форму Deepgram /v1/listen.
"""

from typing import Any

import pytest

from app.errors import JobError
from app.pipeline.stage1_transcribe import deepgram_to_transcript


def _resp(words: list[dict[str, Any]], duration: float = 12.5) -> dict[str, Any]:
    return {
        "metadata": {"duration": duration, "channels": 1},
        "results": {
            "channels": [
                {"alternatives": [{"transcript": "...", "confidence": 0.99, "words": words}]}
            ]
        },
    }


def test_words_normalized_in_seconds_with_punctuation() -> None:
    resp = _resp(
        [
            {"word": "so", "start": 0.1, "end": 0.4, "confidence": 0.98, "punctuated_word": "So"},
            {
                "word": "yeah",
                "start": 0.5,
                "end": 0.9,
                "confidence": 0.95,
                "punctuated_word": "yeah.",
            },
        ]
    )
    t = deepgram_to_transcript(resp)
    assert len(t.words) == 2
    assert t.words[0].text == "So"  # punctuated_word, не raw "so"
    assert t.words[1].text == "yeah."
    assert t.words[0].start == 0.1 and t.words[0].end == 0.4  # секунды, не мс
    assert t.words[0].confidence == 0.98
    assert t.duration == 12.5


def test_words_get_sorted_by_start() -> None:
    resp = _resp(
        [
            {"word": "b", "start": 5.0, "end": 5.4, "punctuated_word": "B"},
            {"word": "a", "start": 1.0, "end": 1.4, "punctuated_word": "A"},
        ]
    )
    t = deepgram_to_transcript(resp)
    assert [w.text for w in t.words] == ["A", "B"]


def test_falls_back_to_raw_word_when_no_punctuated() -> None:
    resp = _resp([{"word": "hello", "start": 0.0, "end": 0.5}])
    t = deepgram_to_transcript(resp)
    assert t.words[0].text == "hello"
    assert t.words[0].confidence is None


def test_default_language_used() -> None:
    t = deepgram_to_transcript(
        _resp([{"word": "x", "start": 0.0, "end": 0.1}]), default_language="en"
    )
    assert t.language == "en"


def test_detected_language_overrides_default() -> None:
    resp = _resp([{"word": "x", "start": 0.0, "end": 0.1}])
    resp["results"]["channels"][0]["detected_language"] = "ru"
    t = deepgram_to_transcript(resp, default_language="en")
    assert t.language == "ru"


def test_empty_words_raises() -> None:
    with pytest.raises(JobError):
        deepgram_to_transcript(_resp([]))


def test_malformed_structure_raises() -> None:
    with pytest.raises(JobError):
        deepgram_to_transcript({"results": {}})
