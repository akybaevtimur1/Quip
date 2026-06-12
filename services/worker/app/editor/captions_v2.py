"""Компиляция CaptionTrack → ASS (спека §7). PURE.

Один источник правды (CaptionTrack) → ASS для рендера (libass). Караоке = нативный {\\k}.
"""

from __future__ import annotations

from pathlib import Path

from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionTrack, HighlightStyle, HookOverlay, Word
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
    style = (
        f"Style: Hook,{hook.font},{hook.size},{primary},{primary},{outline},{back},"
        f"-1,0,0,0,100,100,0,0,{border_style},{outline_w},{hook.shadow},"
        f"8,60,60,{hook.margin_v},1"
    )
    window = clip_duration if hook.full_clip else min(hook.duration_sec, clip_duration)
    text = hook.text.replace("\n", " ").strip()
    if hook.uppercase:
        text = text.upper()
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
        return s.upper() if uppercase else s

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
    base_tag = _ass_color_tag(st.color)  # цвет текста — куда возвращается color_sweep
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
        lines.append(
            f"Dialogue: 0,{format_ass_time(start_c)},{format_ass_time(end_c)},Default,,0,0,,{text}"
        )
    if hook_dialogue is not None:
        lines.append(hook_dialogue)
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
