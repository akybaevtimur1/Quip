"""Контракт-тест Stage 1: парсер ест РЕАЛЬНУЮ структуру ответа Deepgram.

Фикстура `tests/fixtures/deepgram_sample.json` — усечённый (15 слов) реальный ответ
Deepgram /v1/listen на нашем сэмпле. Ловит смену формата API до прода (§4Е).
"""

import json
from pathlib import Path

from app.pipeline.stage1_transcribe import deepgram_to_transcript

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "deepgram_sample.json"


def test_real_deepgram_response_parses() -> None:
    resp = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    t = deepgram_to_transcript(resp, default_language="en")

    assert len(t.words) == 15
    assert t.language == "en"
    assert t.duration > 0
    # времена в секундах (а не мс): первое слово начинается в пределах минуты
    assert 0 <= t.words[0].start < 60
    # инварианты: end >= start у каждого, отсортировано по start
    assert all(w.end >= w.start for w in t.words)
    assert [w.start for w in t.words] == sorted(w.start for w in t.words)
    # punctuated_word используется (капитализация/пунктуация)
    assert t.words[0].text == "Hey,"
