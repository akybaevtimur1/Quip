"""Тесты pure-логики Stage 4 (субтитры ASS) — тест-первым.

Баг-опасные места (R3): t_clip = t_source - segment.start (рассинхрон ±длина клипа),
группировка слов в чанки, формат времени ASS. Всё детерминированно.
"""

from app.models import Word
from app.pipeline.stage4_captions import (
    build_ass,
    escape_ass_text,
    format_ass_time,
    group_words_into_chunks,
    to_clip_time,
    words_in_segment,
)


def mk(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


class TestToClipTime:
    def test_subtracts_segment_start(self) -> None:
        assert to_clip_time(124.5, 120.0) == 4.5

    def test_clamps_negative_to_zero(self) -> None:
        assert to_clip_time(119.9, 120.0) == 0.0


class TestFormatAssTime:
    def test_zero(self) -> None:
        assert format_ass_time(0.0) == "0:00:00.00"

    def test_subsecond(self) -> None:
        assert format_ass_time(1.5) == "0:00:01.50"

    def test_minutes(self) -> None:
        assert format_ass_time(65.25) == "0:01:05.25"

    def test_hours(self) -> None:
        assert format_ass_time(3661.07) == "1:01:01.07"


class TestWordsInSegment:
    def test_filters_to_window(self) -> None:
        words = [mk("a", 0.0, 0.4), mk("b", 5.0, 5.4), mk("c", 9.9, 10.2)]
        got = words_in_segment(words, 5.0, 9.0)
        assert [w.text for w in got] == ["b"]


class TestGroupWords:
    def test_max_words_split(self) -> None:
        words = [mk(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(6)]
        chunks = group_words_into_chunks(words, max_words=5, max_gap=0.4, max_dur=2.5)
        assert [len(c.words) for c in chunks] == [5, 1]

    def test_break_on_sentence_end(self) -> None:
        words = [mk("A", 0.0, 0.3), mk("b.", 0.3, 0.6), mk("C", 0.6, 0.9)]
        chunks = group_words_into_chunks(words)
        assert [[w.text for w in c.words] for c in chunks] == [["A", "b."], ["C"]]

    def test_break_on_gap(self) -> None:
        words = [mk("A", 0.0, 0.3), mk("B", 1.0, 1.3)]  # пауза 0.7с > 0.4
        chunks = group_words_into_chunks(words, max_gap=0.4)
        assert len(chunks) == 2

    def test_break_on_duration(self) -> None:
        # длинные слова: к 3-му длительность чанка > 2.5с
        words = [mk("A", 0.0, 1.0), mk("B", 1.0, 2.0), mk("C", 2.0, 3.0)]
        chunks = group_words_into_chunks(words, max_words=5, max_gap=5.0, max_dur=2.5)
        assert len(chunks) >= 2

    def test_chunk_times_from_first_last(self) -> None:
        words = [mk("A", 1.0, 1.3), mk("B", 1.3, 1.7)]
        chunk = group_words_into_chunks(words)[0]
        assert chunk.start == 1.0
        assert chunk.end == 1.7


class TestBuildAss:
    def _seg_words(self) -> list[Word]:
        # сегмент начинается в 120с; первое слово ровно в начале клипа
        return [mk("Hello", 120.0, 120.4), mk("world.", 120.4, 120.9)]

    def test_has_header_and_style(self) -> None:
        ass = build_ass(self._seg_words(), segment_start=120.0)
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass
        assert "Montserrat" in ass
        assert "[Events]" in ass

    def test_first_dialogue_is_clip_relative(self) -> None:
        ass = build_ass(self._seg_words(), segment_start=120.0)
        # первое слово в 120.0 → клип-время 0:00:00.00, НЕ source-время
        assert "Dialogue: 0,0:00:00.00," in ass

    def test_text_uppercased(self) -> None:
        ass = build_ass(self._seg_words(), segment_start=120.0)
        assert "HELLO WORLD." in ass


class TestEscapeAssText:
    def test_escapes_braces(self) -> None:
        # {...} = override-блок libass (текст молча пропадает) → экранируем в литералы
        assert escape_ass_text("a {x} b") == "a \\{x\\} b"

    def test_neutralizes_backslash(self) -> None:
        # \N/\n/\h вне блока = перенос/хард-пробел → подмена на безопасный глиф U+29F5
        assert escape_ass_text("a\\Nb") == "a⧵Nb"

    def test_backslash_escaped_before_braces(self) -> None:
        # порядок: бэкслеш ПЕРВЫМ, иначе затёр бы наши же \{ \}
        assert escape_ass_text("{") == "\\{"
        assert escape_ass_text("\\{") == "⧵\\{"

    def test_plain_text_untouched(self) -> None:
        assert escape_ass_text("Привет мир!") == "Привет мир!"

    def test_build_ass_escapes_caption_braces(self) -> None:
        words = [mk("{laughs}", 120.0, 120.4)]
        ass = build_ass(words, segment_start=120.0)
        d = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
        assert "\\{LAUGHS\\}" in d
