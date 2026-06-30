"""Компиляция CaptionTrack → ASS (спека §7). PURE.

Один источник правды (CaptionTrack) → ASS для рендера (libass). Караоке = нативный {\\k}.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionTrack, HighlightStyle, HookOverlay, Word
from app.pipeline.stage4_captions import escape_ass_text, format_ass_time

log = logging.getLogger(__name__)


def _ass_color(hex_color: str, alpha_byte: int = 0) -> str:
    """#RRGGBB → ASS &HAABBGGRR (alpha_byte: 0=непрозрачный, 255=прозрачный)."""
    h = hex_color.lstrip("#")
    rr, gg, bb = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha_byte:02X}{bb}{gg}{rr}".upper()


def _ass_color_tag(hex_color: str) -> str:
    """#RRGGBB → инлайн-цвет ASS &HBBGGRR& (6 hex, без альфы — для пословного \\1c-override).

    Style-строка хочет 8 hex с альфой (_ass_color); инлайн \\1c — 6 hex с хвостовым &.
    """
    h = hex_color.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


# Шрифты БЕЗ реального bold-начертания (single-weight TTF): для них Bold=0 в ASS-Style,
# иначе libass подменяет СЕМЕЙСТВО (берёт чужой реальный Bold) → прожиг ≠ превью. Зеркалится
# во фронте (assStyle.ts). См. build_hook_event / compile_ass.
SINGLE_WEIGHT_FONTS = frozenset(
    {
        # UI-шрифты (StyleControls.CAPTION_FONTS) без bold-ката.
        "Unbounded",
        "Anton",
        "Archivo Black",
        "Bebas Neue",
        "Luckiest Guy",
        "Poppins",
        "Russo One",
        # Кириллице-способные look-match'ы (LOOK_MATCH_FOR_CYRILLIC ниже): одиночные ТЯЖЁЛЫЕ
        # статик-инстансы с subfamily "Regular". Bold=0 → libass матчит Regular-фейс ТОЧНО (сам
        # глиф уже жирный → без fake-bold, без подмены семейства). «Rubik» здесь НЕТ: его TTF —
        # это Bold-кат, матчится через Bold=-1 как и выбранный юзером Rubik (без регрессии).
        "Rubik Black",
        "Play",
        "Oswald Heavy",
        "Oswald",
        "Inter",
        "Nunito Black",
    }
)

# Шрифты БЕЗ кириллических глифов (Latin-only): на кириллице → tofu. Russo One РУССКУЮ
# кириллицу покрывает, поэтому в этом наборе его НЕТ (но казахский — см. ниже). См.
# resolve_font_for_text.
LATIN_ONLY_FONTS = frozenset({"Anton", "Archivo Black", "Bebas Neue", "Luckiest Guy", "Poppins"})

# Казахо-уникальные кодпойнты: 9 букв × 2 регистра = 18. Есть в казахском, но НЕ в стандартном
# русском. Это ровно те глифы, которых нет в Unbounded/Russo One (→ tofu на казахском).
# ЕДИНЫЙ источник правды: test_fonts.py импортирует это и проверяет, что каждый шрифт-фолбэк их
# покрывает; зеркалится во фронте (assStyle.ts KAZAKH_CODEPOINTS) → preview == render.
KAZAKH_CODEPOINTS = frozenset(
    {
        0x04D9, 0x04D8,  # ә Ә
        0x0493, 0x0492,  # ғ Ғ
        0x049B, 0x049A,  # қ Қ
        0x04A3, 0x04A2,  # ң Ң
        0x04E9, 0x04E8,  # ө Ө
        0x04B1, 0x04B0,  # ұ Ұ
        0x04AF, 0x04AE,  # ү Ү
        0x0456, 0x0406,  # і І
        0x04BB, 0x04BA,  # һ Һ
    }
)  # fmt: skip

# Шрифты С русской кириллицей, но БЕЗ казахо-уникальных глифов (ә ғ қ ң ө ұ ү һ — Unbounded
# покрывает лишь і/І): на казахском → tofu. НЕ Latin-only (русский рендерят верно).
# Unbounded — ДЕФОЛТ хука (models.py HookOverlay.font), Russo One — пресет «u» (Gamer Tech).
# Проверено fonttools 2026-06-30: ни одна upstream-сборка (google/fonts release И source-repo
# HEAD) этих глифов не содержит → замена САМОГО TTF невозможна. Раньше гард свапал их на Montserrat
# (читаемо, но bold-look терялся); теперь — на кириллице-способный LOOK-match (см. ниже).
# Зеркалится во фронте (assStyle.ts KAZAKH_INCOMPLETE_FONTS). См. resolve_font_for_text.
KAZAKH_INCOMPLETE_FONTS = frozenset({"Unbounded", "Russo One"})

