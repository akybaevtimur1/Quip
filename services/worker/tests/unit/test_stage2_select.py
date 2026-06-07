"""Тесты pure-постобработки Stage 2 (выбор моментов) — ядро качества, тест-первым.

Баг-опасные места (план §4А B): маппинг индексов слов → секунды, snap-to-sentence,
длительность-гейт, разрешение пересечений, клиппинг score. Всё детерминированно.
"""

import pytest

from app.errors import JobError
from app.models import ClipType, Word
from app.pipeline.stage2_select import (
    clamp_score,
    indices_to_times,
    postprocess,
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
