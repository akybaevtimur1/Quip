"""Stage 5 (Render): source + регионы V2 + captions → clips/<clip_id>.mp4 (1080×1920).

Два движка (Engine A / B) за единым интерфейсом render_clip(engine=...):

  Engine A (default, REFRAME_ENGINE=A): ОДИН ffmpeg-проход.
    split → per-region trim + crop_expr/fit → concat → subtitles. Crop X-координата =
    piecewise-constant if()-выражение (build_fill_crop_expr) следует за сглаженной
    траекторией лица; аудио непрерывным -map 0:a (нет подлагов). Быстрый (~ffmpeg).

  Engine B (REFRAME_ENGINE=B): cv2.VideoCapture per-frame → pipe raw BGR → ffmpeg stdin.
    Линейная интерполяция cx между сэмплами TrackPoint. libx264 + burn subtitles + aac.
    Медленнее (~CPU-bound), но pixelpoint-точная линейная интерполяция.

Оба движка: аудио непрерывно (нет подлагов), ASS субтитры жжём в кодировщике.
Выпилено: build_reframe_filter / per-shot нарезка на файлы (давали подлаг + чёрный кадр).

Границы: сборка фильтра/команды — PURE (unit-тесты). Запуск ffmpeg — обёртка, JobError.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from app.errors import JobError
from app.pipeline.stage3_reframe import TrackPoint, compute_crop_window

if TYPE_CHECKING:
    from app.pipeline.stage3_reframe import TrackRegion

_STAGE = "render"


# ─────────────────────────── Engine A: pure-builders ───────────────────────────


def build_fill_crop_expr(
    points: tuple[TrackPoint, ...], t0_offset: float, src_w: int, src_h: int
) -> str:
    """Piecewise-constant if()-выражение для ffmpeg crop X-координаты (Engine A).

    t в выражении — PTS-STARTPTS (0-based после trim), t_rel = point.t - t0_offset.
    Запятые экранируются \\, для filtergraph. Последний x — else-ветка (дефолт от t0).
    Пример: if(lt(t\\,0.200)\\,312\\,if(lt(t\\,0.400)\\,315\\,320))
    """
    if not points:
        raise JobError(_STAGE, "fill-регион без траектории (build_fill_crop_expr)")
    pairs: list[tuple[float, int]] = []
    for p in points:
        t_rel = max(0.0, round(p.t - t0_offset, 3))
        c = compute_crop_window(src_w, src_h, p.cx if p.cx is not None else 0.5, t=0.0)
        pairs.append((t_rel, c.x))
    pairs.sort()
    if len(pairs) == 1:
        return str(pairs[0][1])
    # Nested if: if(lt(t,T1),V0,...,Vn). Строим с конца: else=Vn.
    # Запятые в filtergraph нужно экранировать \, (двойной \ в Python = \, в строке).
    expr = str(pairs[-1][1])
    for i in range(len(pairs) - 2, -1, -1):
        t_boundary = pairs[i + 1][0]
        if t_boundary > 0:
            expr = f"if(lt(t\\,{t_boundary:.3f})\\,{pairs[i][1]}\\,{expr})"
    return expr


def build_smooth_filter(
    regions: list[TrackRegion],
    src_w: int,
    src_h: int,
    fps: float,
    ass_name: str,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    blur: int = 20,
) -> str:
    """filter_complex Engine A: split → per-region trim+crop_expr/fit → concat → subtitles.

    fill-регион: crop=W:H:EXPR:0 (piecewise-const expr следит за лицом).
    fit-регион: blur-overlay (весь кадр + рамки, b-roll широко).
    setsar=1 на каждом (concat требует одинаковый SAR). Аудио НЕ трогаем.
    """
    if not regions:
        raise JobError(_STAGE, "smooth-фильтр требует ≥1 регион")
    n = len(regions)
    crop_w = round(src_h * 9 / 16)
    heads = "".join(f"[a{i}]" for i in range(n))
    parts = [f"[0:v]setpts=PTS-STARTPTS,split={n}{heads};"]
    for i, r in enumerate(regions):
        f0 = round(r.t0 * fps)
        f1 = round(r.t1 * fps)
        if r.mode == "fit":
            seg = (
                f"split=2[bg{i}][fg{i}];"
                f"[bg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},gblur=sigma={blur}[bgb{i}];"
                f"[fg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgb{i}];"
                f"[bgb{i}][fgb{i}]overlay=(W-w)/2:(H-h)/2"
            )
        else:
            if not r.points:
                raise JobError(_STAGE, f"fill-регион #{i} без траектории")
            x_expr = build_fill_crop_expr(r.points, r.t0, src_w, src_h)
            seg = f"crop={crop_w}:{src_h}:{x_expr}:0,scale={out_w}:{out_h}:flags=lanczos"
        parts.append(
            f"[a{i}]trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS,{seg},setsar=1[s{i}];"
        )
    labels = "".join(f"[s{i}]" for i in range(n))
    parts.append(f"{labels}concat=n={n}:v=1[cv];[cv]subtitles={ass_name}[outv]")
    return "".join(parts)


def build_single_pass_cmd(
    source: str, start: float, dur: float, filter_complex: str, out_name: str
) -> list[str]:
    """ffmpeg: -ss ДО -i (выровненный старт), видео [outv], аудио непрерывным 0:a."""
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


# ─────────────────────────── Engine B: cv2 pipe ───────────────────────────


def _get_region_at(regions: list[TrackRegion], t: float) -> TrackRegion:
    """Найти активный регион для клип-времени t."""
    for r in regions:
        if r.t0 <= t < r.t1:
            return r
    return regions[-1]


def _interp_cx(region: TrackRegion, t: float) -> float:
    """Линейная интерполяция cx между ближайшими TrackPoint (Engine B)."""
    pts = region.points
    if not pts:
        return 0.5
    for i in range(len(pts) - 1):
        if pts[i].t <= t <= pts[i + 1].t:
            dt = pts[i + 1].t - pts[i].t
            if dt == 0:
                return pts[i].cx or 0.5
            alpha = (t - pts[i].t) / dt
            return (pts[i].cx or 0.5) + alpha * ((pts[i + 1].cx or 0.5) - (pts[i].cx or 0.5))
    return pts[-1].cx or 0.5 if t >= pts[-1].t else pts[0].cx or 0.5


def render_frame_by_frame(
    source: Path,
    aligned_start: float,
    dur: float,
    regions: list[TrackRegion],
    src_w: int,
    src_h: int,
    fps: float,
    ass_name: str,
    out_name: str,
    data_dir: Path,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    blur_k: int = 55,
) -> None:
    """Engine B: cv2 per-frame → pipe raw BGR → ffmpeg stdin.

    Fill: линейная интерполяция cx по TrackPoint → compute_crop_window → кроп+scale.
    Fit: blur background (GaussianBlur) + letterbox foreground overlay. aac из source.
    blur_k должен быть нечётным (GaussianBlur требует). 55 по умолчанию.
    """
    import cv2  # noqa: PLC0415

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise JobError(_STAGE, f"Engine B: не открыть {source}")
    cap.set(cv2.CAP_PROP_POS_MSEC, aligned_start * 1000)

    total_frames = round(dur * fps)
    ksize = blur_k | 1  # гарантируем нечётное
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "pipe:0",
        "-ss", str(aligned_start), "-t", str(dur), "-i", str(source),
        "-map", "0:v:0", "-map", "1:a:0?",
        "-vf", f"subtitles={ass_name}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip
    proc = subprocess.Popen(ffmpeg_cmd, cwd=data_dir, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    pipe = proc.stdin
    try:
        for frame_idx in range(total_frames):
            ret, frame = cap.read()
            if not ret:
                break
            t_clip = frame_idx / fps
            region = _get_region_at(regions, t_clip)
            if region.mode == "fit":
                bg = cv2.resize(frame, (out_w, out_h))
                bg = cv2.GaussianBlur(bg, (ksize, ksize), 0)
                scale = min(out_w / src_w, out_h / src_h)
                fw = max(2, round(src_w * scale))
                fh = max(2, round(src_h * scale))
                fw -= fw % 2
                fh -= fh % 2
                fg = cv2.resize(frame, (fw, fh))
                y_off = (out_h - fh) // 2
                x_off = (out_w - fw) // 2
                bg[y_off : y_off + fh, x_off : x_off + fw] = fg
                out_frame = bg
            else:
                cx = _interp_cx(region, t_clip)
                c = compute_crop_window(src_w, src_h, cx, t=0.0)
                cropped = frame[c.y : c.y + c.h, c.x : c.x + c.w]
                out_frame = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            if pipe is not None:
                pipe.write(out_frame.tobytes())
    finally:
        cap.release()
        if pipe is not None:
            pipe.close()
        proc.wait()
    if proc.returncode != 0:
        stderr_bytes = proc.stderr.read() if proc.stderr else b""
        stderr = stderr_bytes.decode("utf-8", errors="replace")[-400:]
        raise JobError(_STAGE, f"Engine B ffmpeg код {proc.returncode}: {stderr}")


# ─────────────────────────── Unified render_clip ───────────────────────────


def render_clip(
    data_dir: Path,
    source_name: str,
    seg_start: float,
    ass_name: str,
    out_name: str,
    *,
    regions: list[TrackRegion],
    src_w: int,
    src_h: int,
    fps: float,
    engine: str = "A",
) -> float:
    """ОДИН проход рендера клипа (V2): Engine A (ffmpeg expr) или B (cv2 pipe).

    Аудио непрерывным потоком (нет подлагов); старт выровнен на границу кадра.
    engine='A' (default) — быстрый ffmpeg; engine='B' — точная per-frame линейная интерп.
    Возвращает латентность рендера (с). JobError при сбое.
    """
    if not regions:
        raise JobError(_STAGE, "render: пустые регионы")
    (data_dir / out_name).parent.mkdir(parents=True, exist_ok=True)
    aligned_start = round(seg_start * fps) / fps
    clip_dur = max(r.t1 for r in regions)
    dur = round(seg_start + clip_dur - aligned_start, 3)

    t0 = time.perf_counter()
    if engine == "B":
        render_frame_by_frame(
            data_dir / source_name,
            aligned_start,
            dur,
            regions,
            src_w,
            src_h,
            fps,
            ass_name,
            out_name,
            data_dir,
        )
    else:  # Engine A (default)
        fc = build_smooth_filter(regions, src_w, src_h, fps, ass_name)
        cmd = build_single_pass_cmd(source_name, aligned_start, dur, fc, out_name)
        _run_ffmpeg(cmd, data_dir)

    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"рендер не создал {out_name}")
    return round(time.perf_counter() - t0, 2)
