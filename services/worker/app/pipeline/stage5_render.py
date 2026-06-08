"""Stage 5 (Render): source + план шотов + captions → clips/<clip_id>.mp4 (1080×1920, ОДИН проход).

Один проход декода (R1c, фикс подлагов аудио + чёрных кадров): аудио НЕ режем — отдаём
непрерывным потоком (`-map 0:a`), поэтому ноль подлагов/рассинхрона на склейках. Видео: один
`split` → каждый шот `trim` ПО НОМЕРАМ КАДРОВ (frame-exact) + свой crop (fill) или blur-fit (fit)
→ `concat`-фильтр стыкует декодированные кадры встык → `subtitles`. Старт выровнен на границу
кадра (`-ss` = round(seg_start*fps)/fps) → trim-границы совпадают с реальными склейками источника
(кроп меняется ровно на кадре-склейке, без чёрных кадров от промаха на 1 кадр).

Прежнее решение (нарезка на отдельные файлы + concat-демуксер) выпилено: оно давало подлаг
аудио (priming AAC на каждом стыке копился) и чёрный кадр на стыке (старт на дробном кадре).

Границы: сборка фильтра/команды — PURE (unit-тесты). Запуск ffmpeg — обёртка, JobError при сбое.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from app.errors import JobError
from app.pipeline.stage3_reframe import compute_crop_window

if TYPE_CHECKING:
    from app.pipeline.stage3_reframe import ShotPlan

_STAGE = "render"


def build_reframe_filter(
    shots: list[ShotPlan],
    src_w: int,
    src_h: int,
    fps: float,
    ass_name: str,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    blur: int = 20,
) -> str:
    """filter_complex одного прохода: split → per-shot trim + crop/fit → concat → субтитры.

    Каждый шот режется `trim` ПО КАДРАМ (frame-exact) своим фильтром: fill → crop 9:16 +
    scale; fit → весь кадр + блюр-рамки. setsar=1 на каждом (иначе concat падает). concat
    стыкует декодированные кадры (нет таймстамп-дыр → нет чёрных кадров). Субтитры — после
    concat (0-based клип-таймлайн). Аудио НЕ трогаем (непрерывный поток в render_clip).
    """
    if not shots:
        raise JobError(_STAGE, "reframe-фильтр требует ≥1 шот")
    n = len(shots)
    heads = "".join(f"[a{i}]" for i in range(n))
    parts = [f"[0:v]setpts=PTS-STARTPTS,split={n}{heads};"]
    for i, s in enumerate(shots):
        f0 = round(s.t0 * fps)
        f1 = round(s.t1 * fps)
        if s.mode == "fit":
            # лейблы УНИКАЛЬНЫ по шоту (filtergraph-лейблы глобальны → иначе коллизия на 2+ fit)
            seg = (
                f"split=2[bg{i}][fg{i}];"
                f"[bg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},gblur=sigma={blur}[bgb{i}];"
                f"[fg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgb{i}];"
                f"[bgb{i}][fgb{i}]overlay=(W-w)/2:(H-h)/2"
            )
        else:
            if s.center is None:
                raise JobError(_STAGE, f"fill-шот без center: #{i}")
            c = compute_crop_window(src_w, src_h, s.center, t=0.0)
            seg = f"crop={c.w}:{c.h}:{c.x}:0,scale={out_w}:{out_h}:flags=lanczos"
        # setsar=1 нормализует SAR — иначе concat падает (fill и fit дают разный sample-aspect).
        parts.append(
            f"[a{i}]trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS,{seg},setsar=1[s{i}];"
        )
    labels = "".join(f"[s{i}]" for i in range(n))
    parts.append(f"{labels}concat=n={n}:v=1[cv];[cv]subtitles={ass_name}[outv]")
    return "".join(parts)


def build_single_pass_cmd(
    source: str, start: float, dur: float, filter_complex: str, out_name: str
) -> list[str]:
    """ffmpeg: -ss ДО -i (выровненный старт), видео [outv], аудио непрерывным 0:a (не режем)."""
    return [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", source, "-t", str(dur),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip


def _run_ffmpeg(cmd: list[str], cwd: Path) -> None:
    """Запуск ffmpeg с cwd; JobError при отсутствии бинарника или ненулевом коде (№8)."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
    if proc.returncode != 0:
        raise JobError(_STAGE, f"ffmpeg код {proc.returncode}: {(proc.stderr or '')[-400:]}")


def render_clip(
    data_dir: Path,
    source_name: str,
    seg_start: float,
    ass_name: str,
    out_name: str,
    *,
    shots: list[ShotPlan],
    src_w: int,
    src_h: int,
    fps: float,
) -> float:
    """ОДИН проход рендера клипа (R1c): видео — per-shot crop/fit через trim+concat-фильтр;
    аудио — непрерывным потоком (нет подлагов); кроп меняется ровно на склейке (нет чёрных кадров).

    seg_start — абсолютный старт клипа; выравниваем на границу кадра, чтобы trim-кадры совпали с
    реальными склейками. cwd=data_dir (относит. пути). Латентность (с). JobError при сбое.
    """
    if not shots:
        raise JobError(_STAGE, "render: пустой план шотов")
    (data_dir / out_name).parent.mkdir(parents=True, exist_ok=True)
    aligned_start = round(seg_start * fps) / fps  # старт ровно на границе кадра
    clip_dur = max(s.t1 for s in shots)
    dur = round(seg_start + clip_dur - aligned_start, 3)
    fc = build_reframe_filter(shots, src_w, src_h, fps, ass_name)
    cmd = build_single_pass_cmd(source_name, aligned_start, dur, fc, out_name)
    t0 = time.perf_counter()
    _run_ffmpeg(cmd, data_dir)
    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"рендер не создал {out_name}")
    return round(time.perf_counter() - t0, 2)