# Шрифт-фолбэк для кириллицы (покрывает U+0400–U+04FF + все 18 казахских, есть в обоих
# fonts-каталогах). Используется как ПОСЛЕДНИЙ резерв — только для шрифтов БЕЗ записи в
# LOOK_MATCH_FOR_CYRILLIC (читаемо, но bold-look теряется).
_CYRILLIC_FALLBACK_FONT = "Montserrat"

# Кириллице-способный LOOK-match на каждый display-слот: сохраняет ЖИРНЫЙ ДИСПЛЕЙНЫЙ ЛУК на
# кириллице/казахском вместо отката в Montserrat. Каждый таргет ПРОВЕРЕН fonttools 2026-06-30 —
# покрывает все 18 казахских глифов (ә ғ қ ң ө ұ ү һ і + верхний регистр) И базовую русскую
# кириллицу — и подобран ПОД ЛУК оригинала (OFL, google/fonts). Свап применяется ко ВСЕЙ
# кириллице (русский ТОЖЕ получает лук, не только казахский). TTF лежат в обоих fonts-каталогах
# (services/worker/fonts + apps/web/public/libass/fonts), зарегистрированы в LibassLayer.
# Источник правды; зеркалится во фронте (assStyle.ts LOOK_MATCH_FOR_CYRILLIC) → preview == render.
#   Unbounded     (дефолт хука: геометрический ультра-болд, скруглён) → Rubik Black
#   Russo One     (пресет «u» Gamer Tech: квадратный техно)          → Play
#   Anton         (пресет «n»: высокий узкий жирный)                 → Oswald Heavy
#   Bebas Neue    (пресет «q»: высокий узкий капс)                   → Oswald
#   Archivo Black (пресет «o»: гротеск-блэк)                         → Inter
#   Luckiest Guy  (пресет «t» Sticker Round: комикс-круглый)         → Nunito Black
#   Poppins       (пресет «p» Bold Pop White: геометрический болд)   → Rubik
LOOK_MATCH_FOR_CYRILLIC = {
    "Unbounded": "Rubik Black",
    "Russo One": "Play",
    "Anton": "Oswald Heavy",
    "Bebas Neue": "Oswald",
    "Archivo Black": "Inter",
    "Luckiest Guy": "Nunito Black",
    "Poppins": "Rubik",
}


def _ass_bold_flag(font: str) -> int:
    """ASS Bold-флаг для шрифта: 0 (single-weight, без fake-bold/подмены) иначе -1. PURE."""
    return 0 if font in SINGLE_WEIGHT_FONTS else -1


def _has_cyrillic(text: str) -> bool:
    """True если в тексте есть символ из кириллического блока U+0400–U+04FF. PURE."""
    return any("Ѐ" <= ch <= "ӿ" for ch in text)


def _has_kazakh(text: str) -> bool:
    """True если в тексте есть казахо-уникальный кодпойнт (KAZAKH_CODEPOINTS). PURE."""
    return any(ord(ch) in KAZAKH_CODEPOINTS for ch in text)


def resolve_font_for_text(font: str, text: str) -> str:
    """Подобрать шрифт под текст: шрифт без нужных глифов → кириллице-способный аналог.

    ОСОЗНАННОЕ render-решение (НЕ молчаливый проглот ошибки): display-шрифты без кириллицы
    (Anton/…) или без казахских глифов (Unbounded/Russo One) дают tofu (□□□) на казахском.
    Латиница в тексте нет кириллицы → шрифт не трогаем.
    Текст СОДЕРЖИТ кириллицу — порядок разрешения:
      1. LOOK-match (LOOK_MATCH_FOR_CYRILLIC): шрифт-слот → кириллице-способный аналог,
         подобранный ПОД ЛУК оригинала и покрывающий все 18 казахских глифов + русский. Это
         СОХРАНЯЕТ жирный дисплейный лук (фаундер закрывает B2B-сделку в Алматы) вместо отката
         в Montserrat. Применяется ко ВСЕЙ кириллице → русский тоже получает лук, не только казах.
      2. Фолбэк (у шрифта НЕТ записи в LOOK-match): Latin-only → Montserrat (кириллицы нет вовсе);
         Kazakh-incomplete → Montserrat ТОЛЬКО если в тексте реально есть казахо-уникальный глиф
         (чисто русский на таком шрифте остаётся как есть — лук сохранён).
    Подмена логируется (явная, НЕ тихая — см. CLAUDE.md). Детерминирована по (font, text) —
    return чистый; info-лог = наблюдаемость. Зеркалится во фронте (assStyle.ts
    resolveFontForText) → preview == render (WYSIWYG).
    """
    if not _has_cyrillic(text):
        return font
    look = LOOK_MATCH_FOR_CYRILLIC.get(font)
    if look is not None:
        log.info("font swap: %r → %r (Cyrillic look-match, preserves bold look)", font, look)
        return look
    if font in LATIN_ONLY_FONTS:
        log.info("font swap: %r is Latin-only, Cyrillic text → %s", font, _CYRILLIC_FALLBACK_FONT)
        return _CYRILLIC_FALLBACK_FONT
    if font in KAZAKH_INCOMPLETE_FONTS and _has_kazakh(text):
        log.info(
            "font swap: %r lacks Kazakh glyphs, Kazakh text → %s", font, _CYRILLIC_FALLBACK_FONT
        )
        return _CYRILLIC_FALLBACK_FONT
    return font


