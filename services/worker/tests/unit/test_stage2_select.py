"""Тесты pure-постобработки Stage 2 (выбор моментов) — ядро качества, тест-первым.

Баг-опасные места (план §4А B): маппинг индексов слов → секунды, snap-to-sentence,
длительность-гейт, разрешение пересечений, клиппинг score. Всё детерминированно.
"""

import pytest

from app.errors import JobError
from app.models import ClipType, Transcript, Word
from app.pipeline.stage2_select import (
    _backoff_delay,
    build_indexed_transcript,
    build_user_prompt,
    clamp_score,
    indices_to_times,
    is_transient_gemini_error,
    pad_clip_end,
    postprocess,
    resolve_max_clips,
    resolve_overlaps,
    snap_end_index,
    snap_start_index,
)


def mkwords(specs: list[tuple[str, float, float]]) -> list[Word]:
    return [Word(text=t, start=s, end=e) for (t, s, e) in specs]


# равномерные слова: индекс k → [k, k+0.8]; "Sn." заканчивает предложение
def uniform(n: int, sentence_ends: set[int] | None = None) -> list[Word]:
    ends = sentence_ends or set()
    return [
        Word(text=(f"w{k}." if k in ends else f"w{k}"), start=float(k), end=float(k) + 0.8)
        for k in range(n)
    ]


class TestClampScore:
    def test_above_one(self) -> None:
        assert clamp_score(1.5) == 1.0

    def test_below_zero(self) -> None:
        assert clamp_score(-0.2) == 0.0

    def test_inside(self) -> None:
        assert clamp_score(0.5) == 0.5


class TestResolveMaxClips:
    """Сколько кандидатов отдавать: запрос юзера (UI-степпер) > дефолт, с клампом в диапазон."""

    def test_none_falls_back_to_default(self) -> None:
        assert resolve_max_clips(None, 8) == 8

    def test_request_overrides_default(self) -> None:
        assert resolve_max_clips(3, 8) == 3

    def test_clamps_below_lo(self) -> None:
        assert resolve_max_clips(0, 8, lo=1, hi=12) == 1

    def test_clamps_above_hi(self) -> None:
        assert resolve_max_clips(99, 8, lo=1, hi=12) == 12

    def test_default_cap_is_30(self) -> None:
        # Прод-потолок «как найдётся, максимум 30» (UI Auto-режим шлёт 30).
        assert resolve_max_clips(99, 8) == 30
        assert resolve_max_clips(30, 8) == 30


class TestIsTransientGeminiError:
    """Ретраить ТОЛЬКО транзиентные сбои Gemini (free-tier 429 / 5xx / сеть);
    перманентные (401/403/404/400 — ключ/модель/схема) ронять сразу, не маскируя 60с бэкоффа."""

    def _api_error(self, code: int) -> Exception:
        from google.genai import errors

        # APIError.__init__(code, response_json, response=None); message из response_json
        return errors.APIError(code, {"error": {"message": "boom", "status": "X"}})

    def test_429_rate_limit_is_transient(self) -> None:
        assert is_transient_gemini_error(self._api_error(429)) is True

    def test_503_unavailable_is_transient(self) -> None:
        assert is_transient_gemini_error(self._api_error(503)) is True

    def test_500_server_error_is_transient(self) -> None:
        assert is_transient_gemini_error(self._api_error(500)) is True

    def test_401_auth_is_permanent(self) -> None:
        assert is_transient_gemini_error(self._api_error(401)) is False

    def test_403_permission_is_permanent(self) -> None:
        assert is_transient_gemini_error(self._api_error(403)) is False

    def test_404_bad_model_is_permanent(self) -> None:
        assert is_transient_gemini_error(self._api_error(404)) is False

    def test_400_bad_request_is_permanent(self) -> None:
        assert is_transient_gemini_error(self._api_error(400)) is False

    def test_network_timeout_is_transient(self) -> None:
        import httpx

        assert is_transient_gemini_error(httpx.ReadTimeout("slow")) is True
        assert is_transient_gemini_error(httpx.ConnectError("down")) is True

    def test_unknown_exception_is_transient_by_default(self) -> None:
        # неизвестный тип → лучше ретрайнуть (консервативно), чем уронить из-за классификации
        assert is_transient_gemini_error(RuntimeError("???")) is True


