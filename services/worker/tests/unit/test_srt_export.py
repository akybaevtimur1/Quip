"""Тесты SRT-экспорта (app.editor.captions_v2.compile_srt / format_srt_time).

SRT-экспорт — часть «экспорт-свободы» (юзер уносит субтитры в любой редактор).
Инвариант: compile_srt зеркалит reply-итерацию compile_ass (те же реплики, тот же
cmap.source_to_clip) → скачанный SRT совпадает с прожжённым видео по таймингам.
Отличия от ASS: плоский текст, натуральный регистр, без караоке/анимации/тегов.
"""

from app.editor.captions_v2 import compile_srt, format_srt_time
from app.editor.timemap import ClipTimeMap
from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    HighlightStyle,
    SourceInterval,
    Word,
)


def _w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def _cmap() -> ClipTimeMap:
    return ClipTimeMap([SourceInterval(source_start=0.0, source_end=10.0)])


# ─────────────────────────── format_srt_time ───────────────────────────


def test_format_srt_time_zero():
    assert format_srt_time(0.0) == "00:00:00,000"


def test_format_srt_time_hours_minutes_millis():
    assert format_srt_time(3661.5) == "01:01:01,500"


def test_format_srt_time_minutes_quarter_second():
    assert format_srt_time(65.25) == "00:01:05,250"


# ─────────────────────────── compile_srt ───────────────────────────


def test_compile_srt_basic_block_structure():
    words = [_w("hello", 0.0, 0.5), _w("world", 0.5, 1.0)]
    track = CaptionTrack(
        style=CaptionStyle(), highlight=None, replies=[CaptionReply(word_refs=[0, 1])]
    )
    srt = compile_srt(track, words, _cmap())
    assert srt.startswith("1\n")
    assert "00:00:00,000 --> 00:00:01,000" in srt
    assert "hello world" in srt


def test_compile_srt_sequential_indices_skip_hidden():
    words = [_w("a", 0.0, 0.5), _w("b", 1.0, 1.5), _w("c", 2.0, 2.5)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=None,
        replies=[
            CaptionReply(word_refs=[0]),
            CaptionReply(word_refs=[1], hidden=True),  # пропускается
            CaptionReply(word_refs=[2]),
        ],
    )
    srt = compile_srt(track, words, _cmap())
    blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
    assert len(blocks) == 2
    assert blocks[0].startswith("1\n")  # нумерация без дыры
    assert blocks[1].startswith("2\n")
    assert "b" not in srt  # текст скрытой реплики отсутствует


def test_compile_srt_plain_text_natural_case_no_ass_tags():
    words = [_w("hello", 0.0, 0.5)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=True),  # в видео CAPS, но SRT — натуральный регистр
        highlight=HighlightStyle(),  # в видео караоке, но SRT без тегов
        replies=[CaptionReply(word_refs=[0])],
    )
    srt = compile_srt(track, words, _cmap())
    assert "hello" in srt
    assert "HELLO" not in srt
    assert "\\k" not in srt
    assert "{" not in srt


def test_compile_srt_uses_text_override():
    words = [_w("a", 0.0, 0.5), _w("b", 0.5, 1.0)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1], text_override="custom line")],
    )
    srt = compile_srt(track, words, _cmap())
    assert "custom line" in srt


def test_compile_srt_skips_reply_in_hole():
    words = [_w("x", 50.0, 50.5)]  # вне интервала [0,10) → дырка
    track = CaptionTrack(
        style=CaptionStyle(), highlight=None, replies=[CaptionReply(word_refs=[0])]
    )
    srt = compile_srt(track, words, _cmap())
    blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
    assert blocks == []