# Длинные служебные/филлер-слова (короткие отсекает min_len) — НЕ ключевые (RU+EN).
_KEYWORD_STOPWORDS = frozenset(
    {
        "потому", "который", "которая", "которое", "которые", "наверное", "вообще",
        "просто", "значит", "понимаешь", "допустим", "например", "вообще-то",
        "because", "however", "actually", "basically", "literally", "something",
        "everything", "anything", "probably", "really", "honestly",
    }
)  # fmt: skip


def pick_keyword_positions(texts: list[str], *, max_emph: int = 2, min_len: int = 6) -> list[int]:
    """Позиции «ключевых» слов реплики для авто-подсветки (T3). PURE.

    Кандидаты: слова с цифрой (числа — главный keyword) и длинные контентные слова
    (≥min_len букв, не стоп-слово). Берём до max_emph по приоритету (числа > длина),
    возвращаем позиции по возрастанию. Краткие/служебные слова игнорируются — иначе
    «подсвечено всё» и эффект теряется (как у OpusClip/Hormozi: 1-2 слова на строку).
    """
    cands: list[tuple[int, int]] = []  # (позиция, приоритет)
    for i, raw in enumerate(texts):
        clean = "".join(ch for ch in raw if ch.isalnum())
        if not clean:
            continue
        if any(ch.isdigit() for ch in clean):
            cands.append((i, 1000))  # числа — топ-приоритет
        elif len(clean) >= min_len and clean.lower() not in _KEYWORD_STOPWORDS:
            cands.append((i, len(clean)))
    top = sorted(cands, key=lambda x: (-x[1], x[0]))[:max_emph]
    return sorted(i for i, _ in top)


# Дефолт-маржины Style-строк (легаси): субтитры 40/40, хук 60/60. Когда wrap_width=None —
# оставляем именно их (байт-в-байт старый вывод). См. _wrap_margins / compile_ass.
_CAPTION_DEFAULT_MARGIN = 40
_HOOK_DEFAULT_MARGIN = 60


def _wrap_margins(wrap_width: float | None, play_w: int, default: int) -> tuple[int, int]:
    """(MarginL, MarginR) для ограничения ширины блока libass-переноса. PURE.

    libass переносит строку в доступную ширину PlayResX − MarginL − MarginR (WrapStyle 0 =
    smart-wrap). Уже ширину → меньше слов в строке → текст реврапится на БОЛЬШЕ строк БЕЗ
    смены кегля (ровно то, что хочет фаундер от боковой ручки). wrap_width=None → легаси-
    маржины (default,default) → байт-в-байт старый вывод. Симметрично: L=R=round((play_w−w)/2),
    где w = round(wrap_width*play_w). Зеркалится во фронте (assStyle.ts) → WYSIWYG.
    """
    if wrap_width is None:
        return default, default
    block_w = round(wrap_width * play_w)
    side = round((play_w - block_w) / 2)
    return side, side


def _pos_override(
    pos_x: float | None,
    pos_y: float | None,
    *,
    play_w: int,
    play_h: int,
    an: int,
    legacy_y: int,
) -> str:
    """Ведущий ASS-override `\\pos(x,y)\\anN` для свободного якоря. PURE. "" если pos не задан.

    \\pos ставит ЯКОРЬ события в (x,y); \\anN фиксирует, КАКАЯ точка блока садится на якорь
    (субтитры — \\an2 нижний-центр, хук — \\an8 верхний-центр) → перенос остаётся симметричным
    вокруг x. Задана ХОТЯ БЫ одна координата → эмитим \\pos, недостающую берём из легаси:
    x по центру (0.5·play_w), y из margin_v-семантики (legacy_y — уже вычислен вызывающим).
    libass-тонкость: при \\pos ширина переноса ВСЁ РАВНО управляется MarginL/MarginR (НЕ авто-
    центрируется по x) — подтверждено спайком; поэтому wrap_width и pos компонуются независимо.
    Зеркалится во фронте (assStyle.ts) → WYSIWYG (превью libass.wasm == прожиг ffmpeg).
    """
    if pos_x is None and pos_y is None:
        return ""
    x = round((pos_x if pos_x is not None else 0.5) * play_w)
    y = round(pos_y * play_h) if pos_y is not None else legacy_y
    return f"\\pos({x},{y})\\an{an}"