class TestIndicesToTimes:
    def test_maps_to_word_boundaries(self) -> None:
        words = uniform(10)
        start, end = indices_to_times(words, 2, 5)
        assert start == 2.0  # words[2].start
        assert end == 5.8  # words[5].end

    def test_out_of_range_raises(self) -> None:
        words = uniform(5)
        with pytest.raises(JobError):
            indices_to_times(words, 0, 10)
        with pytest.raises(JobError):
            indices_to_times(words, -1, 3)

    def test_start_after_end_raises(self) -> None:
        words = uniform(5)
        with pytest.raises(JobError):
            indices_to_times(words, 4, 2)


class TestSnapEnd:
    def test_extends_to_next_sentence_end(self) -> None:
        words = uniform(10, sentence_ends={4})
        # конец на idx2 (не конец предложения) → тянем до idx4 ("w4.")
        assert snap_end_index(words, 2, max_extend=5) == 4

    def test_no_change_if_already_sentence_end(self) -> None:
        words = uniform(10, sentence_ends={2})
        assert snap_end_index(words, 2, max_extend=5) == 2

    def test_no_change_if_none_within_window(self) -> None:
        words = uniform(10, sentence_ends={9})
        # с idx2 до idx9 семь слов — за пределом окна 5 → без изменений
        assert snap_end_index(words, 2, max_extend=5) == 2


class TestSnapEndPause:
    """W1: при отсутствии .?! в окне — снап конца к ПАУЗЕ по word-таймингам (чистый вдох),
    а не резать посреди фразы. .?! приоритетнее паузы."""

    def test_snaps_to_pause_when_no_sentence_end(self) -> None:
        # нет .?!; ясная пауза 1.0с после idx3 → конец снапается к idx3 (вдох)
        words = mkwords(
            [
                ("a", 0.0, 0.5),
                ("b", 0.5, 1.0),
                ("c", 1.0, 1.5),
                ("d", 1.5, 2.0),  # idx3 заканчивается на 2.0
                ("e", 3.0, 3.5),  # пауза 1.0с после idx3
                ("f", 3.5, 4.0),
            ]
        )
        assert snap_end_index(words, 2, max_extend=5, min_pause=0.35) == 3

    def test_prefers_sentence_end_over_pause(self) -> None:
        words = mkwords(
            [
                ("a", 0.0, 0.5),
                ("b.", 0.5, 1.0),  # idx1 конец предложения, паузы нет
                ("c", 1.5, 2.0),  # пауза перед c
            ]
        )
        assert snap_end_index(words, 0, max_extend=5, min_pause=0.35) == 1

    def test_no_pause_no_sentence_keeps_index(self) -> None:
        # сплошная речь, нет .?!, нет паузы ≥ порога → без изменений
        words = mkwords([(f"w{k}", k * 0.5, k * 0.5 + 0.45) for k in range(8)])
        assert snap_end_index(words, 2, max_extend=5, min_pause=0.35) == 2

    def test_wider_default_window_finds_far_sentence_end(self) -> None:
        # дефолтное окно расширено (было 5) → .?! на +7 слов теперь достижим
        words = uniform(20, sentence_ends={9})
        assert snap_end_index(words, 2) == 9


