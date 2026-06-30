from app.editor.captions_v2 import (
    KAZAKH_INCOMPLETE_FONTS,
    LATIN_ONLY_FONTS,
    LOOK_MATCH_FOR_CYRILLIC,
    SINGLE_WEIGHT_FONTS,
    _ass_bold_flag,
    _ass_color,
    _has_kazakh,
    compile_ass,
    resolve_font_for_text,
    word_animation_tags,
)
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


def test_compile_ass_escapes_braces_in_word_text():
    # libass парсит {...} как override-блок → "{laughs}" молча ПРОПАДАЕТ. Должно экранироваться.
    words = [_w("{laughs}", 0.0, 0.4), _w("hi", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1])],
    )
    ass = compile_ass(track, words, _cmap())
    d = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
    assert "\\{laughs\\}" in d  # фигурные экранированы
    assert "{laughs}" not in d.replace("\\{laughs\\}", "")  # сырых скобок нет


def test_compile_ass_escapes_backslash_in_text_override():
    # \N в тексте юзера = принудительный перенос строки в libass → ломает раскладку.
    words = [_w("a", 0.0, 0.4), _w("b", 0.4, 0.8)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False),
        highlight=None,
        replies=[CaptionReply(word_refs=[0, 1], text_override="path\\Nfile")],
    )
    ass = compile_ass(track, words, _cmap())
    d = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue:"))
    assert "\\N" not in d  # бэкслеш-тег нейтрализован
    assert "⧵" in d  # подменён на безопасный глиф U+29F5


