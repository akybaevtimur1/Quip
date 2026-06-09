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


def _reply_text(
    reply: CaptionReply, rwords: list[Word], uppercase: bool, hl: HighlightStyle | None
) -> str:
    def up(s: str) -> str:
        return s.upper() if uppercase else s

    if reply.text_override is not None:
        ov = reply.text_override.split()
        if hl and len(ov) == len(rwords):
            return " ".join(
                f"{{\\k{round((w.end - w.start) * 100)}}}{up(o)}"
                for o, w in zip(ov, rwords, strict=True)
            )
        return up(reply.text_override)
    if hl:
        return " ".join(f"{{\\k{round((w.end - w.start) * 100)}}}{up(w.text)}" for w in rwords)
    return " ".join(up(w.text) for w in rwords)


def compile_ass(track: CaptionTrack, words: list[Word], cmap: ClipTimeMap) -> str:
    """CaptionTrack + слова + тайм-маппинг → полный ASS-текст (тайминги в КЛИП-времени)."""
    st = track.style
    hl = track.highlight
    primary = _ass_color(hl.color) if hl else _ass_color(st.color)  # активный/залитый
    secondary = _ass_color(st.color)  # ещё не проговорённый
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
        text = _reply_text(reply, rwords, st.uppercase, hl)
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