def _hook_entrance_tags(animation: str) -> str:
    """ASS override-теги ВХОДА всего заголовка хука (одиночный блок, не пословно). PURE.

    \\t отсчитывается от старта события (= старт окна хука) → офсеты от 0.
    ⚠️ Layout-нейтральные теги ТОЛЬКО (\\fscy/\\alpha): \\fscx/\\fsp меняют ШИРИНУ строки →
    libass перепереносит её на каждом кадре (текст «прыгает» — жёсткий запрет, см.
    word_animation_tags). bounce зеркалит word_animation_tags (старт приподнят → оседает к 100).
    Возвращает СОДЕРЖИМОЕ override-блока без скобок ("" для none).
    """
    if animation == "pop":
        return "\\fscy60\\t(0,150,\\fscy105)\\t(150,260,\\fscy100)"
    if animation == "fade":
        return "\\alpha&HFF&\\t(0,200,\\alpha&H00&)"
    if animation == "bounce":
        return "\\fscy115\\t(0,90,\\fscy115)\\t(90,170,\\fscy96)\\t(170,250,\\fscy100)"
    return ""


def build_hook_event(hook: HookOverlay, clip_duration: float) -> tuple[str, str]:
    """Хук → (Style-строка "Hook", Dialogue top-event). PURE (T1).

    Верхний якорь (alignment 8) → топ-текст не пересекается с нижними субтитрами.
    Окно показа: весь клип (full_clip) или первые duration_sec (клампится в длину
    клипа). Плашка (box_color) → BorderStyle=3, как у субтитров. Текст .upper() при
    uppercase; переводы строк → пробел (libass WrapStyle 0 переносит сам).
    """
    primary = _ass_color(hook.color)
    if hook.box_color:
        # libass BorderStyle=3 (opaque box) заливает ПЛАШКУ цветом OutlineColour
        # (НЕ BackColour) → box_color кладём в outline; Outline = паддинг плашки.
        # Белый текст на коралл-плашке читаем без отдельного контура.
        outline = _ass_color(hook.box_color, round((1.0 - hook.box_opacity) * 255))
        back = "&H00000000"
        border_style = 3
        outline_w = max(hook.outline_w, 6)
    else:
        outline = _ass_color(hook.outline_color)
        back = "&H64000000"
        border_style = 1
        outline_w = hook.outline_w
    window = clip_duration if hook.full_clip else min(hook.duration_sec, clip_duration)
    text = hook.text.replace("\n", " ").strip()
    if hook.uppercase:
        text = text.upper()
    # Кириллица/казах в хук-тексте → кириллице-способный look-match (сохраняет жирный лук,
    # без tofu); шрифт без look-match откатывается в Montserrat. См. resolve_font_for_text.
    font = resolve_font_for_text(hook.font, text)
    # Bold=0 для single-weight шрифтов (без реального bold-начертания): иначе на воркере libass
    # подменяет СЕМЕЙСТВО (берёт чужой реальный Bold, напр. Montserrat) → хук рендерится не тем
    # шрифтом, что в превью. Bold=0 = точное family+weight совпадение. Зеркалится во фронте
    # (assStyle.ts) → WYSIWYG (превью == прожиг).
    bold = _ass_bold_flag(font)
    # wrap_width → симметричные маржины ширины блока (None → легаси 60/60 = байт-в-байт).
    play_w, play_h = 1080, 1920
    margin_l, margin_r = _wrap_margins(hook.wrap_width, play_w, _HOOK_DEFAULT_MARGIN)
    style = (
        f"Style: Hook,{font},{hook.size},{primary},{primary},{outline},{back},"
        f"{bold},0,0,0,100,100,0,0,{border_style},{outline_w},{hook.shadow},"
        f"8,{margin_l},{margin_r},{hook.margin_v},1"
    )
    text = escape_ass_text(text)  # {/\ в тексте хука → tag-инъекция libass (см. escape_ass_text)
    # Свободный якорь (\pos) + анимация входа в ОДНОМ ведущем override-блоке {…} ПЕРЕД
    # экранированным текстом (его настоящие скобки НЕ прогоняем через escape_ass_text — иначе
    # \{…\} перестанет быть тегом). \t от 0 (старт окна). Хук = верхний якорь → \an8, легаси-y
    # для top-alignment = margin_v (отступ от верха). pos=None + animation="none" → блока нет →
    # байт-в-байт старый вывод (кэш хуков валиден).
    pos = _pos_override(
        hook.pos_x, hook.pos_y, play_w=play_w, play_h=play_h, an=8, legacy_y=hook.margin_v
    )
    entrance = _hook_entrance_tags(hook.animation)
    lead = pos + entrance
    if lead:
        text = f"{{{lead}}}{text}"
    dialogue = f"Dialogue: 0,{format_ass_time(0.0)},{format_ass_time(window)},Hook,,0,0,,{text}"
    return style, dialogue


