from app.editor.captions_v2 import _ass_color, compile_ass
from app.editor.timemap import ClipTimeMap
from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    HighlightStyle,
    SourceInterval,
    Word,
)


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def _cmap():
    return ClipTimeMap([SourceInterval(source_start=0.0, source_end=2.0)])


def test_ass_color_conversion():
    assert _ass_color("#FFFFFF") == "&H00FFFFFF"
    assert _ass_color("#FFE000") == "&H0000E0FF"  # BGR порядок: bb=00 gg=E0 rr=FF


def test_compile_ass_karaoke_tags_and_uppercase():
    words = [_w("Привет", 0.0, 0.4), _w("мир", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(), highlight=HighlightStyle(), replies=[CaptionReply(word_refs=[0, 1])]
    )
    ass = compile_ass(track, words, _cmap())
    assert "[V4+ Styles]" in ass and "[Events]" in ass
    assert ass.count("\\k") == 2  # по \k-тегу на слово
    assert "ПРИВЕТ" in ass  # uppercase=True по умолчанию
    assert "Dialogue: 0," in ass


def test_compile_ass_no_highlight_is_plain():
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\k" not in ass
    assert "a b" in ass


def test_compile_ass_text_override_plain_on_count_mismatch():
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=HighlightStyle(),
        replies=[CaptionReply(word_refs=[0, 1], text_override="ОДНО")],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\k" not in ass and "ОДНО" in ass  # 1 слово ≠ 2 word_refs → без караоке


def test_compile_ass_hidden_skipped():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(), highlight=None, replies=[CaptionReply(word_refs=[0], hidden=True)]
    )
    ass = compile_ass(track, words, _cmap())
    assert "Dialogue:" not in ass


def test_compile_ass_box_sets_border_style_3():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(box_color="#000000", box_opacity=0.5),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    # BorderStyle = 16-е значение строки Style; split(",")[0]="Style: Default" → индекс 15
    style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
    fields = style_line.split(",")
    assert fields[15] == "3"
