from app.editor.captions_v2 import _ass_color, compile_ass, word_animation_tags
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


def test_word_animation_pop_offsets_from_line_start():
    # \t отсчитывается от начала СТРОКИ → теги получают оффсет слова
    assert word_animation_tags("pop", 0) == r"\t(0,120,\fscy118)\t(120,240,\fscy100)"
    assert word_animation_tags("pop", 500) == r"\t(500,620,\fscy118)\t(620,740,\fscy100)"


def test_word_animation_bounce():
    assert (
        word_animation_tags("bounce", 200)
        == r"\t(200,280,\fscy115)\t(280,360,\fscy96)\t(360,440,\fscy100)"
    )


def test_word_animation_never_scales_horizontally():
    # \fscx меняет ширину строки → реврап (слово прыгает на 2-ю строку). Запрещено.
    for anim in ("pop", "bounce", "none", "karaoke_fill"):
        assert "\\fscx" not in word_animation_tags(anim, 0)


def test_word_animation_none_and_karaoke_empty():
    assert word_animation_tags("none", 0) == ""
    assert word_animation_tags("karaoke_fill", 0) == ""


def test_word_animation_punch():
    # сильный зум-удар (вертикальный, без реврапа)
    assert word_animation_tags("punch", 0) == r"\t(0,90,\fscy132)\t(90,220,\fscy100)"
    assert word_animation_tags("punch", 500) == r"\t(500,590,\fscy132)\t(590,720,\fscy100)"


def test_word_animation_fade():
    # пословный reveal: слово появляется проявлением (alpha FF→00)
    assert word_animation_tags("fade", 0) == r"\alpha&HFF&\t(0,180,\alpha&H00&)"
    assert word_animation_tags("fade", 300) == r"\alpha&HFF&\t(300,480,\alpha&H00&)"


def test_word_animation_spring():
    assert word_animation_tags("spring", 0) == (
        r"\fscy40\t(0,110,\fscy128)\t(110,200,\fscy92)\t(200,280,\fscy105)\t(280,340,\fscy100)"
    )


def test_word_animation_blur_in():
    assert word_animation_tags("blur_in", 0) == r"\blur18\alpha&H60&\t(0,220,\blur0\alpha&H00&)"


def test_word_animation_color_sweep_needs_colors():
    # без accent/base — пусто (нечего свайпить)
    assert word_animation_tags("color_sweep", 0) == ""
    # с цветами — вспышка accent → возврат в base
    got = word_animation_tags("color_sweep", 0, accent="&H0000FF&", base="&HFFFFFF&")
    assert got == r"\1c&H0000FF&\t(0,260,\1c&HFFFFFF&)"


def test_new_animations_never_scale_horizontally():
    # \fscx/\fsp меняют ширину → реврап. Новые анимации не должны их трогать.
    for anim in ("punch", "fade", "spring", "blur_in", "color_sweep"):
        tags = word_animation_tags(anim, 0, accent="&H0000FF&", base="&HFFFFFF&")
        assert "\\fscx" not in tags and "\\fsp" not in tags


def test_compile_ass_pop_emits_transforms_per_word():
    words = [_w("Раз", 0.0, 0.4), _w("два", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=HighlightStyle(animation="pop"),
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    assert ass.count("\\k") == 2  # караоке-заливка остаётся
    assert ass.count("\\t(") == 4  # по 2 transform-тега на слово
    assert "\\t(400,520" in ass  # второе слово анимируется на СВОЁМ оффсете
    # \t действует на весь последующий текст → каждый блок ОБЯЗАН сбрасывать
    # \fscy100 ДО своего \t, иначе анимация первого слова дёргает всю строку
    assert ass.count("\\fscy100\\t(") == 2


def test_compile_ass_animation_none_disables_karaoke_fill():
    # none = статичная фраза: без \k вся строка рисуется PrimaryColour →
    # primary обязан быть цветом ТЕКСТА (st.color), не highlight-цветом.
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(color="#FFFFFF"),
        highlight=HighlightStyle(color="#FF0000", animation="none"),
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\k" not in ass
    style_line = next(ln for ln in ass.splitlines() if ln.startswith("Style: Default,"))
    assert style_line.split(",")[3] == "&H00FFFFFF"  # PrimaryColour = цвет текста


def test_compile_ass_emphasis_colors_marked_word_plain():
    # ударное слово (поз. 1) красится emphasis-цветом, с reset к базовому; остальные — нет
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8), _w("c", 0.8, 1.2)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, emphasis_color="#FF0000"),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1, 2], emphasis_refs=[1])],
    )
    ass = compile_ass(track, words, _cmap())
    d = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
    # #FF0000 → инлайн &H0000FF&; reset к белому &HFFFFFF&
    assert "{\\1c&H0000FF&}b{\\1c&HFFFFFF&}" in d


def test_compile_ass_no_emphasis_color_no_override():
    # emphasis_refs есть, но emphasis_color не задан → НЕ красим (байт-в-байт как раньше)
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1], emphasis_refs=[1])],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\1c" not in ass


def test_compile_ass_emphasis_keeps_karaoke():
    # emphasis в караоке-режиме: \k цел, ударное слово получает акцент-цвет
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False, emphasis_color="#00FF00"),
        highlight=HighlightStyle(),
        replies=[CaptionReply(word_refs=[0, 1], emphasis_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    assert ass.count("\\k") == 2  # караоке не сломано
    assert "\\1c&H00FF00&" in ass  # #00FF00 → &H00FF00& на ударном слове


def test_compile_ass_burn_false_skips_captions():
    # T4 #8: видео уже с вшитыми субтитрами → не накладываем наши (нет caption-Dialogue)
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(), highlight=None, replies=[CaptionReply(word_refs=[0])], burn=False
    )
    ass = compile_ass(track, words, _cmap())
    assert "Dialogue:" not in ass


def test_compile_ass_burn_false_keeps_hook():
    # хук (верх) НЕ конфликтует с вшитыми низами → остаётся даже при burn=False
    from app.models import HookOverlay

    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
        burn=False,
        hook=HookOverlay(text="Хук"),
    )
    ass = compile_ass(track, words, _cmap())
    assert ",Hook,," in ass  # топ-хук остаётся
    assert ",Default,," not in ass  # нижние субтитры не накладываются


def test_compile_ass_scale_pops_active_word_vertically():
    # T4 #4: highlight.scale увеличивает АКТИВНОЕ слово по вертикали (\fscy, без реврапа)
    words = [_w("раз", 0.0, 0.4), _w("два", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=HighlightStyle(scale=1.15),  # animation=karaoke_fill (без \fscy-анимации)
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    assert ass.count("\\k") == 2  # караоке цело
    assert "\\fscy115" in ass  # активное слово растёт до 115% (round(1.15*100))
    assert "\\fscx" not in ass  # ТОЛЬКО вертикально (горизонталь = реврап, запрещено)


def test_compile_ass_scale_one_no_transform():
    # scale=1.0 → без \t-трансформа (поведение прежнее)
    words = [_w("раз", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=HighlightStyle(scale=1.0),
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\t(" not in ass


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
