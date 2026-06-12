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

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.errors import JobError
from app.pipeline.stage3_reframe import TrackPoint, compute_crop_window

if TYPE_CHECKING:
    from app.models import SourceInterval
    from app.pipeline.stage3_reframe import TrackRegion

_STAGE = "render"

# ─────────────────────────── T5: соотношения сторон ───────────────────────────

# Выходные размеры на соотношение (все чётные → yuv420p). ASS PlayRes = эти же размеры
# (иначе libass анаморфно растянет субтитры), см. compile_ass(play_w, play_h).
_ASPECT_DIMS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
}


def aspect_to_dims(aspect: str) -> tuple[int, int]:
    """Соотношение сторон → (out_w, out_h). Неизвестное → 9:16 (дефолт). PURE."""
    return _ASPECT_DIMS.get(aspect, (1080, 1920))


def fill_crop_dims(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[int, int]:
    """Размеры fill-кропа целевого аспекта из источника (наибольшее окно, чётные). PURE.

    target ≤ source-аспект → ограничено ВЫСОТОЙ (портрет/квадрат на ландшафте): полная
    высота, узкая ширина — горизонтальное слежение за говорящим.
    target > source-аспект → ограничено ШИРИНОЙ (ландшафтный выход): полная ширина,
    вертикальный центр-кроп (слежения нет — весь кадр и так в кадре).
    """
    target = out_w / out_h
    if target <= src_w / src_h:
        crop_h = src_h
        crop_w = round(src_h * target)
    else:
        crop_w = src_w
        crop_h = round(src_w / target)
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2
    return min(crop_w, src_w), min(crop_h, src_h)


# ─────────────────────────── Engine A: pure-builders ───────────────────────────


def build_fill_crop_expr(
    points: tuple[TrackPoint, ...],
    t0_offset: float,
    src_w: int,
    src_h: int,
    *,
    crop_w: int | None = None,
) -> str:
    """Piecewise-constant if()-выражение для ffmpeg crop X-координаты (Engine A).

    t в выражении — PTS-STARTPTS (0-based после trim), t_rel = point.t - t0_offset.
    Запятые экранируются \\, для filtergraph. Последний x — else-ветка (дефолт от t0).
    Пример: if(lt(t\\,0.200)\\,312\\,if(lt(t\\,0.400)\\,315\\,320))
    crop_w (T5): ширина кропа целевого аспекта; None → 9:16 (compute_crop_window, дефолт).
    """
    if not points:
        raise JobError(_STAGE, "fill-регион без траектории (build_fill_crop_expr)")
    pairs: list[tuple[float, int]] = []
    for p in points:
        t_rel = max(0.0, round(p.t - t0_offset, 3))
        cx = p.cx if p.cx is not None else 0.5
        if crop_w is None:
            x = compute_crop_window(src_w, src_h, cx, t=0.0).x
        else:
            cxc = min(1.0, max(0.0, cx))
            x = max(0, min(round(cxc * src_w - crop_w / 2), src_w - crop_w))
        pairs.append((t_rel, x))
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


# services/worker/fonts — те же TTF, что у превью (apps/web/public/libass/fonts)
_FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"


def _fontsdir_rel(data_dir: Path) -> str | None:
    """Относительный (от cwd ffmpeg) путь к шрифтам проекта; None если папки нет."""
    if not _FONTS_DIR.is_dir():
        return None
    rel: str = os.path.relpath(_FONTS_DIR, data_dir)
    return rel.replace("\\", "/")


def _subtitles_filter(ass_name: str, fontsdir: str | None) -> str:
    """Фильтр прожига субтитров; fontsdir = шрифты проекта (Montserrat/Unbounded/Rubik),
    ОДИНАКОВЫЕ с libass.wasm-превью (apps/web/public/libass/fonts) — WYSIWYG-контракт.
    Путь относительный (от cwd ffmpeg = data_dir) — без двоеточий, не нужно экранировать.
    """
    if fontsdir:
        return f"subtitles={ass_name}:fontsdir={fontsdir}"
    return f"subtitles={ass_name}"


def _piecewise_x_expr(pairs: list[tuple[float, int]]) -> str:
    """Список (t_rel, x) → вложенный if()-expr (запятые экранированы для filtergraph). PURE."""
    pairs = sorted(pairs)
    if len(pairs) == 1:
        return str(pairs[0][1])
    expr = str(pairs[-1][1])
    for i in range(len(pairs) - 2, -1, -1):
        t_boundary = pairs[i + 1][0]
        if t_boundary > 0:
            expr = f"if(lt(t\\,{t_boundary:.3f})\\,{pairs[i][1]}\\,{expr})"
    return expr


def build_split_crop_expr(
    points: tuple[TrackPoint, ...], t0_offset: float, src_w: int, crop_w: int
) -> str:
    """Piecewise X-expr для split-половины: кроп произвольной ширины crop_w вокруг cx. PURE."""
    if not points:
        raise JobError(_STAGE, "split-регион без траектории (build_split_crop_expr)")
    pairs: list[tuple[float, int]] = []
    for p in points:
        t_rel = max(0.0, round(p.t - t0_offset, 3))
        cx = min(1.0, max(0.0, p.cx if p.cx is not None else 0.5))
        x = max(0, min(round(cx * src_w - crop_w / 2), src_w - crop_w))
        pairs.append((t_rel, x))
    return _piecewise_x_expr(pairs)


def _region_chain(
    i: int,
    mode: str,
    points: tuple[TrackPoint, ...],
    points_b: tuple[TrackPoint, ...],
    t0_offset: float,
    src_w: int,
    src_h: int,
    *,
    out_w: int,
    out_h: int,
    blur: int,
) -> str:
    """Фильтр-чейн одного региона (между trim и setsar): fit | fill | split. PURE.

    Лейблы внутри чейна уникализированы индексом региона i (урок R1c: глобальные
    [bg][fg] коллидировали на 2+ fit-регионах).
    split: верх/низ по {out_w}×{out_h/2}, кроп каждой половины = src_h*(out_w/(out_h/2))
    по ширине (full-bleed, без рамок), vstack.
    """
    if mode == "fit":
        return (
            f"split=2[bg{i}][fg{i}];"
            f"[bg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},gblur=sigma={blur}[bgb{i}];"
            f"[fg{i}]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fgb{i}];"
            f"[bgb{i}][fgb{i}]overlay=(W-w)/2:(H-h)/2"
        )
    if mode == "split":
        if not points or not points_b:
            raise JobError(_STAGE, f"split-регион #{i} без двух траекторий")
        half_h = out_h // 2
        crop_w = round(src_h * out_w / half_h / 2) * 2  # чётная ширина (yuv420p)
        if crop_w > src_w:
            raise JobError(
                _STAGE,
                f"source {src_w}x{src_h} уже, чем split-половина ({crop_w}px) — split невозможен",
            )
        xa = build_split_crop_expr(points, t0_offset, src_w, crop_w)
        xb = build_split_crop_expr(points_b, t0_offset, src_w, crop_w)
        return (
            f"split=2[pa{i}][pb{i}];"
            f"[pa{i}]crop={crop_w}:{src_h}:{xa}:0,scale={out_w}:{half_h}:flags=lanczos[pha{i}];"
            f"[pb{i}]crop={crop_w}:{src_h}:{xb}:0,scale={out_w}:{half_h}:flags=lanczos[phb{i}];"
            f"[pha{i}][phb{i}]vstack=inputs=2"
        )
    if not points:
        raise JobError(_STAGE, f"fill-регион #{i} без траектории")
    # T5: размеры кропа целевого аспекта (out_w:out_h), не жёсткое 9:16
    crop_w, crop_h = fill_crop_dims(src_w, src_h, out_w, out_h)
    if crop_w >= src_w:
        # ландшафтный выход (16:9): полная ширина, вертикальный центр-кроп, без слежения
        y = (src_h - crop_h) // 2
        return f"crop={crop_w}:{crop_h}:0:{y},scale={out_w}:{out_h}:flags=lanczos"
    x_expr = build_fill_crop_expr(points, t0_offset, src_w, src_h, crop_w=crop_w)
    return f"crop={crop_w}:{crop_h}:{x_expr}:0,scale={out_w}:{out_h}:flags=lanczos"


def _chain_video_segs(seg_labels: list[str], final_label: str) -> list[str]:
    """Chain N≥2 видео-сегментов попарным concat (жёсткий cut на границе шота). PURE.

    Граница = реальная склейка источника → жёсткий cut невидим (контент и так прыгает).
    xfade удалён намеренно: кроссфейд тайт↔широкий сам читался как зум-вспышка.
    """
    parts: list[str] = []
    current = seg_labels[0]
    for i in range(1, len(seg_labels)):
        is_last = i == len(seg_labels) - 1
        out_label = final_label if is_last else f"ch{i}"
        parts.append(f"[{current}][{seg_labels[i]}]concat=n=2:v=1:a=0[{out_label}];")
        current = out_label
    return parts


def build_smooth_filter(
    regions: list[TrackRegion],
    src_w: int,
    src_h: int,
    fps: float,
    ass_name: str | None = None,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    blur: int = 20,
    fontsdir: str | None = None,
) -> str:
    """filter_complex Engine A: split → per-region trim+crop_expr/fit → chain → [subtitles].

    fill-регион: crop=W:H:EXPR:0 (piecewise-const expr следит за лицом).
    fit-регион: blur-overlay (весь кадр + рамки, b-roll широко).
    Все переходы: жёсткий cut (pairwise concat). xfade удалён — граница = реальная
    склейка источника, поэтому hard-cut невидим.
    setsar=1 на каждом (concat требует одинаковый SAR). Аудио НЕ трогаем.
    ass_name=None → субтитры НЕ жжём (CC overlay в браузере).
    """
    if not regions:
        raise JobError(_STAGE, "smooth-фильтр требует ≥1 регион")
    n = len(regions)
    heads = "".join(f"[a{i}]" for i in range(n))
    parts = [f"[0:v]setpts=PTS-STARTPTS,split={n}{heads};"]
    for i, r in enumerate(regions):
        f0 = round(r.t0 * fps)
        f1 = round(r.t1 * fps)
        seg = _region_chain(
            i, r.mode, r.points, r.points_b, r.t0, src_w, src_h,
            out_w=out_w, out_h=out_h, blur=blur,
        )  # fmt: skip
        parts.append(
            f"[a{i}]trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS,{seg},setsar=1[s{i}];"
        )

    if n == 1:
        parts.append(
            f"[s0]{_subtitles_filter(ass_name, fontsdir)}[outv]" if ass_name else "[s0]null[outv]"
        )
    else:
        if ass_name:
            parts.extend(_chain_video_segs([f"s{i}" for i in range(n)], "cv"))
            parts.append(f"[cv]{_subtitles_filter(ass_name, fontsdir)}[outv]")
        else:
            parts.extend(_chain_video_segs([f"s{i}" for i in range(n)], "outv"))
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
    ass_name: str | None,
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
        *(["-vf", f"subtitles={ass_name}"] if ass_name else []),
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
    out_name: str,
    *,
    ass_name: str | None = None,
    regions: list[TrackRegion],
    src_w: int,
    src_h: int,
    fps: float,
    engine: str = "A",
    out_w: int = 1080,
    out_h: int = 1920,
) -> float:
    """ОДИН проход рендера клипа (V2): Engine A (ffmpeg expr) или B (cv2 pipe).

    Аудио непрерывным потоком (нет подлагов); старт выровнен на границу кадра.
    engine='A' (default) — быстрый ffmpeg; engine='B' — точная per-frame линейная интерп.
    out_w/out_h (T5) — размеры выхода соотношения сторон (9:16 дефолт). Временная сетка
    (trim по кадрам) от аспекта НЕ зависит — Δ=0 инвариант цел.
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
            out_w=out_w,
            out_h=out_h,
        )
    else:  # Engine A (default)
        fc = build_smooth_filter(
            regions, src_w, src_h, fps, ass_name, out_w=out_w, out_h=out_h,
            fontsdir=_fontsdir_rel(data_dir),
        )  # fmt: skip
        cmd = build_single_pass_cmd(source_name, aligned_start, dur, fc, out_name)
        _run_ffmpeg(cmd, data_dir)

    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"рендер не создал {out_name}")
    return round(time.perf_counter() - t0, 2)


# ─────────────────────────── Timeline render (multi-interval, спека §6) ───────────────────────────


@dataclass(frozen=True)
class TimelineSegment:
    """Плоский сегмент рендера: source-кадры/времена + reframe-режим (спека §6)."""

    src_f0: int
    src_f1: int
    src_t0: float
    src_t1: float
    mode: str
    points: tuple[TrackPoint, ...]
    region_t0: float  # interval-relative старт региона (offset для crop-expr)
    points_b: tuple[TrackPoint, ...] = ()  # split: траектория второго спикера


def flatten_timeline(
    intervals: list[SourceInterval],
    regions_per_interval: list[list[TrackRegion]],
    fps: float,
) -> list[TimelineSegment]:
    """Интервалы + регионы (interval-relative) → плоский список сегментов в SOURCE-кадрах. PURE."""
    segs: list[TimelineSegment] = []
    for iv, regions in zip(intervals, regions_per_interval, strict=True):
        for r in regions:
            st0 = round(iv.source_start + r.t0, 3)
            st1 = round(iv.source_start + r.t1, 3)
            segs.append(
                TimelineSegment(
                    src_f0=round(st0 * fps),
                    src_f1=round(st1 * fps),
                    src_t0=st0,
                    src_t1=st1,
                    mode=r.mode,
                    points=r.points,
                    region_t0=r.t0,
                    points_b=r.points_b,
                )
            )
    return segs


def build_timeline_filter(
    segments: list[TimelineSegment],
    src_w: int,
    src_h: int,
    fps: float,
    ass_name: str | None = None,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    blur: int = 20,
    fontsdir: str | None = None,
) -> str:
    """filter_complex для мульти-интервального рендера (спека §6). PURE.

    Видео: split→per-seg trim(source-кадры)+reframe→_chain_video_segs→subtitles.
    Все переходы: жёсткий cut (concat). xfade удалён — границы = реальные склейки.
    Аудио: asplit→per-seg atrim(source-времена)→concat (бесшовно, до энкода).
    """
    if not segments:
        raise JobError(_STAGE, "build_timeline_filter: пустой таймлайн")
    n = len(segments)
    vheads = "".join(f"[v{i}]" for i in range(n))
    aheads = "".join(f"[a{i}]" for i in range(n))
    parts = [f"[0:v]split={n}{vheads};[0:a]asplit={n}{aheads};"]
    for i, s in enumerate(segments):
        seg = _region_chain(
            i, s.mode, s.points, s.points_b, s.region_t0, src_w, src_h,
            out_w=out_w, out_h=out_h, blur=blur,
        )  # fmt: skip
        parts.append(
            f"[v{i}]trim=start_frame={s.src_f0}:end_frame={s.src_f1},"
            f"setpts=PTS-STARTPTS,{seg},setsar=1[sv{i}];"
        )
        parts.append(
            f"[a{i}]atrim=start={s.src_t0:.3f}:end={s.src_t1:.3f},asetpts=PTS-STARTPTS[sa{i}];"
        )

    sv_labels = [f"sv{i}" for i in range(n)]
    if n == 1:
        parts.append(
            f"[sv0]{_subtitles_filter(ass_name, fontsdir)}[outv];"
            if ass_name
            else "[sv0]null[outv];"
        )
    else:
        if ass_name:
            parts.extend(_chain_video_segs(sv_labels, "cv"))
            parts.append(f"[cv]{_subtitles_filter(ass_name, fontsdir)}[outv];")
        else:
            parts.extend(_chain_video_segs(sv_labels, "outv"))
            parts[-1] = parts[-1].rstrip(";") + ";"  # ensure trailing semicolon before audio

    sa = "".join(f"[sa{i}]" for i in range(n))
    parts.append(f"{sa}concat=n={n}:v=0:a=1[outa]")
    return "".join(parts)


def build_timeline_cmd(source: str, filter_complex: str, out_name: str) -> list[str]:
    """ffmpeg для таймлайна: ПОЛНЫЙ вход (-i), маппим [outv]/[outa] из фильтра."""
    return [
        "ffmpeg", "-y", "-i", source,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        out_name,
    ]  # fmt: skip


def render_timeline(
    data_dir: Path,
    source_name: str,
    intervals: list[SourceInterval],
    regions_per_interval: list[list[TrackRegion]],
    out_name: str,
    *,
    ass_name: str | None = None,
    src_w: int,
    src_h: int,
    fps: float,
    engine: str = "A",
    out_w: int = 1080,
    out_h: int = 1920,
) -> float:
    """Рендер mp4 из edit-state (спека §6). Возвращает латентность (с). JobError при сбое.

    1 интервал → делегирует в render_clip (проверенный путь, непрерывное аудио).
    >1 интервал → мульти-интервальный concat (Engine A; бесшовное аудио внутри filtergraph).
    out_w/out_h (T5) — размеры выхода соотношения сторон (9:16 дефолт).
    """
    if not intervals:
        raise JobError(_STAGE, "render_timeline: нет интервалов")
    (data_dir / out_name).parent.mkdir(parents=True, exist_ok=True)

    if len(intervals) == 1:
        return render_clip(
            data_dir,
            source_name,
            intervals[0].source_start,
            out_name,
            ass_name=ass_name,
            regions=regions_per_interval[0],
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            engine=engine,
            out_w=out_w,
            out_h=out_h,
        )

    segments = flatten_timeline(intervals, regions_per_interval, fps)
    fc = build_timeline_filter(
        segments, src_w, src_h, fps, ass_name, out_w=out_w, out_h=out_h,
        fontsdir=_fontsdir_rel(data_dir),
    )  # fmt: skip
    t0 = time.perf_counter()
    _run_ffmpeg(build_timeline_cmd(source_name, fc, out_name), data_dir)
    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"render_timeline не создал {out_name}")
    return round(time.perf_counter() - t0, 2)
