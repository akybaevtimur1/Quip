import pytest

from app.editor.defaults import default_clip_edit
from app.editor.ops import (
    add_section,
    apply_extend,
    apply_trim,
    set_crop_override,
    set_interval,
)
from app.errors import JobError
from app.models import CropOverride, Segment, SourceInterval, Word


def _w(t, s, e):
    return Word(text=t, start=s, end=e)


WORDS = [
    _w("a", 0.0, 0.4),
    _w("b", 0.4, 0.8),
    _w("c", 1.0, 1.4),
    _w("d", 1.4, 1.8),
    _w("e", 2.0, 2.4),
]


def _base(end=3.0):
    seg = Segment(start=0.0, end=end, reason="r", score=0.5, type="hook")
    return default_clip_edit("clip_01", seg, WORDS)


def test_apply_trim_makes_hole():
    out = apply_trim(_base(), [2, 3], WORDS)  # вырезать c,d → диапазон [1.0,1.8]
    bounds = [(i.source_start, i.source_end) for i in out.source_intervals]
    assert bounds == [(0.0, 1.0), (1.8, 3.0)]
    refs = [i for r in out.captions.replies for i in r.word_refs]
    assert 2 not in refs and 3 not in refs


def test_add_section_inserts_interval_and_words():
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)  # интервал [0,1] → слова a,b
    out = add_section(edit, 2.0, 2.5, 1, WORDS)  # добавить [2.0,2.5] → слово e
    assert len(out.source_intervals) == 2
    assert 4 in [i for r in out.captions.replies for i in r.word_refs]


def test_apply_extend_end_grows_interval():
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)
    out = apply_extend(edit, edge="end", new_value=2.5, words=WORDS)
    assert out.source_intervals[-1].source_end == 2.5
    refs = [i for r in out.captions.replies for i in r.word_refs]
    assert 2 in refs and 3 in refs  # c,d попали в расширенный интервал


def test_apply_trim_empty_indices_raises_joberror():
    # пустой список слов → min()/max() падали ValueError (500). Должен быть явный JobError.
    with pytest.raises(JobError):
        apply_trim(_base(), [], WORDS)


def test_apply_trim_out_of_range_index_raises_joberror():
    with pytest.raises(JobError):
        apply_trim(_base(), [99], WORDS)


def test_apply_extend_invalid_edge_raises_joberror():
    # любой edge != "start"/"end" раньше ТИХО менял конец (silent fallback, правило №8).
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)
    with pytest.raises(JobError):
        apply_extend(edit, edge="START", new_value=2.5, words=WORDS)


def test_apply_extend_start_past_end_raises_joberror():
    # extend start за пределы конца → инвертированный интервал (start>=end).
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)
    with pytest.raises(JobError):
        apply_extend(edit, edge="start", new_value=2.0, words=WORDS)


def test_add_section_inverted_range_raises_joberror():
    seg = Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook")
    edit = default_clip_edit("clip_01", seg, WORDS)
    with pytest.raises(JobError):
        add_section(edit, 2.5, 2.0, 1, WORDS)


def test_add_section_overlapping_range_raises_joberror():
    # интервал [0,3] уже есть; новый [1,4] пересекается → дублировал бы слова. Запрещаем.
    with pytest.raises(JobError):
        add_section(_base(), 1.0, 4.0, 1, WORDS)


def test_set_interval_shift_remaps_captions_to_new_window():
    # W4: сдвиг клипа на таймлайне (set_interval) ОБЯЗАН пересобрать субтитры под новый набор
    # слов — старые выпадают, новые появляются (founder: «проверь, что субтитры перегенерятся
    # при сдвиге»). Единая точка синхронизации = rebuild_replies в _with_intervals.
    edit = _base(end=3.0)  # [0,3] → все a..e
    assert sorted({i for r in edit.captions.replies for i in r.word_refs}) == [0, 1, 2, 3, 4]
    shifted = set_interval(edit, 2.0, 2.5, WORDS, duration=3.0, min_sec=0.0, max_sec=10.0)
    refs = sorted({i for r in shifted.captions.replies for i in r.word_refs})
    assert refs == [4]  # только 'e' (2.0-2.4) в новом окне; старые слова выпали
    assert shifted.source_intervals == [SourceInterval(source_start=2.0, source_end=2.5)]


def test_set_crop_override_replaces_overlapping():
    edit = set_crop_override(
        _base(), CropOverride(source_start=0.0, source_end=1.0, mode="fill", center=0.6)
    )
    assert len(edit.reframe_overrides) == 1
    edit2 = set_crop_override(edit, CropOverride(source_start=0.5, source_end=1.5, mode="fit"))
    assert len(edit2.reframe_overrides) == 1 and edit2.reframe_overrides[0].mode == "fit"
