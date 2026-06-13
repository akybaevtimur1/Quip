"""ClipFlow heavy worker on Modal (serverless GPU) — SPIKE scaffold.

Что это и зачем
===============
Тяжёлая часть пайплайна (reframe-анализ лиц/склеек + рендер 9:16) меряна ~6 мин
компьюта на видео на CPU. Цель спайка — гонять ЭТОТ кусок на Modal (serverless GPU,
auto-scale, scale-to-zero) и замерить РЕАЛЬНУЮ стоимость/время на GPU-инстансе.

Это ТОЛЬКО scaffold тяжёлого воркера. Лёгкие API/БД/фронт остаются на Vercel/Supabase
(НЕ здесь). Полная миграция storage/БД — отдельная сессия.

Что гоняем (реальный код пайплайна, без дублей логики)
------------------------------------------------------
Точно та же тройка функций, что и REST-путь редактора (`app/tasks.py::render_edit_to_file`):
    analyze_source_range  (app.editor.reframe_cache)  — ffmpeg + MediaPipe + PySceneDetect
    resolve_regions       (app.editor.reframe_cache)  — PURE планировщик cut-aligned
    render_timeline       (app.pipeline.stage5_render) — ffmpeg crop/scale/concat → mp4

Рендерим БЕЗ субтитров (with_subtitles=False-эквивалент): это сохраняет ВЕСЬ тяжёлый
компьют (детект лиц + scene-detect + ffmpeg-кодировка), но не тянет на Modal транскрипт/
ASS/шрифты. Замер репрезентативен для «сколько стоит/длится reframe+render одного клипа».

Команды (фаундер делает ОДИН раз `modal setup` — браузер-авторизация):
    pip install modal           # в любой venv (НЕ в pyproject воркера!)
    modal setup                 # один раз, открывает браузер для токена
    modal run deploy/modal/app.py            # дефолт-энтрипоинт: замер 1 сэмпл-клипа
    # либо явно:
    modal run deploy/modal/app.py::measure   # то же самое
См. также measure.py (тонкая обёртка над тем же энтрипоинтом) и README.md.

⚠️ Без `modal setup` (нет токена) — `modal run` упрётся в auth-ошибку ПОСЛЕ локальной
сборки графа (импорт app.py, проверка образа-депов проходят). Это ожидаемо.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import modal

# ─────────────────────────────── пути локального репо ───────────────────────────────
# app.py лежит в deploy/modal/ → корень репо = parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_APP = _REPO_ROOT / "services" / "worker" / "app"  # пакет `app` (импорт-имя)
_WORKER_FONTS = _REPO_ROOT / "services" / "worker" / "fonts"  # TTF для рендера

# Сэмпл-джоб с готовыми source.mp4 + meta.json + segments.json (реальный прогон,
# 1920×1080, 4 сегмента). Берём первый сегмент (~55с) как сэмпл-клип для замера.
_SAMPLE_JOB = "job_17bb726bc1ec"
_SAMPLE_JOB_DIR = _REPO_ROOT / "services" / "worker" / "data" / _SAMPLE_JOB

# Куда монтируем внутри контейнера (Linux-пути).
_C_APP = "/root/app"  # пакет приложения → на PYTHONPATH (/root)
_C_FONTS = "/root/fonts"
_C_SAMPLE = "/root/sample"  # сюда кладём source.mp4 / meta.json / segments.json


# ───────────────────────────────── GPU-образ ─────────────────────────────────
# Рантайм-зависимости задаём ЗДЕСЬ (Image.pip_install), НЕ в pyproject воркера.
# Зеркалят services/worker/pyproject.toml [project.dependencies], но без dev/линтеров,
# без yt-dlp/bgutil (скачивание — лёгкий путь, не на Modal) и без anthropic/google-genai/
# deepgram (LLM/транскрипция — лёгкий путь). Оставлены только депы тяжёлого reframe+render.
#
# torch: на Linux+GPU ставим CUDA-колесо (cu124). На CPU-воркере (Windows) это был CPU-whl —
# здесь смысл GPU, поэтому CUDA. Если функция запускается без gpu=, CUDA-torch всё равно
# импортируется и падает на .cuda() — но наш ASD-путь тут НЕ вызывается (см. примечание ниже),
# а reframe-analyze/render используют ffmpeg+MediaPipe, не torch. torch в образе — на будущее
# (active-speaker ASD-путь) и чтобы образ был «как в воркере».
_TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"

image = (
    modal.Image.debian_slim(python_version="3.12")
    # ffmpeg — декод AV1/H264 + crop/scale/concat-кодировка. libGL/glib — рантайм opencv.
    .apt_install(
        "ffmpeg",
        "libgl1",
        "libglib2.0-0",
        # MediaPipe FaceDetector (0.10.x) грузит GLES/EGL → libGLESv2.so.2 / libEGL.so.1.
        "libegl1",
        "libgles2",
        "libglvnd0",
        "libsm6",
        "libxext6",
    )
    # torch CUDA-колесо отдельным шагом (со своим index-url), чтобы не тащить CPU-вариант.
    .pip_install("torch>=2.2", "torchaudio>=2.2", extra_index_url=_TORCH_CUDA_INDEX)
    # Остальные рантайм-депы тяжёлого пути (зеркало pyproject, обрезано до reframe+render).
    .pip_install(
        "mediapipe>=0.10.35",  # FaceDetector (Tasks API) — тянет opencv-contrib + protobuf
        "scenedetect>=0.6.4",  # PySceneDetect ContentDetector (frame-accurate cuts)
        "numpy>=2.4.6",
        "scipy>=1.11",
        "pydantic>=2.13.4",
        "pydantic-settings>=2.14.1",
        "httpx>=0.28.1",  # _ensure_face_model скачивает blaze_face .tflite
        "python_speech_features>=0.6",  # ASD-фронтенд (на будущее, для speaker-пути)
    )
    # Примечание: тяжёлый путь (analyze→resolve→render) НЕ импортирует app.config →
    # API-ключи (Deepgram/Gemini) на Modal НЕ нужны. Подтверждено grep'ом по цепочке
    # импортов reframe_cache/stage5_render/stage3_reframe/models/stage0_import.
    # Монтируем НАШ пакет `app` + шрифты + сэмпл-джоб (copy=True → в слой образа, стабильный
    # cold-start; данные малы кроме source.mp4 ~десятки МБ — приемлемо для спайка).
    .add_local_dir(str(_WORKER_APP), _C_APP, copy=True, ignore=["__pycache__", "*.pyc"])
    .add_local_dir(str(_WORKER_FONTS), _C_FONTS, copy=True)
    .add_local_dir(str(_SAMPLE_JOB_DIR), _C_SAMPLE, copy=True, ignore=["clips", "analysis"])
)

# include_source=False — КРИТИЧНО: иначе Modal авто-монтирует директорию энтрипоинта и
# делает сам app.py импортируемым модулем `app`, что КОЛЛИЗИРУЕТ с нашим пакетом `app/`
# (смонтирован в /root/app). Отключаем авто-инклюд → пакет берётся ТОЛЬКО из add_local_dir.
app = modal.App("clipflow-heavy-worker", image=image, include_source=False)

# Modal per-second GPU-прайс (для оценки стоимости замера). Источник — публичный
# прайслист Modal (T4 ~$0.59/ч, A10G ~$1.10/ч на момент написания). ⚠️ свериться с
# https://modal.com/pricing перед продакшеном — цены меняются.
_GPU_HOURLY_USD = {
    "T4": 0.59,
    "A10G": 1.10,
    "L4": 0.80,
    "A100-40GB": 2.10,
}
_GPU = "A10G"  # дефолт для замера: достаточно VRAM, есть NVENC, дешевле A100.


def _setup_container_paths() -> None:
    """Положить /root на sys.path, чтобы импортировался пакет `app` (смонтирован в /root/app).

    include_source=False отключает авто-инклюд исходников Modal, поэтому путь к пакету
    добавляем явно. /root обычно уже на PYTHONPATH — insert идемпотентен (страховка).
    """
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")


@app.function(gpu=_GPU, timeout=1800, serialized=True)
def reframe_and_render_sample() -> dict[str, object]:
    """Прогнать тяжёлый путь (analyze→resolve→render) для одного сэмпл-сегмента на Modal-GPU.

    Возвращает метрики: длительность клипа, время каждой фазы, размер выходного mp4,
    тип GPU. Стоимость считает вызыватель (local_entrypoint) по wall-времени контейнера.

    serialized=True → Modal ПИКЛИТ функцию (cloudpickle), а не импортит её по имени
    модуля. Это убирает коллизию: имя деплой-модуля больше не важно, а наш пакет `app`
    (смонтирован в /root/app) импортируется ВНУТРИ функции в рантайме.
    """
    import sys

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")  # пакет `app` смонтирован в /root/app

    # Импорты ПОСЛЕ настройки path — это наш реальный код пайплайна (без дублей логики).
    from app.editor.reframe_cache import analyze_source_range, resolve_regions
    from app.models import CaptionStyle, CaptionTrack, ClipEdit, SourceInterval
    from app.pipeline.stage0_import import SourceMeta
    from app.pipeline.stage5_render import render_timeline

    sample = Path(_C_SAMPLE)
    out_dir = Path("/tmp/clipflow_job")  # рабочая папка рендера (эфемерная)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Копируем входы в рабочую папку (render_timeline пишет относительно data_dir).
    import shutil

    shutil.copy(sample / "source.mp4", out_dir / "source.mp4")
    shutil.copy(sample / "meta.json", out_dir / "meta.json")

    meta = SourceMeta.model_validate_json((out_dir / "meta.json").read_text(encoding="utf-8"))

    # Сэмпл-клип = первый сегмент из реального прогона (реальный диапазон source).
    segments = json.loads((sample / "segments.json").read_text(encoding="utf-8"))
    seg_list = segments["segments"] if isinstance(segments, dict) else segments
    seg0 = seg_list[0]
    seg_start, seg_end = float(seg0["start"]), float(seg0["end"])
    clip_dur = round(seg_end - seg_start, 2)

    # Минимальный edit-state: один интервал, без subtitle-overrides. captions — валидный
    # дефолт-трек (обязательное поле модели), но НЕ прожигается (render с ass_name=None).
    edit = ClipEdit(
        id="sample_clip",
        version=1,
        source_intervals=[SourceInterval(source_start=seg_start, source_end=seg_end)],
        captions=CaptionTrack(style=CaptionStyle()),  # не прожигаем (ass_name=None)
        reframe_overrides=[],
        aspect="9:16",
    )

    # Дефолты reframe-кнобов = как в config (не зовём get_settings, чтобы не тянуть ключи).
    face_fps = 25.0
    scene_threshold = 27.0
    smoothing = 0.15
    min_hold_sec = 1.5
    wide_ratio = 0.5

    analysis_dir = out_dir / "analysis"

    t0 = time.perf_counter()
    raw = [
        analyze_source_range(
            out_dir / "source.mp4",
            iv.source_start,
            iv.source_end,
            cache_dir=analysis_dir,
            fps=face_fps,
            cut_threshold=scene_threshold,
        )
        for iv in edit.source_intervals
    ]
    t_analyze = round(time.perf_counter() - t0, 2)

    t1 = time.perf_counter()
    regions = resolve_regions(
        edit.source_intervals,
        raw,
        edit.reframe_overrides,
        src_w=meta.width,
        src_h=meta.height,
        smoothing=smoothing,
        min_hold_sec=min_hold_sec,
        mode_setting="auto",
        wide_ratio=wide_ratio,
        split_enabled=True,
    )
    t_resolve = round(time.perf_counter() - t1, 2)

    out_rel = "clips/sample_clip.mp4"
    t2 = time.perf_counter()
    render_latency: float = 0.0
    render_ok = True
    render_err = ""
    try:
        render_latency = render_timeline(
            out_dir,
            "source.mp4",
            edit.source_intervals,
            regions,
            out_rel,
            ass_name=None,  # без субтитров
            src_w=meta.width,
            src_h=meta.height,
            fps=meta.fps,
            engine="A",
        )
    except Exception as e:  # noqa: BLE001 — рендер-портируемость на debian-ffmpeg меряем отдельно
        render_ok = False
        render_err = str(e)[-300:]
    t_render = round(time.perf_counter() - t2, 2)

    out_path = out_dir / out_rel
    out_size = out_path.stat().st_size if out_path.exists() else 0

    # Диагностика GPU: видит ли torch CUDA внутри контейнера (для дальнейшего ASD-пути).
    cuda_ok = False
    cuda_name = "n/a"
    try:
        import torch  # noqa: PLC0415

        cuda_ok = bool(torch.cuda.is_available())
        if cuda_ok:
            cuda_name = torch.cuda.get_device_name(0)
    except Exception as e:  # noqa: BLE001 — диагностика, не критично для замера
        cuda_name = f"torch err: {e}"

    return {
        "gpu": _GPU,
        "cuda_available": cuda_ok,
        "cuda_device": cuda_name,
        "clip_duration_sec": clip_dur,
        "n_intervals": len(edit.source_intervals),
        "n_regions": sum(len(r) for r in regions),
        "n_cuts": sum(len(r.cuts) for r in raw),
        "n_face_samples": sum(len(r.faces) for r in raw),
        "render_ok": render_ok,
        "render_err": render_err,
        "t_analyze_sec": t_analyze,
        "t_resolve_sec": t_resolve,
        "t_render_sec": t_render,
        "render_latency_reported": render_latency,
        "out_mp4_bytes": out_size,
        "compute_sec": round(t_analyze + t_resolve + t_render, 2),
    }


def _summarize(metrics: dict[str, object], wall_sec: float) -> str:
    """Человекочитаемый отчёт замера + оценка стоимости на Modal (по wall-времени GPU)."""
    gpu = str(metrics.get("gpu", _GPU))
    hourly = _GPU_HOURLY_USD.get(gpu, _GPU_HOURLY_USD[_GPU])
    # Стоимость считаем по wall-времени контейнера (Modal биллит занятость инстанса,
    # включая cold-start импорт-фазу первого вызова). compute_sec — чистый пайплайн.
    cost_wall = wall_sec / 3600.0 * hourly
    compute_sec = float(metrics.get("compute_sec", 0.0))
    cost_compute = compute_sec / 3600.0 * hourly
    clip_dur = float(metrics.get("clip_duration_sec", 0.0))
    ratio = round(compute_sec / clip_dur, 2) if clip_dur else 0.0

    lines = [
        "",
        "═══════════════ ClipFlow на Modal — замер тяжёлого воркера ═══════════════",
        f"  GPU:                {gpu}  (${hourly:.2f}/ч)",
        f"  CUDA доступна:      {metrics.get('cuda_available')}  ({metrics.get('cuda_device')})",
        f"  Сэмпл-клип:         {clip_dur:.1f}с видео, {metrics.get('n_intervals')} интервал(ов)",
        f"  Анализ (лица+cuts): {metrics.get('t_analyze_sec')}с  "
        f"({metrics.get('n_face_samples')} сэмплов лиц, {metrics.get('n_cuts')} склеек)",
        f"  Планировщик (PURE): {metrics.get('t_resolve_sec')}с  "
        f"({metrics.get('n_regions')} регионов)",
        f"  Рендер (ffmpeg):    {metrics.get('t_render_sec')}с  "
        f"→ {int(metrics.get('out_mp4_bytes', 0)) / 1e6:.1f} МБ mp4",
        "  ─────────────────────────────────────────────────────────────────────",
        f"  Чистый компьют:     {compute_sec:.1f}с  ({ratio}× длительности клипа)",
        f"  Wall (с cold-start):{wall_sec:.1f}с",
        f"  Стоимость/клип:     ${cost_wall:.4f} по wall  |  ${cost_compute:.4f} по компьюту",
        "═════════════════════════════════════════════════════════════════════════",
        "  ⚠️ wall включает cold-start первого вызова (импорт torch/mediapipe ~десятки с).",
        "     На прогретом инстансе стоимость ≈ по-компьюту. Цены — сверить с modal.com/pricing.",
        "",
    ]
    return "\n".join(lines)


@app.local_entrypoint()
def measure() -> None:
    """Дефолт-энтрипоинт: 1 удалённый прогон на Modal-GPU + печать замера/стоимости.

    Запуск:  modal run deploy/modal/app.py
       либо:  modal run deploy/modal/app.py::measure
    """
    print(f"[clipflow-modal] вызываю reframe_and_render_sample() на {_GPU}…")
    t0 = time.perf_counter()
    metrics = reframe_and_render_sample.remote()
    wall = round(time.perf_counter() - t0, 2)
    print(_summarize(metrics, wall))
    print("[clipflow-modal] сырые метрики:")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
