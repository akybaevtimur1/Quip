"""Stage 5 (Render): source + crop + captions → clips/<clip_id>.mp4 (1080×1920, один проход ffmpeg).

Один проход: cut (input -ss + -t) → crop → scale 1080×1920 → setpts (PTS→0) → burn субтитров
→ libx264/aac. -ss ДО -i сбрасывает PTS к нулю, чтобы клип-тайминг .ass совпал (R3).
ffmpeg запускаем с cwd=data/<job_id> и ОТНОСИТЕЛЬНЫМ subtitles=<file>.ass (без ада escaping).

Границы: сборка фильтра/команды — PURE (unit-тесты). Запуск ffmpeg — обёртка, JobError при сбое.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from app.errors import JobError
from app.models import CropWindow

_STAGE = "render"


def build_vf(crop: CropWindow, ass_name: str, *, out_w: int = 1080, out_h: int = 1920) -> str:
    """FILL: crop → scale(lanczos) → setpts(PTS→0) → burn субтитров (отн. имя .ass)."""
    return (
        f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y},"
        f"scale={out_w}:{out_h}:flags=lanczos,setpts=PTS-STARTPTS,subtitles={ass_name}"
    )


def build_vf_fit(ass_name: str, *, out_w: int = 1080, out_h: int = 1920, blur: int = 20) -> str:
    """FIT: весь кадр целиком в центре + размытый зум-фон сверху/снизу (ничего не режет).

    split → bg(заполнить+crop+blur) + fg(вписать целиком) → overlay по центру → субтитры.
    """
    return (
        f"setpts=PTS-STARTPTS,split=2[bg][fg];"
        f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},gblur=sigma={blur}[bgb];"
        f"[fg]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgb];"
        f"[bgb][fgb]overlay=(W-w)/2:(H-h)/2,subtitles={ass_name}"
    )


def build_crop_x_step_expr(windows: list[tuple[float, int]]) -> str:
    """СТУПЕНЧАТЫЙ x(t) (hold & cut): x держится константой внутри плана, мгновенно скачет
    на границе плана. Вход — (shot_start_t, x) по возрастанию t. Соседние равные x схлопываем.

    1 план → константа. N → вложенные ``if(lt(t,T_i), X_{i-1}, …)``. БЕЗ экранирования
    (его делает build_vf_dynamic). Время t — КЛИП-относительное.
    """
    if not windows:
        raise ValueError("нужен ≥1 план для x-выражения")
    reduced: list[tuple[float, int]] = [windows[0]]
    for t, x in windows[1:]:
        if x != reduced[-1][1]:
            reduced.append((t, x))
    if len(reduced) == 1:
        return str(reduced[0][1])
    expr = str(reduced[-1][1])
    for i in range(len(reduced) - 1, 0, -1):
        boundary = reduced[i][0]
        x_before = reduced[i - 1][1]
        expr = f"if(lt(t,{boundary}),{x_before},{expr})"
    return expr


def build_vf_dynamic(
    crops: list[CropWindow], ass_name: str, *, out_w: int = 1080, out_h: int = 1920
) -> str:
    """FILL cut-aware: окно держит план, скачок на склейке. setpts ПЕРВЫМ → crop видит
    клип-время (0-based). x(t) — СТУПЕНЧАТОЕ выражение; запятые экранируем ``\\,`` для
    filtergraph-парсера (vf уходит одним argv, без shell). w/h из первого окна (постоянны).
    """
    if not crops:
        raise JobError(_STAGE, "динамический кроп требует ≥1 окна")
    w, h = crops[0].w, crops[0].h
    x_expr = build_crop_x_step_expr([(c.t, c.x) for c in crops])
    x_esc = x_expr.replace(",", "\\,")
    return (
        f"setpts=PTS-STARTPTS,crop={w}:{h}:{x_esc}:0,"
        f"scale={out_w}:{out_h}:flags=lanczos,subtitles={ass_name}"
    )


def build_ffmpeg_cmd(source: str, start: float, end: float, vf: str, out_name: str) -> list[str]:
    """Команда ffmpeg: -ss ДО -i (PTS→0 для синка субтитров), -t = длительность сегмента."""
    dur = round(end - start, 3)
    return [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", source, "-t", str(dur),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip


def render_clip(
    data_dir: Path,
    source_name: str,
    start: float,
    end: float,
    ass_name: str,
    out_name: str,
    *,
    mode: str = "fill",
    crop: list[CropWindow] | None = None,
) -> float:
    """Один клип: ffmpeg cut + (fill-кроп | fit-блюр) + burn + encode. cwd=data_dir.

    crop — трек окон 9:16: 1 окно → статический кроп; >1 → динамический (x едет за лицом).
    Возвращает латентность (с). JobError при сбое/отсутствии выхода.
    """
    (data_dir / out_name).parent.mkdir(parents=True, exist_ok=True)
    if mode == "fit":
        vf = build_vf_fit(ass_name)
    else:
        if not crop:
            raise JobError(_STAGE, "fill-режим требует crop-окно(а)")
        vf = build_vf_dynamic(crop, ass_name) if len(crop) > 1 else build_vf(crop[0], ass_name)
    cmd = build_ffmpeg_cmd(source_name, start, end, vf, out_name)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=data_dir, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"не найден ffmpeg: {e}") from e
    if proc.returncode != 0:
        raise JobError(_STAGE, f"ffmpeg render код {proc.returncode}: {(proc.stderr or '')[-400:]}")
    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"рендер не создал {out_name}")
    return round(time.perf_counter() - t0, 2)
