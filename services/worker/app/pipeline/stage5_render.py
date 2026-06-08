"""Stage 5 (Render): source + план шотов + captions → clips/<clip_id>.mp4 (1080×1920, per-shot).

Per-shot (R1): каждый план — отдельный сегмент (cut + свой static-crop ИЛИ fit-блюр) →
concat-демуксер → burn субтитров ВТОРЫМ проходом. Кроп меняется ровно на склейке (встык
concat) → флешей нет by-design. -ss ДО -i сбрасывает PTS к нулю → шоты встык 0-based →
непрерывный клип-таймлайн → .ass (0-based) совпадает (R3). ffmpeg с cwd=data/<job_id> и
ОТНОСИТЕЛЬНЫМИ путями (subtitles=<file>.ass, concat-список) — без ада escaping.

Границы: сборка фильтра/команды — PURE (unit-тесты). Запуск ffmpeg — обёртка, JobError при сбое.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from app.errors import JobError
from app.models import CropWindow

if TYPE_CHECKING:
    from app.pipeline.stage3_reframe import ShotPlan

_STAGE = "render"


def build_vf_fill(crop: CropWindow, *, out_w: int = 1080, out_h: int = 1920) -> str:
    """Per-shot FILL (R1.3): crop → scale(lanczos) → setpts(PTS→0). БЕЗ субтитров.

    Каждый шот рендерим отдельным сегментом со СВОИМ статическим кропом → смена кадра
    ровно на склейке (встык concat), флешей нет by-design. Субтитры жжём после concat.
    """
    return (
        f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y},"
        f"scale={out_w}:{out_h}:flags=lanczos,setpts=PTS-STARTPTS"
    )


def build_vf_fit_shot(*, out_w: int = 1080, out_h: int = 1920, blur: int = 20) -> str:
    """Per-shot FIT (R1.3): весь кадр + размытый зум-фон (b-roll широко). БЕЗ субтитров."""
    return (
        f"setpts=PTS-STARTPTS,split=2[bg][fg];"
        f"[bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},gblur=sigma={blur}[bgb];"
        f"[fg]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgb];"
        f"[bgb][fgb]overlay=(W-w)/2:(H-h)/2"
    )


def build_concat_list(shot_files: list[str]) -> str:
    """Контент файла-списка для ffmpeg concat-демуксера (по одному ``file '<имя>'`` на строку)."""
    if not shot_files:
        raise JobError(_STAGE, "concat: пустой список шотов")
    return "".join(f"file '{f}'\n" for f in shot_files)


def build_concat_burn_cmd(list_file: str, ass_name: str, out_name: str) -> list[str]:
    """Финальный проход: concat-демуксер шотов + burn субтитров (один re-encode видео, аудио aac).

    Шоты уже встык 0-based → concat даёт непрерывный клип-таймлайн → .ass (0-based) совпадает.
    -safe 0 → относительные пути в списке (cwd=data_dir, как и burn) без ада escaping.
    """
    return [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", list_file,
        "-vf", f"subtitles={ass_name}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip


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
) -> float:
    """Per-shot рендер клипа (R1): каждый план — отдельный сегмент (свой static-crop ИЛИ
    fit-блюр) → concat-демуксер → burn субтитров ВТОРЫМ проходом. Кроп меняется ровно на
    склейке (встык concat) → флешей нет by-design; b-roll-планы показаны широко (fit).

    seg_start — абсолютный старт клипа в источнике; план — клип-относительный (t0/t1).
    cwd=data_dir (относительные пути → без ада escaping). Temp-файлы шотов/списка чистим.
    Возвращает латентность (с). JobError при сбое/отсутствии выхода.
    """
    from app.pipeline.stage3_reframe import compute_crop_window  # noqa: PLC0415

    if not shots:
        raise JobError(_STAGE, "render: пустой план шотов")
    (data_dir / out_name).parent.mkdir(parents=True, exist_ok=True)
    clip_tag = Path(out_name).stem  # clip_01
    list_name = f"_concat_{clip_tag}.txt"
    shot_files: list[str] = []
    t0 = time.perf_counter()
    try:
        for i, shot in enumerate(shots):
            if shot.mode == "fit":
                vf = build_vf_fit_shot()
            else:
                if shot.center is None:
                    raise JobError(_STAGE, f"fill-шот без center: {clip_tag}#{i}")
                vf = build_vf_fill(compute_crop_window(src_w, src_h, shot.center, t=shot.t0))
            shot_name = f"_shot_{clip_tag}_{i:02d}.mp4"
            _run_ffmpeg(
                build_ffmpeg_cmd(
                    source_name, seg_start + shot.t0, seg_start + shot.t1, vf, shot_name
                ),
                data_dir,
            )
            shot_files.append(shot_name)
        (data_dir / list_name).write_text(build_concat_list(shot_files), encoding="utf-8")
        _run_ffmpeg(build_concat_burn_cmd(list_name, ass_name, out_name), data_dir)
        if not (data_dir / out_name).exists():
            raise JobError(_STAGE, f"рендер не создал {out_name}")
    finally:
        for sf in shot_files:
            (data_dir / sf).unlink(missing_ok=True)
        (data_dir / list_name).unlink(missing_ok=True)
    return round(time.perf_counter() - t0, 2)