def word_animation_tags(animation: str, offset_ms: int, *, accent: str = "", base: str = "") -> str:
    """ASS-теги анимации активного слова (рендерятся ИДЕНТИЧНО libass.wasm и ffmpeg).

    \\t отсчитывается от начала СТРОКИ → offset_ms = момент начала слова в строке.
    ⚠️ Layout-нейтральные теги ТОЛЬКО (\\fscy/\\blur/\\alpha/\\1c): \\fscx/\\fsp/размер
    меняют ШИРИНУ строки → libass перепереносит её на каждом кадре (слово «прыгает» —
    фидбек фаундера). Вертикальный масштаб/блюр/альфа/цвет ширину не трогают → раскладка
    стабильна (подтверждено спайком anim_spike).
    accent/base — инлайн-цвета (_ass_color_tag) для color_sweep: вспышка accent → base.
    pop/punch/spring: \\fscy-флеши разной упругости; bounce: подскок; fade: проявление;
    blur_in: фокус из размытия; color_sweep: цвет-волна по словам.
    none/karaoke_fill → пусто (заливку даёт \\k).
    """
    if animation == "pop":
        return (
            f"\\t({offset_ms},{offset_ms + 120},\\fscy118)"
            f"\\t({offset_ms + 120},{offset_ms + 240},\\fscy100)"
        )
    if animation == "bounce":
        return (
            f"\\t({offset_ms},{offset_ms + 80},\\fscy115)"
            f"\\t({offset_ms + 80},{offset_ms + 160},\\fscy96)"
            f"\\t({offset_ms + 160},{offset_ms + 240},\\fscy100)"
        )
    if animation == "punch":
        # сильный зум-удар (выразительнее pop) — тоже только \fscy (без реврапа)
        return (
            f"\\t({offset_ms},{offset_ms + 90},\\fscy132)"
            f"\\t({offset_ms + 90},{offset_ms + 220},\\fscy100)"
        )
    if animation == "fade":
        # пословный reveal: слово невидимо до своего момента, затем проявляется
        # (alpha FF→00). Не трогает раскладку → реврапа нет.
        return f"\\alpha&HFF&\\t({offset_ms},{offset_ms + 180},\\alpha&H00&)"
    o = offset_ms
    if animation == "spring":
        # упругая пружина с овершутом ТОЛЬКО по Y (40→128→92→105→100) — явно «живее» pop
        return (
            f"\\fscy40\\t({o},{o + 110},\\fscy128)\\t({o + 110},{o + 200},\\fscy92)"
            f"\\t({o + 200},{o + 280},\\fscy105)\\t({o + 280},{o + 340},\\fscy100)"
        )
    if animation == "blur_in":
        # слово появляется размытым+притушённым → резкий фокус (\blur пост-растровый,
        # раскладку не трогает). Каждое слово само ставит \blur/\alpha → без утечки.
        return f"\\blur18\\alpha&H60&\\t({o},{o + 220},\\blur0\\alpha&H00&)"
    if animation == "color_sweep":
        # цвет-волна: слово вспыхивает accent → возврат в base. Ширину не меняет.
        if not (accent and base):
            return ""
        return f"\\1c{accent}\\t({o},{o + 260},\\1c{base})"
    if animation == "drop_in":
        # слово «роняется» сверху: уменьшенная высота+прозрачность → оседает (\fscy/\alpha,
        # без \fscx → ширина стабильна, реврапа нет).
        return (
            f"\\fscy130\\alpha&HFF&\\t({o},{o + 90},\\fscy96\\alpha&H00&)"
            f"\\t({o + 90},{o + 170},\\fscy100)"
        )
    if animation == "glow_pulse":
        # мягкая пульсация свечения (\blur пост-растровый → раскладка не трогается).
        return f"\\blur0\\t({o},{o + 120},\\blur6)\\t({o + 120},{o + 260},\\blur0)"
    if animation == "shake":
        # лёгкая тряска поворотом (\frz — вращение, ширину строки не меняет → без реврапа).
        return (
            f"\\frz0\\t({o},{o + 60},\\frz4)\\t({o + 60},{o + 120},\\frz-4)"
            f"\\t({o + 120},{o + 180},\\frz0)"
        )
    if animation == "slide_up":
        # «выезд» снизу: приплюснут+притушён → разворачивается (\fscy/\alpha, без \fscx).
        return f"\\fscy70\\alpha&H80&\\t({o},{o + 160},\\fscy100\\alpha&H00&)"
    if animation == "flash":
        # вспышка белым → возврат в accent (как color_sweep, но фикс-белый старт).
        if not accent:
            return ""
        return f"\\1c&HFFFFFF&\\t({o},{o + 120},\\1c{accent})"
    return ""


