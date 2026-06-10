from app.editor.defaults import default_clip_edit
from app.editor.ops import add_section, apply_extend, apply_trim, set_crop_override
from app.models import CropOverride, Segment, Word


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


def test_set_crop_override_replaces_overlapping():
    edit = set_crop_override(
        _base(), CropOverride(source_start=0.0, source_end=1.0, mode="fill", center=0.6)
    )
    assert len(edit.reframe_overrides) == 1
    edit2 = set_crop_override(edit, CropOverride(source_start=0.5, source_end=1.5, mode="fit"))
    assert len(edit2.reframe_overrides) == 1 and edit2.reframe_overrides[0].mode == "fit"
