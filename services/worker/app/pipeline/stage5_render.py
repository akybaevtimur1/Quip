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


def clamp_output_dims(out_w: int, out_h: int, max_resolution: int) -> tuple[int, int]:
    """Снизить (out_w,out_h) так, чтобы МЕНЬШАЯ сторона ≤ max_resolution (free→720p). PURE.

    «720p»/«1080p» вертикали = меньшая сторона (ширина для портрета): 1080×1920 → 720×1280.
    Меньшая сторона уже ≤ потолка → без изменений (не апскейлим). Масштаб пропорционален
    (аспект сохранён); обе стороны округляются до чётного (yuv420p). НЕ трогает временную сетку
    (trim по SOURCE-кадрам от out_w/out_h не зависит, см. render_clip) → Δ=0 инвариант цел.
    """
    short_side = min(out_w, out_h)
    if short_side <= max_resolution:
        return out_w, out_h
    scale = max_resolution / short_side
    new_w = round(out_w * scale)
    new_h = round(out_h * scale)
    new_w -= new_w % 2
    new_h -= new_h % 2
    return new_w, new_h


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
    """Piecewise-ЛИНЕЙНОЕ if()-выражение для ffmpeg crop X-координаты (Engine A): рампим x
    между кейфреймами → плавный пан (раньше был piecewise-const = ступеньки/резкие скачки).

    t в выражении — PTS-STARTPTS (0-based после trim), t_rel = point.t - t0_offset.
    Запятые экранируются \\, для filtergraph. После последнего кейфрейма x держится константой.
    Пример: if(lt(t\\,0.200)\\,(312+(15.0000)*(t-0.000))\\,320)
    crop_w (T5): ширина кропа целевого аспекта; None → 9:16 (compute_crop_window, дефолт).
    """
    if not points:
        raise JobError(_STAGE, "fill region has no trajectory (build_fill_crop_expr)")
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
    # Дедуп по t_rel (одинаковое округлённое время → делёж на 0 в рампе; держим последний x).
    dedup: list[tuple[float, int]] = []
    for t_rel, x in pairs:
        if dedup and abs(t_rel - dedup[-1][0]) < 1e-6:
            dedup[-1] = (t_rel, x)
        else:
            dedup.append((t_rel, x))
    pairs = dedup
    if len(pairs) == 1:
        return str(pairs[0][1])
    # Если первый кейфрейм не в t=0 (трек начинается на пару кадров позже старта региона) —
    # держим его x от t=0 (как старый step), чтобы рамп не экстраполировал НАЗАД до t0.
    if pairs[0][0] > 1e-6:
        pairs.insert(0, (0.0, pairs[0][1]))
    # Piecewise-ЛИНЕЙНЫЙ пан: между кейфреймами рампим x = x0 + slope*(t-t0) → ПЛАВНОЕ движение
    # в скачанном файле (раньше Engine A держал x ступенькой = резкие скачки ~3% ширины). После
    # последнего кейфрейма x держится константой (else-ветка). Первый кейфрейм всегда t_rel=0
    # (старт региона после setpts=PTS-STARTPTS) → экстраполяции до t0 нет; рамп идёт между уже
    # клампнутыми в кадр значениями x. ⚠️ Меняем ТОЛЬКО cx ВНУТРИ fill-региона: границы регионов
    # (trim-кадры round(t0*fps)) НЕ трогаются → кадровая сетка и переходы fill↔fit/split целы,
    # флеши невозможны (см. docs/REFRAME_FPS_GRID_INVARIANT.md §«Что МОЖНО менять»).
    expr = str(pairs[-1][1])
    for i in range(len(pairs) - 2, -1, -1):
        t0i, x0i = pairs[i]
        t1i, x1i = pairs[i + 1]
        slope = (x1i - x0i) / (t1i - t0i)  # t1i>t0i после дедупа → не делим на 0
        ramp = f"({x0i}+({slope:.4f})*(t-{t0i:.3f}))"
        expr = f"if(lt(t\\,{t1i:.3f})\\,{ramp}\\,{expr})"
    return expr


# services/worker/fonts — те же TTF, что у превью (apps/web/public/libass/fonts)
_FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"


