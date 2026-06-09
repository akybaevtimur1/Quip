from app.editor.replies import default_caption_track, rebuild_replies
from app.models import CaptionReply, SourceInterval, Word


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


WORDS = [
    _w("Привет", 0.0, 0.4),
    _w("мир.", 0.4, 0.8),  # конец предложения → разрыв после
    _w("Это", 1.0, 1.2),
    _w("тест", 1.2, 1.6),
    _w("редактора", 1.6, 2.2),
]


def test_rebuild_full_interval_groups_and_refs():
    intervals = [SourceInterval(source_start=0.0, source_end=3.0)]
    replies = rebuild_replies(WORDS, intervals)
    # "Привет мир." заканчивает предложение → отдельная реплика; затем "Это тест редактора"
    assert [r.word_refs for r in replies] == [[0, 1], [2, 3, 4]]


def test_rebuild_drops_words_in_gap():
    # интервал покрывает только слова 2..4 (1.0..2.2); 0,1 вне → выпадают
    intervals = [SourceInterval(source_start=1.0, source_end=3.0)]
    replies = rebuild_replies(WORDS, intervals)
    assert [r.word_refs for r in replies] == [[2, 3, 4]]


def test_rebuild_preserves_text_override_for_unchanged_refs():
    intervals = [SourceInterval(source_start=0.0, source_end=3.0)]
    keep = [CaptionReply(word_refs=[2, 3, 4], text_override="ИЗМЕНЕНО", hidden=True)]
    replies = rebuild_replies(WORDS, intervals, keep=keep)
    edited = next(r for r in replies if r.word_refs == [2, 3, 4])
    assert edited.text_override == "ИЗМЕНЕНО" and edited.hidden is True


def test_default_caption_track_defaults_on():
    track = default_caption_track(WORDS, [SourceInterval(source_start=0.0, source_end=3.0)])
    assert track.style.font == "Montserrat"
    assert track.highlight is not None  # караоке включён по умолчанию
    assert len(track.replies) == 2
