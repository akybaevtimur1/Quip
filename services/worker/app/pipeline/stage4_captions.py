"""Stage 4 (Captions): transcript + сегмент → captions_<clip_id>.ass (тайминг от клипа).

Всё PURE (вход→выход, без сети) → целиком под unit-тестами. Критично (R3): времена
субтитров СЧИТАЕМ ОТ НАЧАЛА КЛИПА: t_clip = t_source - segment.start (изолировано в
``to_clip_time`` — единственная точка ошибок «±длина клипа»).

Стиль: один brand-neutral (Montserrat 90, толстый чёрный контур, MarginV=260, .upper()).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from app.models import Word

_SENT_END = (".", "!", "?")

# ── ASS-шаблон (PlayRes 1080x1920; Montserrat 90; контур 6 + тень; снизу по центру) ──
_SCRIPT_INFO = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
    "WrapStyle: 2\nScaledBorderAndShadow: yes\n"
)
_STYLES = (
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Montserrat,90,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
    "-1,0,0,0,100,100,0,0,1,6,2,2,40,40,260,1\n"
)
_EVENTS_HDR = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, Effect, Text\n"


class CaptionChunk(BaseModel):
    """Группа слов в одну реплику субтитра (времена — в секундах source)."""

    words: list[Word]
    text: str
    start: float
    end: float


def _ends_sentence(text: str) -> bool:
    return text.strip().rstrip("\"'»").endswith(_SENT_END)


def to_clip_time(t_source: float, segment_start: float) -> float:
    """t_clip = t_source - segment.start (клип ≥ 0). ЕДИНСТВЕННАЯ точка пересчёта времени (R3)."""
    return round(max(0.0, t_source - segment_start), 3)


def format_ass_time(seconds: float) -> str:
    """Секунды → ASS-время ``H:MM:SS.cc`` (центисекунды)."""
    cs = round(max(0.0, seconds) * 100)
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def words_in_segment(words: list[Word], start: float, end: float) -> list[Word]:
    """Слова, начинающиеся внутри [start, end)."""
    return [w for w in words if start <= w.start < end]


def _mk_chunk(ws: list[Word]) -> CaptionChunk:
    return CaptionChunk(
        words=list(ws), text=" ".join(w.text for w in ws), start=ws[0].start, end=ws[-1].end
    )


def group_words_into_chunks(
    words: list[Word], *, max_words: int = 5, max_gap: float = 0.4, max_dur: float = 2.5
) -> list[CaptionChunk]:
    """Группировка в чанки 3–5 слов. Разрыв при: ≥max_words, паузе >max_gap, длине >max_dur,
    либо предыдущее слово заканчивает предложение (.?!).
    """
    chunks: list[CaptionChunk] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            prev = cur[-1]
            gap = w.start - prev.end
            dur_if_added = w.end - cur[0].start
            if (
                len(cur) >= max_words
                or gap > max_gap
                or dur_if_added > max_dur
                or _ends_sentence(prev.text)
            ):
                chunks.append(_mk_chunk(cur))
                cur = []
        cur.append(w)
    if cur:
        chunks.append(_mk_chunk(cur))
    return chunks


def build_ass(
    words: list[Word],
    *,
    segment_start: float,
    max_words: int = 5,
    max_gap: float = 0.4,
    max_dur: float = 2.5,
) -> str:
    """Слова клипа (в координатах source) → полный ASS-текст с таймингом ОТ КЛИПА."""
    chunks = group_words_into_chunks(words, max_words=max_words, max_gap=max_gap, max_dur=max_dur)
    lines = [_SCRIPT_INFO, _STYLES, _EVENTS_HDR]
    for ch in chunks:
        start = format_ass_time(to_clip_time(ch.start, segment_start))
        end = format_ass_time(to_clip_time(ch.end, segment_start))
        text = ch.text.upper().replace("\n", " ")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,,{text}")
    return "\n".join(lines) + "\n"


def write_captions_ass(
    words: list[Word], segment_start: float, segment_end: float, out_path: Path
) -> str:
    """Отфильтровать слова сегмента, собрать ASS, записать файл. Возвращает ASS-текст."""
    seg_words = words_in_segment(words, segment_start, segment_end)
    ass = build_ass(seg_words, segment_start=segment_start)
    out_path.write_text(ass, encoding="utf-8")
    return ass