def _fontsdir_rel(data_dir: Path) -> str | None:
    """Относительный (от cwd ffmpeg) путь к шрифтам проекта; None если папки нет."""
    if not _FONTS_DIR.is_dir():
        return None
    rel: str = os.path.relpath(_FONTS_DIR, data_dir)
    return rel.replace("\\", "/")


_WATERMARK_TEXT = "Made with Quip"


def build_watermark_drawtext(out_w: int, out_h: int, fontfile: str | None) -> str:
    """drawtext-фильтр вотермарки «Made with Quip» в нижнем-правом углу (free-план). PURE.

    Аддитивный оверлей поверх ГОТОВОГО кадра на финальном энкоде — НЕ трогает trim/crop/fps,
    поэтому кадровая сетка reframe (Δ=0) цела (см. docs/REFRAME_FPS_GRID_INVARIANT.md). Текст
    полупрозрачный белый с лёгкой тенью (читаемо на любом фоне, не разрушает клип). Размер
    шрифта и отступ пропорциональны высоте выхода (одинаково смотрится на 9:16/1:1/4:5/16:9).
    fontfile (опц.) — относительный (от cwd ffmpeg) путь к TTF проекта; None → шрифт ffmpeg.
    Запятые НЕ используются в выражениях (drawtext в filtergraph их бы съел как разделитель).
    """
    fontsize = max(16, round(out_h * 0.022))  # ~42px на 1920 высоте
    pad = max(12, round(out_h * 0.016))
    font = f"fontfile={fontfile}:" if fontfile else ""
    return (
        f"drawtext={font}text='{_WATERMARK_TEXT}':"
        f"fontsize={fontsize}:fontcolor=white@0.78:"
        f"shadowcolor=black@0.45:shadowx=2:shadowy=2:"
        f"x=w-tw-{pad}:y=h-th-{pad}"
    )


def _final_video_chain(
    in_label: str, ass_name: str | None, fontsdir: str | None, watermark_dt: str | None
) -> str:
    """Финальная видео-цепочка на [outv]: [in](subtitles?)(drawtext-вотермарка?). PURE.

    Порядок: субтитры прожигаются ПЕРВЫМИ (часть контента клипа), вотермарка — ПОСЛЕДНЕЙ
    (поверх всего, включая субтитры). Оба — аддитивные фильтры на готовом кадре, кадровую
    сетку не трогают. Нет ни субтитров, ни вотермарки → null-копи лейбла в [outv].
    """
    filters: list[str] = []
    if ass_name:
        filters.append(_subtitles_filter(ass_name, fontsdir))
    if watermark_dt:
        filters.append(watermark_dt)
    if not filters:
        return f"[{in_label}]null[outv]"
    return f"[{in_label}]{','.join(filters)}[outv]"


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
        raise JobError(_STAGE, "split region has no trajectory (build_split_crop_expr)")
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
            raise JobError(_STAGE, f"split region #{i} is missing two trajectories")
        half_h = out_h // 2
        crop_w = round(src_h * out_w / half_h / 2) * 2  # чётная ширина (yuv420p)
        if crop_w > src_w:
            raise JobError(
                _STAGE,
                f"source {src_w}x{src_h} is narrower than the split half "
                f"({crop_w}px) — split impossible",
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
        raise JobError(_STAGE, f"fill region #{i} has no trajectory")
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
    watermark: bool = False,
) -> str:
    """filter_complex Engine A: split → per-region trim+crop_expr/fit → chain → [subtitles].

    fill-регион: crop=W:H:EXPR:0 (piecewise-const expr следит за лицом).
    fit-регион: blur-overlay (весь кадр + рамки, b-roll широко).
    Все переходы: жёсткий cut (pairwise concat). xfade удалён — граница = реальная
    склейка источника, поэтому hard-cut невидим.
    setsar=1 на каждом (concat требует одинаковый SAR). Аудио НЕ трогаем.
    ass_name=None → субтитры НЕ жжём (CC overlay в браузере).
    watermark=True (free-план) → аддитивный drawtext «Made with Quip» поверх ГОТОВОГО кадра
    (после субтитров) — НЕ трогает кадровую сетку (Δ=0, см. REFRAME_FPS_GRID_INVARIANT).
    """
    if not regions:
        raise JobError(_STAGE, "smooth filter requires ≥1 region")
    n = len(regions)
    wm = build_watermark_drawtext(out_w, out_h, fontsdir) if watermark else None
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
        final_in = "s0"
    else:
        final_in = "cv"
        parts.extend(_chain_video_segs([f"s{i}" for i in range(n)], final_in))
    parts.append(_final_video_chain(final_in, ass_name, fontsdir, wm))
    return "".join(parts)


