"""Свободное позиционирование (pos_x/pos_y) + ширина блока (wrap_width) субтитров и хука.

Стратегия (согласована с фаундером): \\pos(x,y) для свободного якоря + MarginL/MarginR для
ограничения ширины переноса (libass переносит в PlayResX - MarginL - MarginR при WrapStyle 0).
Один ASS → libass.wasm (превью) и ffmpeg (экспорт) → WYSIWYG. PURE-логика, тест-первым.

Семантика (точно):
- pos_x: доля PlayResX (0..1) ЦЕНТРА блока по горизонтали. None = центр (легаси).
- pos_y: доля PlayResY (0..1) ЯКОРЯ по вертикали; для субтитров якорь = НИЖНИЙ край блока
  (\\an2 сохраняется), для хука = ВЕРХНИЙ край (\\an8 сохраняется). None = легаси (margin_v).
- wrap_width: доля PlayResX (0..1) ширины блока. None = легаси-перенос (полная ширина − дефолт-
  маржины). Симметричные MarginL=MarginR=round((play_w - wrap_width*play_w)/2).
- pos задан (хотя бы одна координата) → ведущий блок {\\pos(X,Y)\\anN} перед текстом события.
"""

from app.editor.captions_v2 import build_hook_event, compile_ass
from app.editor.timemap import ClipTimeMap
from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    HighlightStyle,
    HookOverlay,
    SourceInterval,
    Word,
)


def _w(text, start, end):
    return Word(text=text, start=start, end=end)


def _cmap(dur=2.0):
    return ClipTimeMap([SourceInterval(source_start=0.0, source_end=dur)])


def _default_style_line(ass: str) -> str:
    return next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))


def _caption_dialogue(ass: str) -> str:
    return next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:") and ",Default," in ln)


def _dialogue_text(dialogue: str) -> str:
    # поле Text = после ПОСЛЕДНЕГО ",," (Effect пустой перед ним)
    return dialogue.rsplit(",,", 1)[1]


# ─────────────────────── Регрессия: None/None/None = байт-в-байт ───────────────────────


def test_caption_default_none_unchanged_style_and_dialogue():
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    style = _default_style_line(ass)
    # дефолт-маржины 40,40 и хвост ...,2,40,40,260,1 целы
    assert style.endswith(",1,6,2,2,40,40,260,1")
    # текст события без ведущего override-блока \pos
    body = _dialogue_text(_caption_dialogue(ass))
    assert "\\pos(" not in body
    assert body == "a b"


def test_hook_default_none_unchanged():
    style, dialogue = build_hook_event(HookOverlay(text="hi", uppercase=False), clip_duration=10.0)
    fields = style.split(",")
    assert fields[19] == "60" and fields[20] == "60"  # MarginL/MarginR дефолт
    body = dialogue.rsplit(",,", 1)[1]
    assert "\\pos(" not in body
    assert body == "hi"


# ─────────────────────── wrap_width → симметричные маржины ───────────────────────


def test_caption_wrap_width_half_sets_symmetric_margins():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, wrap_width=0.5),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    fields = _default_style_line(ass).split(",")
    # play_w=1080; L=R=round((1080 - 0.5*1080)/2)=round(270)=270
    assert fields[19] == "270"  # MarginL
    assert fields[20] == "270"  # MarginR


def test_hook_wrap_width_sets_symmetric_margins():
    style, _ = build_hook_event(
        HookOverlay(text="x", uppercase=False, wrap_width=0.6), clip_duration=10.0
    )
    fields = style.split(",")
    # L=R=round((1080-0.6*1080)/2)=round(216)=216
    assert fields[19] == "216"
    assert fields[20] == "216"


# ─────────────────────── pos_x/pos_y → \pos override ───────────────────────


def test_caption_pos_center_emits_pos_an2():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, pos_x=0.5, pos_y=0.5),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    body = _dialogue_text(_caption_dialogue(ass))
    # x=round(0.5*1080)=540, y=round(0.5*1920)=960; нижний якорь субтитра \an2
    assert body.startswith("{\\pos(540,960)\\an2}")
    assert body.endswith("a")


