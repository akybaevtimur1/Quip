"""СПАЙК (доказательство wrap-парити): рендерит ОДИН кадр субтитра через ffmpeg (libass,
тот же движок, что превью libass.wasm) при wrap_width=None и wrap_width=0.5 и доказывает, что
ограничение ширины РЕАЛЬНО переносит текст на больше строк / в более узкий блок БЕЗ смены кегля.

Почему этого достаточно для WYSIWYG: превью (libass.wasm) и экспорт (ffmpeg) потребляют
ИДЕНТИЧНУЮ ASS-строку из одного генератора (captions_v2). Значит структурная парити
гарантирована, как только ASS верен; ffmpeg-рендер тут — независимая проверка, что libass
действительно трактует MarginL/MarginR как ограничитель ширины переноса (а не косметику).

Пропускается, если ffmpeg недоступен (CI без ffmpeg) — тогда полагаемся на unit-тесты ASS.
Запуск: uv run pytest tests/spike -q  (PowerShell с PATH refresh).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.editor.captions_v2 import compile_ass
from app.editor.timemap import ClipTimeMap
from app.models import CaptionReply, CaptionStyle, CaptionTrack, SourceInterval, Word

_FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")

_PLAY_W, _PLAY_H = 1080, 1920


def _track(wrap_width: float | None) -> CaptionTrack:
    # длинная фраза, чтобы перенос был наглядным
    return CaptionTrack(
        style=CaptionStyle(uppercase=False, wrap_width=wrap_width, size=70),
        highlight=None,
        replies=[CaptionReply(word_refs=list(range(10)))],
    )


def _words() -> list[Word]:
    txt = "the quick brown fox jumps over the very lazy dog".split()
    return [Word(text=t, start=i * 0.2, end=i * 0.2 + 0.18) for i, t in enumerate(txt)]


def _render_one_frame(ass_path: Path, png_path: Path) -> None:
    # чёрный фон PlayRes-размера, прожиг ASS, один кадр PNG; fontsdir = шрифты проекта.
    # ffmpeg subtitles-фильтр требует Unix-стиль/escape пути на Windows: используем относительный
    # запуск из каталога с .ass, чтобы не возиться с экранированием двоеточия диска.
    cwd = ass_path.parent
    # ffmpeg-filter: двоеточие разделяет опции фильтра → абсолютный Windows-путь (C:/...) ломает
    # парсер. Зеркалим прод (stage5_render._fontsdir_rel): ОТНОСИТЕЛЬНЫЙ путь от cwd ffmpeg.
    fontsdir = os.path.relpath(_FONTS_DIR, cwd).replace("\\", "/")
    vf = f"subtitles={ass_path.name}:fontsdir={fontsdir}"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s={_PLAY_W}x{_PLAY_H}:d=1",
        "-vf", vf, "-frames:v", "1", "-update", "1", png_path.name,
    ]  # fmt: skip
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _ink_bbox_width_and_rows(png_path: Path) -> tuple[int, int]:
    """(ширина по X непрозрачно-белого текста, число строк-полос). Грубая метрика через PIL."""
    from PIL import Image

    img = Image.open(png_path).convert("L")  # текст белый на чёрном
    px = img.load()
    w, h = img.size
    min_x, max_x = w, 0
    rows_with_ink = []
    for y in range(0, h, 4):  # шаг 4px — достаточно для подсчёта полос
        row_has = False
        for x in range(0, w, 4):
            if px[x, y] > 80:
                row_has = True
                min_x = min(min_x, x)
                max_x = max(max_x, x)
        rows_with_ink.append(row_has)
    width = max(0, max_x - min_x)
    # число «полос» текста = группы подряд идущих строк с чернилами
    bands = 0
    prev = False
    for r in rows_with_ink:
        if r and not prev:
            bands += 1
        prev = r
    return width, bands


def test_wrap_width_narrows_block_and_adds_lines(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    cmap = ClipTimeMap([SourceInterval(source_start=0.0, source_end=3.0)])
    words = _words()

    full = compile_ass(_track(None), words, cmap, play_w=_PLAY_W, play_h=_PLAY_H)
    half = compile_ass(_track(0.5), words, cmap, play_w=_PLAY_W, play_h=_PLAY_H)

    (tmp_path / "full.ass").write_text(full, encoding="utf-8")
    (tmp_path / "half.ass").write_text(half, encoding="utf-8")
    _render_one_frame(tmp_path / "full.ass", tmp_path / "full.png")
    _render_one_frame(tmp_path / "half.ass", tmp_path / "half.png")

    w_full, bands_full = _ink_bbox_width_and_rows(tmp_path / "full.png")
    w_half, bands_half = _ink_bbox_width_and_rows(tmp_path / "half.png")

    # wrap_width=0.5 → блок заметно уже и переносится на БОЛЬШЕ строк (тот же кегль)
    assert w_half < w_full, f"half width {w_half} should be < full {w_full}"
    assert bands_half > bands_full, f"half bands {bands_half} should be > full {bands_full}"
    # узкий блок не шире ~половины кадра + контур/паддинг
    assert w_half <= _PLAY_W * 0.62, f"half block {w_half}px wider than expected"