def _video_out_args(crf: int, preset: str) -> list[str]:
    """Выходные args ffmpeg (видео+аудио). Качество (crf/preset) приходит из RenderPolicy
    владельца джоба → платные планы рендерят чётче (ниже crf, медленнее preset), free — быстрый
    дефолт. yuv420p — совместимость браузер/соцсети; faststart — moov вперёд. Меняет ТОЛЬКО энкод,
    НЕ кадровую сетку (trim/fps/регионы) → Δ=0 инвариант цел (REFRAME_FPS_GRID_INVARIANT). PURE."""
    return [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
    ]  # fmt: skip


def build_single_pass_cmd(
    source: str, start: float, dur: float, filter_complex: str, out_name: str,
    *, crf: int = 20, preset: str = "veryfast",
) -> list[str]:  # fmt: skip
    """ffmpeg: -ss ДО -i (выровненный старт), видео [outv], аудио непрерывным 0:a."""
    return [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", source, "-t", str(dur),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a",
        *_video_out_args(crf, preset),
        out_name,
    ]  # fmt: skip


def _run_ffmpeg(cmd: list[str], cwd: Path) -> None:
    """Запуск ffmpeg с cwd; JobError при отсутствии бинарника или ненулевом коде (№8)."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise JobError(_STAGE, f"ffmpeg not found: {e}") from e
    if proc.returncode != 0:
        raise JobError(_STAGE, f"ffmpeg exit code {proc.returncode}: {(proc.stderr or '')[-400:]}")


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
    watermark: bool = False,
    crf: int = 20,
    preset: str = "veryfast",
) -> None:
    """Engine B: cv2 per-frame → pipe raw BGR → ffmpeg stdin.

    Fill: линейная интерполяция cx по TrackPoint → compute_crop_window → кроп+scale.
    Fit: blur background (GaussianBlur) + letterbox foreground overlay. aac из source.
    blur_k должен быть нечётным (GaussianBlur требует). 55 по умолчанию.
    watermark=True (free) → аддитивный drawtext «Made with Quip» в -vf (после субтитров).
    """
    import cv2  # noqa: PLC0415

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise JobError(_STAGE, f"Engine B: cannot open {source}")
    cap.set(cv2.CAP_PROP_POS_MSEC, aligned_start * 1000)

    total_frames = round(dur * fps)
    ksize = blur_k | 1  # гарантируем нечётное
    # -vf: субтитры ПЕРВЫМИ (контент), вотермарка ПОСЛЕДНЕЙ (поверх). Оба — на готовом кадре.
    vf_filters: list[str] = []
    if ass_name:
        vf_filters.append(f"subtitles={ass_name}")
    if watermark:
        vf_filters.append(build_watermark_drawtext(out_w, out_h, _fontsdir_rel(data_dir)))
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}", "-r", str(fps), "-i", "pipe:0",
        "-ss", str(aligned_start), "-t", str(dur), "-i", str(source),
        "-map", "0:v:0", "-map", "1:a:0?",
        *(["-vf", ",".join(vf_filters)] if vf_filters else []),
        *_video_out_args(crf, preset),
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
        raise JobError(_STAGE, f"Engine B ffmpeg exit code {proc.returncode}: {stderr}")


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
    watermark: bool = False,
    crf: int = 20,
    preset: str = "veryfast",
) -> float:
    """ОДИН проход рендера клипа (V2): Engine A (ffmpeg expr) или B (cv2 pipe).

    Аудио непрерывным потоком (нет подлагов); старт выровнен на границу кадра.
    engine='A' (default) — быстрый ffmpeg; engine='B' — точная per-frame линейная интерп.
    out_w/out_h (T5) — размеры выхода соотношения сторон (9:16 дефолт). Временная сетка
    (trim по кадрам) от аспекта НЕ зависит — Δ=0 инвариант цел.
    watermark=True (free-план) — прожечь «Made with Quip» в нижнем углу (аддитивный drawtext,
    кадровую сетку не трогает). Решается СЕРВЕРНО из плана владельца (см. run.render_one_clip).
    Возвращает латентность рендера (с). JobError при сбое.
    """
    if not regions:
        raise JobError(_STAGE, "render: empty regions")
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
            watermark=watermark,
            crf=crf,
            preset=preset,
        )
    else:  # Engine A (default)
        fc = build_smooth_filter(
            regions, src_w, src_h, fps, ass_name, out_w=out_w, out_h=out_h,
            fontsdir=_fontsdir_rel(data_dir), watermark=watermark,
        )  # fmt: skip
        cmd = build_single_pass_cmd(
            source_name, aligned_start, dur, fc, out_name, crf=crf, preset=preset
        )
        _run_ffmpeg(cmd, data_dir)

    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"render did not create {out_name}")
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
    watermark: bool = False,
) -> str:
    """filter_complex для мульти-интервального рендера (спека §6). PURE.

    Видео: split→per-seg trim(source-кадры)+reframe→_chain_video_segs→subtitles.
    Все переходы: жёсткий cut (concat). xfade удалён — границы = реальные склейки.
    Аудио: asplit→per-seg atrim(source-времена)→concat (бесшовно, до энкода).
    watermark=True (free) → drawtext «Made with Quip» поверх готового кадра (после субтитров).
    """
    if not segments:
        raise JobError(_STAGE, "build_timeline_filter: empty timeline")
    n = len(segments)
    wm = build_watermark_drawtext(out_w, out_h, fontsdir) if watermark else None
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
    final_in = "sv0" if n == 1 else "cv"
    if n > 1:
        parts.extend(_chain_video_segs(sv_labels, final_in))
    # Финальная видео-цепочка (субтитры+вотермарка) на [outv]; trailing ; перед аудио-concat.
    parts.append(_final_video_chain(final_in, ass_name, fontsdir, wm) + ";")

    sa = "".join(f"[sa{i}]" for i in range(n))
    parts.append(f"{sa}concat=n={n}:v=0:a=1[outa]")
    return "".join(parts)


def build_timeline_cmd(
    source: str, filter_complex: str, out_name: str, *, crf: int = 20, preset: str = "veryfast"
) -> list[str]:
    """ffmpeg для таймлайна: ПОЛНЫЙ вход (-i), маппим [outv]/[outa] из фильтра."""
    return [
        "ffmpeg", "-y", "-i", source,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        *_video_out_args(crf, preset),
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
    watermark: bool = False,
    crf: int = 20,
    preset: str = "veryfast",
) -> float:
    """Рендер mp4 из edit-state (спека §6). Возвращает латентность (с). JobError при сбое.

    1 интервал → делегирует в render_clip (проверенный путь, непрерывное аудио).
    >1 интервал → мульти-интервальный concat (Engine A; бесшовное аудио внутри filtergraph).
    out_w/out_h (T5) — размеры выхода соотношения сторон (9:16 дефолт).
    watermark=True (free) → прожечь «Made with Quip» (решается СЕРВЕРНО из плана владельца,
    см. tasks.render_edit_to_file) — обойти из редактора нельзя.
    """
    if not intervals:
        raise JobError(_STAGE, "render_timeline: no intervals")
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
            watermark=watermark,
            crf=crf,
            preset=preset,
        )

    segments = flatten_timeline(intervals, regions_per_interval, fps)
    fc = build_timeline_filter(
        segments, src_w, src_h, fps, ass_name, out_w=out_w, out_h=out_h,
        fontsdir=_fontsdir_rel(data_dir), watermark=watermark,
    )  # fmt: skip
    t0 = time.perf_counter()
    _run_ffmpeg(build_timeline_cmd(source_name, fc, out_name, crf=crf, preset=preset), data_dir)
    if not (data_dir / out_name).exists():
        raise JobError(_STAGE, f"render_timeline did not create {out_name}")
    return round(time.perf_counter() - t0, 2)
