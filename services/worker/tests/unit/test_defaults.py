from app.editor.defaults import default_clip_edit
from app.models import Segment, Word


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def test_default_clip_edit_from_segment():
    words = [_w("Раз", 5.0, 5.3), _w("два", 5.3, 5.6), _w("три.", 5.6, 6.0), _w("Вне", 99.0, 99.4)]
    seg = Segment(start=5.0, end=7.0, reason="хук", score=0.8, type="hook")
    edit = default_clip_edit("clip_01", seg, words)
    assert edit.id == "clip_01"
    assert edit.version == 1
    assert len(edit.source_intervals) == 1
    assert edit.source_intervals[0].source_start == 5.0
    assert edit.source_intervals[0].source_end == 7.0
    assert edit.reframe_overrides == []
    # слово "Вне" (t=99) вне сегмента → не попало в реплики
    all_refs = [i for r in edit.captions.replies for i in r.word_refs]
    assert 3 not in all_refs and all_refs == [0, 1, 2]