def test_compile_ass_does_not_escape_own_karaoke_tags():
    # экранирование текста НЕ должно трогать наши \k/\1c-теги
    words = [_w("hi", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(uppercase=False),
        highlight=HighlightStyle(),
        replies=[CaptionReply(word_refs=[0])],
    )
    ass = compile_ass(track, words, _cmap())
    assert "\\k" in ass  # караоке-тег цел (не превратился в ⧵k)


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


# ───────────────── Bold=0 single-weight set ─────────────────


def test_ass_bold_flag_single_weight_fonts():
    expected = {
        # UI-шрифты без bold-ката
        "Unbounded",
        "Anton",
        "Archivo Black",
        "Bebas Neue",
        "Luckiest Guy",
        "Poppins",
        "Russo One",
        # кириллице-способные look-match'ы (тяжёлые статик-инстансы, subfamily "Regular")
        "Rubik Black",
        "Play",
        "Oswald Heavy",
        "Oswald",
        "Golos Text Black",
        "Nunito Black",
    }
    for f in expected:
        assert _ass_bold_flag(f) == 0, f
    assert SINGLE_WEIGHT_FONTS == expected


def test_ass_bold_flag_multi_weight_fonts():
    assert _ass_bold_flag("Montserrat") == -1
    # "Rubik" остаётся multi-weight (его TTF — Bold-кат, матчится через Bold=-1), даже будучи
    # look-match'ем Poppins — без регрессии относительно выбранного юзером Rubik.
    assert _ass_bold_flag("Rubik") == -1


def test_compile_ass_default_style_bold0_for_anton():
    words = [_w("a", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(font="Anton"), highlight=None, replies=[CaptionReply(word_refs=[0])]
    )
    style_line = next(
        ln
        for ln in compile_ass(track, words, _cmap()).splitlines()
        if ln.startswith("Style: Default,")
    )
    fields = style_line.split(",")
    assert fields[1] == "Anton"  # Fontname
    assert fields[7] == "0"  # Bold


# ───────────────── Cyrillic look-match (preserve bold display look) ─────────────────
# Каждый display-слот свапается на кириллице-способный аналог, СОХРАНЯЯ жирный лук (а не
# откатываясь в Montserrat). Свап — ко ВСЕЙ кириллице (русский тоже). Зеркало assStyle.ts.


def test_look_match_map_covers_all_seven_display_slots():
    # ровно 7 слотов; ни один таргет не равен Montserrat (лук сохранён, не fallback)
    assert LOOK_MATCH_FOR_CYRILLIC == {
        "Unbounded": "Rubik Black",
        "Russo One": "Play",
        "Anton": "Oswald Heavy",
        "Bebas Neue": "Oswald",
        "Archivo Black": "Golos Text Black",
        "Luckiest Guy": "Nunito Black",
        "Poppins": "Rubik",
    }
    assert "Montserrat" not in set(LOOK_MATCH_FOR_CYRILLIC.values())
    # каждый Latin-only и каждый Kazakh-incomplete шрифт ИМЕЕТ look-match (Montserrat не нужен)
    assert LATIN_ONLY_FONTS <= set(LOOK_MATCH_FOR_CYRILLIC)
    assert KAZAKH_INCOMPLETE_FONTS <= set(LOOK_MATCH_FOR_CYRILLIC)


def test_resolve_font_latin_font_latin_text_unchanged():
    # латиница не содержит кириллицы → шрифт не трогаем (look-match не срабатывает)
    assert resolve_font_for_text("Anton", "Hello world") == "Anton"
    assert resolve_font_for_text("Poppins", "Hello") == "Poppins"


def test_resolve_font_look_match_applies_to_russian_for_every_slot():
    # РУССКИЙ (не только казахский) получает лук — свап на look-match для всех 7 слотов
    for orig, look in LOOK_MATCH_FOR_CYRILLIC.items():
        assert resolve_font_for_text(orig, "Привет мир") == look, orig


def test_resolve_font_look_match_applies_to_kazakh_for_every_slot():
    # казахский с уникальными глифами → тот же look-match (он покрывает все 18 — см. test_fonts)
    for orig, look in LOOK_MATCH_FOR_CYRILLIC.items():
        assert resolve_font_for_text(orig, "Қазақша мәтін") == look, orig


def test_resolve_font_hook_default_unbounded_to_rubik_black():
    # самый важный слот: дефолтный хук (Unbounded) → Rubik Black (геометрический ультра-болд)
    assert resolve_font_for_text("Unbounded", "Сәлем") == "Rubik Black"
    assert resolve_font_for_text("Unbounded", "Привет") == "Rubik Black"


def test_resolve_font_russo_one_to_play():
    assert resolve_font_for_text("Russo One", "Қазақ мәтіні") == "Play"
    assert resolve_font_for_text("Russo One", "Привет") == "Play"


def test_resolve_font_anton_to_oswald_heavy():
    assert resolve_font_for_text("Anton", "Привет") == "Oswald Heavy"
    assert resolve_font_for_text("Anton", "Қазақ") == "Oswald Heavy"


def test_resolve_font_montserrat_always_unchanged():
    # Montserrat нет в look-match, не Latin-only, не Kazakh-incomplete → не трогаем
    assert resolve_font_for_text("Montserrat", "Привет") == "Montserrat"
    assert resolve_font_for_text("Montserrat", "Hello") == "Montserrat"


def test_resolve_font_unmapped_latin_only_falls_back_to_montserrat():
    # защитный фолбэк: Latin-only шрифт БЕЗ записи в look-match (гипотетический) → Montserrat.
    # (в текущем продукте все слоты замаплены; проверяем сам резерв-механизм.)
    import app.editor.captions_v2 as c

    orig = dict(c.LOOK_MATCH_FOR_CYRILLIC)
    try:
        c.LOOK_MATCH_FOR_CYRILLIC.pop("Anton")
        assert c.resolve_font_for_text("Anton", "Привет") == "Montserrat"
    finally:
        c.LOOK_MATCH_FOR_CYRILLIC.clear()
        c.LOOK_MATCH_FOR_CYRILLIC.update(orig)


# ─────────── казахо-уникальные глифы ───────────
# Тест-строка с КАЖДЫМ казахо-уникальным глифом (ә ғ қ ң ө ұ ү һ і + верхний регистр).
_KAZAKH_TEXT = "Сәлем! Қазақша мәтін — әріптер: ғ қ ң ө ұ ү һ і Ғ Қ Ң Ө Ұ Ү Һ І"


def test_has_kazakh_detects_unique_codepoints():
    assert _has_kazakh("Қазақ")  # қ/Қ — казахо-уникальные
    assert _has_kazakh("мәтін")  # ә/і
    assert _has_kazakh(_KAZAKH_TEXT)


def test_has_kazakh_false_for_russian_and_latin():
    # Чисто русский (нет казахо-уникальных кодпойнтов) и латиница → False
    assert not _has_kazakh("Привет мир")
    assert not _has_kazakh("Hello world")
    assert not _has_kazakh("")


def test_kazakh_incomplete_set_membership():
    # Unbounded (дефолт хука) и Russo One (пресет u) русскую кириллицу рендерят, но без
    # казахских глифов → tofu. НЕ Latin-only (русский корректен).
    assert KAZAKH_INCOMPLETE_FONTS == frozenset({"Unbounded", "Russo One"})
    assert KAZAKH_INCOMPLETE_FONTS.isdisjoint(LATIN_ONLY_FONTS)


def test_resolve_font_montserrat_kazakh_unchanged():
    # Montserrat покрывает все 18 → не трогаем
    assert resolve_font_for_text("Montserrat", _KAZAKH_TEXT) == "Montserrat"


def test_compile_ass_kazakh_hook_swaps_unbounded_to_look_match():
    # Хук с дефолтным Unbounded + казахский текст → Hook-style эмитит look-match (Rubik Black)
    from app.models import HookOverlay

    words = [_w("Привет", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
        hook=HookOverlay(text="Сәлем достар!", font="Unbounded"),
    )
    hook_line = next(
        ln
        for ln in compile_ass(track, words, _cmap()).splitlines()
        if ln.startswith("Style: Hook,")
    )
    fields = hook_line.split(",")
    assert fields[1] == "Rubik Black"  # Fontname
    assert fields[7] == "0"  # Bold=0 (single-weight look-match)


def test_compile_ass_kazakh_caption_swaps_russo_one_to_look_match():
    # Субтитры на Russo One + казахский → Default-style эмитит look-match (Play)
    words = [_w("Қазақша", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(font="Russo One"),
        highlight=None,
        replies=[CaptionReply(word_refs=[0])],
    )
    style_line = next(
        ln
        for ln in compile_ass(track, words, _cmap()).splitlines()
        if ln.startswith("Style: Default,")
    )
    assert style_line.split(",")[1] == "Play"


def test_compile_ass_cyrillic_text_swaps_latin_only_font_to_look_match():
    words = [_w("Привет", 0.0, 0.4)]
    track = CaptionTrack(
        style=CaptionStyle(font="Anton"), highlight=None, replies=[CaptionReply(word_refs=[0])]
    )
    style_line = next(
        ln
        for ln in compile_ass(track, words, _cmap()).splitlines()
        if ln.startswith("Style: Default,")
    )
    assert style_line.split(",")[1] == "Oswald Heavy"


# ───────────────── new word animations ─────────────────


def test_new_word_animations_layout_neutral():
    # все 5 новых: без \fscx/\fsp (которые меняют ширину → реврап)
    for anim in ["drop_in", "glow_pulse", "shake", "slide_up"]:
        tags = word_animation_tags(anim, 100)
        assert tags, anim
        assert "\fscx" not in tags and "\fsp" not in tags, anim


def test_flash_animation_uses_accent():
    assert word_animation_tags("flash", 0) == ""  # без accent — пусто
    out = word_animation_tags("flash", 50, accent="&H00FF00&")
    assert r"\1c&HFFFFFF&" in out and "&H00FF00&" in out


def test_drop_in_offsets():
    out = word_animation_tags("drop_in", 200)
    assert r"\t(200,290," in out and r"\t(290,370," in out
