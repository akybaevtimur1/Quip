"""Компиляция CaptionTrack → ASS (спека §7). PURE.

Один источник правды (CaptionTrack) → ASS для рендера (libass). Караоке = нативный {\\k}.
"""

from __future__ import annotations

from pathlib import Path

from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionTrack, HighlightStyle, Word
from app.pipeline.stage4_captions import format_ass_time


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


def word_animation_tags(animation: str, offset_ms: int) -> str:
    """ASS-теги анимации активного слова (рендерятся ИДЕНТИЧНО libass.wasm и ffmpeg).

    \\t отсчитывается от начала СТРОКИ → offset_ms = момент начала слова в строке.
    ⚠️ ТОЛЬКО вертикальный масштаб (\\fscy): \\fscx меняет ШИРИНУ строки → libass
    перепереносит строку на каждом кадре анимации (слово «перепрыгивает» на вторую
    строку и обратно — фидбек фаундера «субтитры дёргаются»). \\fscy растёт от
    базлайна вверх и ширину не трогает → раскладка стабильна.
    pop: быстрая вспышка вверх; bounce: подскок с овершутом.
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
    return ""


def _karaoke_word(
    word_text: str, w: Word, line_start: float, animation: str, *, color: str | None = None
) -> str:
    """Одно слово караоке-строки: {\\k<дур>[\\1c<цвет>][\\fscy100<анимация>]}ТЕКСТ.

    \\t действует на ВЕСЬ последующий текст строки → без сброса анимация первого
    слова «протекала» на все слова (вся строка прыгала), а у последующих слов
    смешивалась с чужой. Статический \\fscy100 в начале КАЖДОГО блока обрывает
    чужую анимацию: слово анимируется только своим \\t в своё время.

    color: инлайн \\1c для ЭТОГО слова (emphasis-акцент или канонический primary).
    Когда emphasis активен, цвет ставится на КАЖДОЕ слово — иначе \\1c «протекает»
    на следующие (та же утечка тегов, что с \\fscy). None → \\1c не трогаем (поведение
    без emphasis байт-в-байт прежнее).
    """
    k = round((w.end - w.start) * 100)
    anim = word_animation_tags(animation, round((w.start - line_start) * 1000))
    reset = "\\fscy100" if anim else ""
    col = f"\\1c{color}" if color else ""
    return f"{{\\k{k}{col}{reset}{anim}}}{word_text}"


def _reply_text(
    reply: CaptionReply,
    rwords: list[Word],
    uppercase: bool,
    hl: HighlightStyle | None,
    *,
    emphasis_color: str | None = None,
    emph_positions: frozenset[int] = frozenset(),
    primary: str = "",
) -> str:
    """Текст реплики для Dialogue. emphasis_color+emph_positions красят «ударные» слова
    (по позиции в рамках реплики) в emphasis_color; остальные — в primary. primary —
    инлайн-цвет (_ass_color_tag). emphasis выключен (None/пусто) → рендер как раньше.
    """

    def up(s: str) -> str:
        return s.upper() if uppercase else s

    anim = hl.animation if hl else "none"
    line_start = rwords[0].start
    active = bool(emphasis_color) and bool(emph_positions)

    def kw(text: str, w: Word, j: int) -> str:
        # emphasis активен → \1c на КАЖДОМ слове (ударное→акцент, иначе→primary; без утечки)
        color = (emphasis_color if j in emph_positions else primary) if active else None
        return _karaoke_word(text, w, line_start, anim, color=color)

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


def compile_ass(track: CaptionTrack, words: list[Word], cmap: ClipTimeMap) -> str:
    """CaptionTrack + слова + тайм-маппинг → полный ASS-текст (тайминги в КЛИП-времени)."""
    st = track.style
    # animation="none" = статичная фраза: караоке выключается ЦЕЛИКОМ (без \k вся
    # строка рисуется PrimaryColour → он обязан остаться цветом текста, не подсветки).
    hl = track.highlight if (track.highlight and track.highlight.animation != "none") else None
    primary = _ass_color(hl.color) if hl else _ass_color(st.color)  # активный/залитый
    secondary = _ass_color(st.color)  # ещё не проговорённый
    # «Ударные» слова: инлайн \1c-теги (6-hex). primary_tag = канонический цвет слова.
    emph_tag = _ass_color_tag(st.emphasis_color) if st.emphasis_color else None
    primary_tag = _ass_color_tag(hl.color) if hl else _ass_color_tag(st.color)
    outline = _ass_color(st.outline_color)
    if st.box_color:
        back = _ass_color(st.box_color, round((1.0 - st.box_opacity) * 255))
        border_style = 3
    else:
        back = "&H64000000"
        border_style = 1

    script_info = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n"
    )
    styles = (
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{st.font},{st.size},{primary},{secondary},{outline},{back},"
        f"-1,0,0,0,100,100,0,0,{border_style},{st.outline_w},{st.shadow},"
        f"{st.alignment},40,40,{st.margin_v},1\n"
    )
    events_hdr = (
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"
    )
    lines = [script_info, styles, events_hdr]

    for reply in track.replies:
        if reply.hidden or not reply.word_refs:
            continue
        rwords = [words[i] for i in reply.word_refs]
        start_c = cmap.source_to_clip(rwords[0].start)
        if start_c is None:
            continue  # слово в дырке → пропуск
        last_c = cmap.source_to_clip(rwords[-1].start)
        end_c = (last_c if last_c is not None else start_c) + (rwords[-1].end - rwords[-1].start)
        emph_set = set(reply.emphasis_refs)
        emph_positions = (
            frozenset(j for j, wr in enumerate(reply.word_refs) if wr in emph_set)
            if emph_tag
            else frozenset()
        )
        text = _reply_text(
            reply,
            rwords,
            st.uppercase,
            hl,
            emphasis_color=emph_tag,
            emph_positions=emph_positions,
            primary=primary_tag,
        )
        lines.append(
            f"Dialogue: 0,{format_ass_time(start_c)},{format_ass_time(end_c)},Default,,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def write_caption_ass(
    track: CaptionTrack, words: list[Word], cmap: ClipTimeMap, out_path: Path
) -> str:
    """Скомпилировать и записать ASS-файл. Возвращает ASS-текст."""
    ass = compile_ass(track, words, cmap)
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