class TestPadClipEnd:
    """W1: хвостовой паддинг — добить конец клипа тишиной для чистого лупа,
    но не залезть в следующее слово и не выйти за длительность."""

    def test_pads_into_trailing_silence(self) -> None:
        words = mkwords([("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 5.0, 6.0)])
        assert pad_clip_end(2.0, words, 1, duration=10.0, pad=0.3) == pytest.approx(2.3)

    def test_caps_at_next_word_start(self) -> None:
        words = mkwords([("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 2.1, 3.0)])
        # зазор лишь 0.1с → паддинг кламп к 2.1 (не 2.3) — не залезаем в следующее слово
        assert pad_clip_end(2.0, words, 1, duration=10.0, pad=0.3) == pytest.approx(2.1)

    def test_caps_at_duration_for_last_word(self) -> None:
        words = mkwords([("a", 0.0, 1.0), ("b", 1.0, 2.0)])
        assert pad_clip_end(2.0, words, 1, duration=2.15, pad=0.3) == pytest.approx(2.15)

    def test_zero_pad_is_noop(self) -> None:
        words = mkwords([("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 5.0, 6.0)])
        assert pad_clip_end(2.0, words, 1, duration=10.0, pad=0.0) == 2.0

    def test_never_shortens_on_overlapping_timings(self) -> None:
        # ASR иногда отдаёт ПЕРЕКРЫВАЮЩИЕСЯ тайминги: next.start < current.end (поймано на
        # реальном 1ч-видео). Паддинг НЕ должен укорачивать клип (резать конечное слово) —
        # кламп к next_start не может уйти раньше конца слова.
        words = mkwords([("a", 0.0, 1.0), ("end.", 1.0, 3.0), ("next", 2.0, 2.5)])
        assert pad_clip_end(3.0, words, 1, duration=100.0, pad=0.3) >= 3.0


class TestHookRegen:
    """W4: одноразовая перегенерация хука под новый интервал (узкий Gemini-вызов, не чат)."""

    def test_build_prompt_includes_text_duration_and_styles(self) -> None:
        from app.pipeline.stage2_select import build_hook_regen_prompt

        prompt = build_hook_regen_prompt("привет это клип про деньги", language="ru", duration=23.0)
        assert "привет это клип про деньги" in prompt
        assert "23" in prompt
        assert "hook_style" in prompt.lower()

    def test_parse_response_returns_hook_and_normalized_style(self) -> None:
        import json

        from app.pipeline.stage2_select import parse_hook_response

        text = json.dumps({"tone": "shock", "hook_style": "  SHOCK ", "hook": "  Он потерял всё "})
        hook, style = parse_hook_response(text)
        assert hook == "Он потерял всё"
        assert style == "shock"

    def test_parse_response_empty_style_is_none(self) -> None:
        import json

        from app.pipeline.stage2_select import parse_hook_response

        hook, style = parse_hook_response(json.dumps({"hook": "Текст", "hook_style": ""}))
        assert hook == "Текст"
        assert style is None

    def test_parse_response_missing_hook_raises(self) -> None:
        import json

        from app.errors import JobError
        from app.pipeline.stage2_select import parse_hook_response

        with pytest.raises(JobError):
            parse_hook_response(json.dumps({"hook_style": "pov", "hook": "   "}))

    def test_parse_response_bad_json_raises(self) -> None:
        from app.errors import JobError
        from app.pipeline.stage2_select import parse_hook_response

        with pytest.raises(JobError):
            parse_hook_response("not json{")


class TestSystemPromptV2:
    """W2: системный промпт вынесен в файл v2 (версионируем без передеплоя) и описывает
    двухступенчатую генерацию хука (тон → стиль → текст)."""

    def test_prompt_path_is_v2(self) -> None:
        from app.pipeline.stage2_select import _PROMPT_PATH

        assert _PROMPT_PATH.name == "select_moments.v2.txt"

    def test_v2_file_exists_and_describes_hook_styles(self) -> None:
        from app.pipeline.stage2_select import _PROMPT_PATH

        assert _PROMPT_PATH.exists(), "prompts/select_moments.v2.txt должен существовать"
        text = _PROMPT_PATH.read_text(encoding="utf-8").lower()
        assert "hook_style" in text
        # перечислены стили нового брифа (story/insight/question/bold_claim/number; POV выпилен)
        for style in ("story", "insight", "question", "bold_claim", "number"):
            assert style in text

    def test_load_system_prompt_reads_v2_file(self) -> None:
        from app.pipeline.stage2_select import load_system_prompt

        assert "hook_style" in load_system_prompt().lower()


class TestBuildUserPromptLength:
    """W1: реальные clip_min/max_sec уходят в промпт как ЖЁСТКИЙ лимит (модель обязана соблюсти)."""

    def test_includes_hard_length_limits(self) -> None:
        words = uniform(20)
        tr = Transcript(language="en", duration=20.0, words=words)
        indexed = build_indexed_transcript(words)
        prompt = build_user_prompt("title", tr, indexed, max_clips=5, min_sec=15, max_sec=45)
        assert "45" in prompt
        assert "15" in prompt
        assert "second" in prompt.lower()


class TestSnapStart:
    def test_moves_to_sentence_start(self) -> None:
        words = uniform(10, sentence_ends={0})
        # idx0 "w0." заканчивает предложение → начало след. предложения = idx1
        assert snap_start_index(words, 3, max_extend=5) == 1

    def test_no_change_if_already_at_sentence_start(self) -> None:
        words = uniform(10, sentence_ends={1})
        # words[1] заканчивает предложение → idx2 уже начало предложения
        assert snap_start_index(words, 2, max_extend=5) == 2

    def test_zero_index_stays(self) -> None:
        words = uniform(10)
        assert snap_start_index(words, 0, max_extend=5) == 0

    def test_skips_dangling_tail_to_next_sentence(self) -> None:
        # старт на ХВОСТЕ длинного предложения (само слово завершает его, а начало
        # предложения недостижимо назад в окне) → уходим в начало след. предложения.
        # Это баг «Антимошенника»: клип не должен начинаться с последнего слова мысли.
        words = uniform(20, sentence_ends={9})  # [9] завершает предложение, назад в 5 концов нет
        assert snap_start_index(words, 9, max_extend=5) == 10

    def test_preserves_short_opening_sentence(self) -> None:
        # [4] завершает предыдущее предложение → [5] уже чистый старт короткого
        # предложения "w5 w6 w7." — НЕ перепрыгиваем его (иначе теряем короткий хук).
        words = uniform(20, sentence_ends={4, 7})
        assert snap_start_index(words, 5, max_extend=5) == 5


class TestResolveOverlaps:
    def _seg(self, start: float, end: float, score: float) -> object:
        from app.models import Segment

        return Segment(start=start, end=end, reason="r", score=score, type=ClipType.hook)

    def test_keeps_higher_score_on_overlap(self) -> None:
        from app.models import Segment

        a = Segment(start=0, end=20, reason="r", score=0.9, type=ClipType.hook)
        b = Segment(start=10, end=30, reason="r", score=0.5, type=ClipType.hook)  # overlaps a
        out = resolve_overlaps([a, b])
        assert len(out) == 1
        assert out[0].score == 0.9

    def test_keeps_all_when_disjoint(self) -> None:
        from app.models import Segment

        a = Segment(start=0, end=20, reason="r", score=0.5, type=ClipType.hook)
        b = Segment(start=25, end=45, reason="r", score=0.9, type=ClipType.hook)
        out = resolve_overlaps([a, b])
        assert len(out) == 2
        assert [s.start for s in out] == [0, 25]  # отсортировано по start


class TestPostprocess:
    def test_happy_path_snaps_gates_and_validates(self) -> None:
        words = uniform(40, sentence_ends={2, 25})
        raw = [
            {
                "start_word_index": 3,
                "end_word_index": 22,
                "reason": "  concrete why  ",
                "score": 1.4,  # клип в 1.0
                "type": "hook",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60)
        assert len(segs) == 1
        s = segs[0]
        assert s.score == 1.0  # клипнут
        assert s.reason == "concrete why"  # тримнут
        assert s.type is ClipType.hook
        # start снэпнут к началу предложения (после w2.) = idx3 -> остаётся 3 (idx2 конец)
        assert s.start == 3.0
        # end снэпнут к w25. = idx25 -> end = 25.8
        assert s.end == 25.8

    def test_drops_too_short(self) -> None:
        words = uniform(40)
        raw = [
            {
                "start_word_index": 0,
                "end_word_index": 5,
                "reason": "r",
                "score": 0.9,
                "type": "hook",
            }
        ]
        assert postprocess(raw, words, min_sec=15, max_sec=60) == []

    def test_drops_too_long(self) -> None:
        words = mkwords([("a", 0.0, 0.5), ("b", 70.0, 70.5)])
        raw = [
            {
                "start_word_index": 0,
                "end_word_index": 1,
                "reason": "r",
                "score": 0.9,
                "type": "hook",
            }
        ]
        assert postprocess(raw, words, min_sec=15, max_sec=60) == []

    def test_drops_invalid_type(self) -> None:
        words = uniform(40)
        raw = [
            {
                "start_word_index": 0,
                "end_word_index": 20,
                "reason": "r",
                "score": 0.9,
                "type": "bogus",
            }
        ]
        assert postprocess(raw, words, min_sec=15, max_sec=60) == []

    def test_caps_to_max_clips_by_score(self) -> None:
        words = uniform(120)
        raw = [
            {
                "start_word_index": 0,
                "end_word_index": 20,
                "reason": "a",
                "score": 0.5,
                "type": "hook",
            },
            {
                "start_word_index": 25,
                "end_word_index": 45,
                "reason": "b",
                "score": 0.9,
                "type": "hook",
            },
            {
                "start_word_index": 50,
                "end_word_index": 70,
                "reason": "c",
                "score": 0.7,
                "type": "hook",
            },
            {
                "start_word_index": 75,
                "end_word_index": 95,
                "reason": "d",
                "score": 0.95,
                "type": "hook",
            },
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60, max_clips=2)
        assert len(segs) == 2
        assert {s.reason for s in segs} == {"b", "d"}  # топ-2 по score
        assert [s.start for s in segs] == sorted(s.start for s in segs)  # сортировка по start

    def test_carries_hook_and_why_works(self) -> None:
        # T1/T2: LLM-поля hook/why_works пробрасываются в Segment (объяснимость как продукт)
        words = uniform(40, sentence_ends={2, 25})
        raw = [
            {
                "start_word_index": 3,
                "end_word_index": 22,
                "reason": "concrete why",
                "score": 0.8,
                "type": "hook",
                "hook": "Он потерял всё за день",
                "why_works": "Ставка и конфликт в первой фразе",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60)
        assert len(segs) == 1
        assert segs[0].hook == "Он потерял всё за день"
        assert segs[0].why_works == "Ставка и конфликт в первой фразе"

    def test_carries_and_normalizes_hook_style(self) -> None:
        # W2: hook_style пробрасывается в Segment и нормализуется (trim + lower).
        words = uniform(40, sentence_ends={2, 25})
        raw = [
            {
                "start_word_index": 3,
                "end_word_index": 22,
                "reason": "r",
                "score": 0.8,
                "type": "hook",
                "hook": "POV: тот самый темщик",
                "hook_style": "  POV  ",
                "why_works": "w",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60)
        assert segs[0].hook_style == "pov"

    def test_missing_hook_style_is_none(self) -> None:
        # старый raw без hook_style → None (обратная совместимость)
        words = uniform(40, sentence_ends={2, 25})
        raw = [
            {
                "start_word_index": 3,
                "end_word_index": 22,
                "reason": "r",
                "score": 0.8,
                "type": "hook",
                "hook": "h",
                "why_works": "w",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60)
        assert segs[0].hook_style is None

    def test_missing_hook_fields_are_none(self) -> None:
        # старый raw без hook/why_works → поля None (не падаем, обратная совместимость)
        words = uniform(40, sentence_ends={2, 25})
        raw = [
            {
                "start_word_index": 3,
                "end_word_index": 22,
                "reason": "r",
                "score": 0.8,
                "type": "hook",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60)
        assert len(segs) == 1
        assert segs[0].hook is None and segs[0].why_works is None

    def test_applies_tail_padding(self) -> None:
        # W1: tail_pad добивает конец тишиной (чистый луп). end snap к w25.→25.8; w26 старт 26.0;
        # pad 0.3 → min(26.1, 26.0) = 26.0.
        words = uniform(40, sentence_ends={2, 25})
        raw = [
            {
                "start_word_index": 3,
                "end_word_index": 22,
                "reason": "r",
                "score": 0.8,
                "type": "hook",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60, duration=100.0, tail_pad=0.3)
        assert len(segs) == 1
        assert segs[0].end == pytest.approx(26.0)

    def test_tail_padding_gate_uses_unpadded_length(self) -> None:
        # Гейт длины считается по РЕЧИ (без паддинга): клип ровно на max_sec проходит,
        # а паддинг (в реальную тишину) потом добавляет хвост сверх max — и НЕ дропает клип.
        words = mkwords(
            [
                ("Start.", 0.0, 0.5),  # idx0 конец предложения → старт снапнется к idx1
                ("a", 1.0, 1.5),  # idx1 — старт клипа = 1.0
                ("end.", 60.5, 61.0),  # idx2 конец → речь = 61.0-1.0 = 60.0 == max
                ("next", 65.0, 65.5),  # 4с тишины после idx2
            ]
        )
        raw = [
            {
                "start_word_index": 1,
                "end_word_index": 2,
                "reason": "r",
                "score": 0.9,
                "type": "hook",
            }
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60, duration=200.0, tail_pad=0.3)
        assert len(segs) == 1  # гейт по речи (60.0) → проходит
        assert segs[0].end == pytest.approx(61.3)  # 61.0 + 0.3 паддинга в тишину

    def test_resolves_overlap_keeping_higher_score(self) -> None:
        words = uniform(60)
        raw = [
            {
                "start_word_index": 0,
                "end_word_index": 20,
                "reason": "a",
                "score": 0.6,
                "type": "hook",
            },
            {
                "start_word_index": 10,
                "end_word_index": 30,
                "reason": "b",
                "score": 0.95,
                "type": "strong_quote",
            },
        ]
        segs = postprocess(raw, words, min_sec=15, max_sec=60)
        assert len(segs) == 1
        assert segs[0].reason == "b"


class TestBackoffDelay:
    """Backoff с jitter: де-коррелирует ретраи параллельных джоб под provider-wide 503."""

    def test_within_bounds_for_attempts_0_to_6(self) -> None:
        # Верхняя граница = min(2**attempt, cap=30); нижняя = 0 (jitter не уходит в минус).
        for attempt in range(7):
            ceil = min(2**attempt, 30)
            for _ in range(200):
                d = _backoff_delay(attempt)
                assert 0.0 <= d <= ceil, f"attempt={attempt}: {d} not in [0, {ceil}]"

    def test_equal_jitter_keeps_minimum_wait(self) -> None:
        # equal-jitter: гарантированный минимум = 0.5 * min(2**attempt, cap).
        for attempt in range(7):
            ceil = min(2**attempt, 30)
            for _ in range(200):
                d = _backoff_delay(attempt)
                assert d >= 0.5 * ceil, f"attempt={attempt}: {d} < {0.5 * ceil}"

    def test_cap_honoured_at_high_attempts(self) -> None:
        # При attempt >> log2(cap) потолок остаётся cap (не растёт экспоненциально дальше).
        for _ in range(200):
            d = _backoff_delay(20)
            assert 15.0 <= d <= 30.0

    def test_decorrelated_not_all_identical(self) -> None:
        # Главная цель фикса: повторные вызовы для одного attempt не совпадают
        # (jitter рассинхронизирует волны ретраев). Детерминированный delay → set размера 1.
        vals = {_backoff_delay(5) for _ in range(50)}
        assert len(vals) > 1