def _scale_pop_tags(w: Word, line_start: float, scale: float) -> str:
    """\\fscy-пап активного слова до scale% на его караоке-окно, затем назад (T4 #4). PURE.

    ТОЛЬКО вертикальный масштаб (\\fscy) — \\fscx менял бы ширину → реврап (запрет, фидбек
    фаундера). Сброс \\fscy100 перед \\t обрывает утечку трансформа на следующие слова.
    """
    ws = round((w.start - line_start) * 1000)
    we = round((w.end - line_start) * 1000)
    sc = round(scale * 100)
    return f"\\fscy100\\t({ws},{ws + 90},\\fscy{sc})\\t({we},{we + 90},\\fscy100)"


def _karaoke_word(
    word_text: str,
    w: Word,
    line_start: float,
    animation: str,
    *,
    color: str | None = None,
    accent: str = "",
    base: str = "",
    scale: float = 1.0,
) -> str:
    """Одно слово караоке-строки: {\\k<дур>[\\1c<цвет>][\\fscy100<анимация|scale>]}ТЕКСТ.

    \\t действует на ВЕСЬ последующий текст строки → без сброса анимация первого
    слова «протекала» на все слова (вся строка прыгала), а у последующих слов
    смешивалась с чужой. Статический \\fscy100 в начале КАЖДОГО блока обрывает
    чужую анимацию: слово анимируется только своим \\t в своё время.

    color: инлайн \\1c для ЭТОГО слова (emphasis-акцент или канонический primary).
    scale (>1.0): вертикальный пап активного слова (T4 #4, highlight.scale) — применяется
    ТОЛЬКО когда нет именованной анимации (иначе их \\fscy-трансформы конфликтуют).
    """
    k = round((w.end - w.start) * 100)
    anim = word_animation_tags(
        animation, round((w.start - line_start) * 1000), accent=accent, base=base
    )
    if anim:
        dyn = "\\fscy100" + anim
    elif scale and scale != 1.0:
        dyn = _scale_pop_tags(w, line_start, scale)
    else:
        dyn = ""
    col = f"\\1c{color}" if color else ""
    return f"{{\\k{k}{col}{dyn}}}{word_text}"


def _reply_text(
    reply: CaptionReply,
    rwords: list[Word],
    uppercase: bool,
    hl: HighlightStyle | None,
    *,
    emphasis_color: str | None = None,
    emph_positions: frozenset[int] = frozenset(),
    primary: str = "",
    accent: str = "",
    base: str = "",
) -> str:
    """Текст реплики для Dialogue. emphasis_color+emph_positions красят «ударные» слова
    (по позиции в рамках реплики) в emphasis_color; остальные — в primary. primary —
    инлайн-цвет (_ass_color_tag). emphasis выключен (None/пусто) → рендер как раньше.
    """

    def up(s: str) -> str:
        # escape ПОСЛЕ upper(): {/\ в тексте слова/override иначе ломают libass (tag-инъекция)
        return escape_ass_text(s.upper() if uppercase else s)

    anim = hl.animation if hl else "none"
    scale = hl.scale if hl else 1.0
    line_start = rwords[0].start
    active = bool(emphasis_color) and bool(emph_positions)

    def kw(text: str, w: Word, j: int) -> str:
        # emphasis активен → \1c на КАЖДОМ слове (ударное→акцент, иначе→primary; без утечки)
        color = (emphasis_color if j in emph_positions else primary) if active else None
        return _karaoke_word(
            text, w, line_start, anim, color=color, accent=accent, base=base, scale=scale
        )

    if reply.text_override is not None:
        ov = reply.text_override.split()
        if hl and len(ov) == len(rwords):
            return " ".join(
                kw(up(o), w, j) for j, (o, w) in enumerate(zip(ov, rwords, strict=True))
            )
        return up(reply.text_override)  # override без пословного маппинга → emphasis не применяем
    if hl:
        return " ".join(kw(up(w.text), w, j) for j, w in enumerate(rwords))
    # plain (без караоке)
    if not active:
        return " ".join(up(w.text) for w in rwords)
    parts: list[str] = []
    for j, w in enumerate(rwords):
        t = up(w.text)
        if j in emph_positions:
            t = f"{{\\1c{emphasis_color}}}{t}{{\\1c{primary}}}"
        parts.append(t)
    return " ".join(parts)