def test_caption_pos_corner():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, pos_x=0.3, pos_y=0.8, wrap_width=0.5),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    body = _dialogue_text(_caption_dialogue(ass))
    # x=round(0.3*1080)=324, y=round(0.8*1920)=1536
    assert body.startswith("{\\pos(324,1536)\\an2}")
    # wrap_width=0.5 всё равно даёт симметричные маржины
    fields = _default_style_line(ass).split(",")
    assert fields[19] == "270" and fields[20] == "270"


def test_hook_pos_emits_pos_an8():
    style, dialogue = build_hook_event(
        HookOverlay(text="x", uppercase=False, pos_x=0.5, pos_y=0.2, wrap_width=0.6),
        clip_duration=10.0,
    )
    body = dialogue.rsplit(",,", 1)[1]
    # x=round(0.5*1080)=540, y=round(0.2*1920)=384; верхний якорь хука \an8
    assert body.startswith("{\\pos(540,384)\\an8}")
    fields = style.split(",")
    assert fields[19] == "216" and fields[20] == "216"


def test_hook_pos_composes_with_entrance_animation():
    # \pos-блок и анимация входа должны сосуществовать в ОДНОМ ведущем блоке
    _, dialogue = build_hook_event(
        HookOverlay(text="x", uppercase=False, pos_x=0.5, pos_y=0.2, animation="pop"),
        clip_duration=10.0,
    )
    body = dialogue.rsplit(",,", 1)[1]
    assert body.startswith("{\\pos(540,384)\\an8")
    assert "\\fscy" in body[: body.index("}") + 1]  # анимация в том же блоке
    assert "\\fscx" not in body[: body.index("}") + 1]


def test_caption_pos_keeps_karaoke():
    # \pos-блок не ломает пословное караоке (\k остаются после ведущего блока)
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, pos_x=0.5, pos_y=0.5),
        highlight=HighlightStyle(),
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    body = _dialogue_text(_caption_dialogue(ass))
    assert body.startswith("{\\pos(540,960)\\an2}")
    assert body.count("\\k") == 2  # караоке цело


def test_caption_pos_x_only_fills_y_from_legacy():
    # задан только pos_x → pos всё равно эмитится, y берётся из margin_v-семантики
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, pos_x=0.25, margin_v=260),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    body = _dialogue_text(_caption_dialogue(ass))
    # x=round(0.25*1080)=270; y = play_h - margin_v = 1920-260 = 1660 (нижний якорь)
    assert body.startswith("{\\pos(270,1660)\\an2}")


def test_hook_pos_y_only_fills_x_center():
    # задан только pos_y → x = центр (0.5), y из pos_y
    _, dialogue = build_hook_event(
        HookOverlay(text="x", uppercase=False, pos_y=0.1), clip_duration=10.0
    )
    body = dialogue.rsplit(",,", 1)[1]
    # x=round(0.5*1080)=540, y=round(0.1*1920)=192
    assert body.startswith("{\\pos(540,192)\\an8}")


# ─────────────────────── клампинг / краевые ───────────────────────


def test_wrap_width_full_equals_zero_margins():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, wrap_width=1.0),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    fields = _default_style_line(ass).split(",")
    assert fields[19] == "0" and fields[20] == "0"


def test_pos_edge_zero_and_one():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, pos_x=0.0, pos_y=1.0),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    body = _dialogue_text(_caption_dialogue(ass))
    assert body.startswith("{\\pos(0,1920)\\an2}")


def test_wrap_width_clamped_to_unit_range():
    import pytest

    with pytest.raises(ValueError):
        CaptionStyle(wrap_width=1.5)
    with pytest.raises(ValueError):
        CaptionStyle(wrap_width=-0.1)


def test_pos_x_clamped_to_unit_range():
    import pytest

    with pytest.raises(ValueError):
        CaptionStyle(pos_x=1.5)
    with pytest.raises(ValueError):
        HookOverlay(pos_y=-0.2)


def test_custom_playres_scales_pos_and_margins():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, pos_x=0.5, pos_y=0.5, wrap_width=0.5),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap(), play_w=720, play_h=1280)
    body = _dialogue_text(_caption_dialogue(ass))
    assert body.startswith("{\\pos(360,640)\\an2}")
    fields = _default_style_line(ass).split(",")
    # L=R=round((720-0.5*720)/2)=round(180)=180
    assert fields[19] == "180" and fields[20] == "180"