def compile_ass(
    track: CaptionTrack,
    words: list[Word],
    cmap: ClipTimeMap,
    *,
    play_w: int = 1080,
    play_h: int = 1920,
) -> str:
    """CaptionTrack + слова + тайм-маппинг → полный ASS-текст (тайминги в КЛИП-времени).

    play_w/play_h (T5) = PlayRes ASS = РАЗМЕРЫ ВЫХОДА (out_w×out_h аспекта). ОБЯЗАНЫ
    совпадать с output-аспектом: иначе libass анаморфно растянет субтитры (PlayRes-
    аспект ≠ кадр-аспект). Превью (libass.wasm) и экспорт (ffmpeg) берут ОДИН ASS → WYSIWYG.
    """
    st = track.style
    # Кириллица/казах в субтитрах → кириллице-способный look-match (сохраняет жирный лук, без
    # tofu); шрифт без look-match откатывается в Montserrat. Style один на все реплики →
    # проверяем кириллицу по СОВОКУПНОМУ тексту видимых реплик (+ override).
    caption_text = " ".join(
        (
            r.text_override
            if r.text_override is not None
            else " ".join(words[i].text for i in r.word_refs)
        )
        for r in (track.replies if track.burn else [])
        if not r.hidden and r.word_refs
    )
    font = resolve_font_for_text(st.font, caption_text)
    # animation="none" = статичная фраза: караоке выключается ЦЕЛИКОМ (без \k вся
    # строка рисуется PrimaryColour → он обязан остаться цветом текста, не подсветки).
    hl = track.highlight if (track.highlight and track.highlight.animation != "none") else None
    primary = _ass_color(hl.color) if hl else _ass_color(st.color)  # активный/залитый
    secondary = _ass_color(st.color)  # ещё не проговорённый
    # «Ударные» слова: инлайн \1c-теги (6-hex). primary_tag = канонический цвет слова.
    emph_tag = _ass_color_tag(st.emphasis_color) if st.emphasis_color else None
    primary_tag = _ass_color_tag(hl.color) if hl else _ass_color_tag(st.color)
    base_tag = _ass_color_tag(st.color)  # цвет текста — куда возвращается color_sweep
    outline = _ass_color(st.outline_color)
    if st.box_color:
        back = _ass_color(st.box_color, round((1.0 - st.box_opacity) * 255))
        border_style = 3
    else:
        back = "&H64000000"
        border_style = 1

    script_info = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {play_w}\nPlayResY: {play_h}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n"
    )
    # wrap_width → симметричные маржины ширины блока (None → легаси 40/40 = байт-в-байт).
    margin_l, margin_r = _wrap_margins(st.wrap_width, play_w, _CAPTION_DEFAULT_MARGIN)
    styles = (
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{st.size},{primary},{secondary},{outline},{back},"
        # Bold=0 для single-weight шрифтов — без fake-bold/подмены (см. build_hook_event).
        f"{_ass_bold_flag(font)},0,0,0,100,100,0,0,{border_style},{st.outline_w},"
        f"{st.shadow},{st.alignment},{margin_l},{margin_r},{st.margin_v},1\n"
    )
    # Свободный якорь субтитра: ведущий {\pos(x,y)\an2} перед текстом КАЖДОЙ реплики (нижний
    # якорь — \an2 — сохраняет семантику margin_v: y по умолчанию = низ кадра − margin_v).
    # pos=None → "" → байт-в-байт старый вывод. Ширина переноса при \pos управляется MarginL/R
    # (libass-тонкость, спайк) → wrap_width и pos компонуются независимо.
    caption_pos = _pos_override(
        st.pos_x, st.pos_y, play_w=play_w, play_h=play_h, an=2, legacy_y=play_h - st.margin_v
    )
    # Топ-текст (хук): отдельный ASS-стиль + событие с верхним якорем. Компилится в
    # ТОТ ЖЕ файл → libass-превью и ffmpeg-экспорт показывают хук пиксель-в-пиксель.
    hook_dialogue: str | None = None
    hk = track.hook
    if hk is not None and hk.enabled and hk.text.strip():
        hook_style, hook_dialogue = build_hook_event(hk, cmap.clip_duration)
        styles = styles + hook_style + "\n"

    events_hdr = (
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"
    )
    lines = [script_info, styles, events_hdr]

    # burn=False (T4 #8): видео уже с вшитыми субтитрами → наши нижние НЕ накладываем
    # (хук сверху не конфликтует с низами → остаётся). WYSIWYG: превью тоже без низов.
    replies = track.replies if track.burn else []
    for reply in replies:
        if reply.hidden or not reply.word_refs:
            continue
        rwords = [words[i] for i in reply.word_refs]
        start_c = cmap.source_to_clip(rwords[0].start)
        if start_c is None:
            continue  # слово в дырке → пропуск
        last_c = cmap.source_to_clip(rwords[-1].start)
        end_c = (last_c if last_c is not None else start_c) + (rwords[-1].end - rwords[-1].start)
        # «Ударные» позиции: явные emphasis_refs > авто-keyword (T3) > пусто.
        if emph_tag and reply.emphasis_refs:
            emph_set = set(reply.emphasis_refs)
            emph_positions = frozenset(j for j, wr in enumerate(reply.word_refs) if wr in emph_set)
        elif emph_tag and st.emphasis_auto:
            emph_positions = frozenset(pick_keyword_positions([w.text for w in rwords]))
        else:
            emph_positions = frozenset()
        text = _reply_text(
            reply,
            rwords,
            st.uppercase,
            hl,
            emphasis_color=emph_tag,
            emph_positions=emph_positions,
            primary=primary_tag,
            accent=primary_tag,
            base=base_tag,
        )
        # Ведущий {\pos...\an2}-блок ПЕРЕД пословными {\k...}-блоками (его настоящие скобки НЕ
        # экранируем — это override-теги, а не текст). pos=None → caption_pos="" → префикса нет.
        if caption_pos:
            text = f"{{{caption_pos}}}{text}"
        lines.append(
            f"Dialogue: 0,{format_ass_time(start_c)},{format_ass_time(end_c)},Default,,0,0,,{text}"
        )
    if hook_dialogue is not None:
        lines.append(hook_dialogue)
    return "\n".join(lines) + "\n"


def write_caption_ass(
    track: CaptionTrack,
    words: list[Word],
    cmap: ClipTimeMap,
    out_path: Path,
    *,
    play_w: int = 1080,
    play_h: int = 1920,
) -> str:
    """Скомпилировать и записать ASS-файл. Возвращает ASS-текст."""
    ass = compile_ass(track, words, cmap, play_w=play_w, play_h=play_h)
    out_path.write_text(ass, encoding="utf-8")
    return ass


# ─────────────────────────── SRT-экспорт (экспорт-свобода) ───────────────────────────


def format_srt_time(t: float) -> str:
    """Секунды → SRT-таймкод HH:MM:SS,mmm (запятая-разделитель миллисекунд). PURE."""
    ms_total = round(t * 1000)
    ms = ms_total % 1000
    s_total = ms_total // 1000
    return f"{s_total // 3600:02d}:{s_total // 60 % 60:02d}:{s_total % 60:02d},{ms:03d}"


def compile_srt(track: CaptionTrack, words: list[Word], cmap: ClipTimeMap) -> str:
    """CaptionTrack + слова + тайм-маппинг → SRT (клип-время). PURE.

    Зеркалит reply-итерацию compile_ass (те же реплики, тот же cmap.source_to_clip)
    → скачанный SRT совпадает с прожжённым видео по таймингам. Отличия: плоский текст
    в НАТУРАЛЬНОМ регистре, без караоке/анимации/ASS-тегов (для переноса в любой
    редактор — CapCut/Premiere/Resolve импортируют SRT). Индексы 1..N по ЭМИТНУТЫМ
    репликам (скрытые/в-дырке пропущены, без дыр в нумерации).
    """
    blocks: list[str] = []
    idx = 1
    for reply in track.replies:
        if reply.hidden or not reply.word_refs:
            continue
        rwords = [words[i] for i in reply.word_refs]
        start_c = cmap.source_to_clip(rwords[0].start)
        if start_c is None:
            continue  # слово в дырке → пропуск (как compile_ass)
        last_c = cmap.source_to_clip(rwords[-1].start)
        end_c = (last_c if last_c is not None else start_c) + (rwords[-1].end - rwords[-1].start)
        text = (
            reply.text_override
            if reply.text_override is not None
            else " ".join(w.text for w in rwords)
        )
        blocks.append(f"{idx}\n{format_srt_time(start_c)} --> {format_srt_time(end_c)}\n{text}")
        idx += 1
    return "\n\n".join(blocks) + ("\n" if blocks else "")
