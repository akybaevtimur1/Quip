"""ClipFlow — бенчмарк «самое выгодное железо под РЕАЛЬНУЮ нагрузку».

Зачем
=====
Спайк (clipflow_modal.py) случайно показал: тяжёлый reframe-путь CPU-bound (MediaPipe
крутился на XNNPACK-CPU даже на A10), а мы платили за A10 $1.10/ч. Это «из пушки по мухе».
Этот бенч доказывает ЦИФРАМИ, какое железо брать под каждую фазу:

  1) ТРАНСКРИПЦИЯ (доминанта СТОИМОСТИ: Deepgram ~$0.258/60-мин) — единственная фаза,
     которой реально нужен GPU. Гоняем faster-whisper large-v3 на T4 / L4 / A10 и меряем
     ФАКТИЧЕСКУЮ $/60-мин-видео на каждом → выбираем дешёвый достаточный.
  2) REFRAME-АНАЛИЗ (лица+склейки) — гоняем на CPU-инстансе (gpu=None) и сравниваем со
     спайком на A10. Если время такое же → GPU под reframe = выброшенные деньги.

Запуск (фаундер; modal setup уже сделан):
    deploy\\modal\\.venv-modal\\Scripts\\modal.exe run deploy\\modal\\bench.py

Первый прогон скачает large-v3 (~3 ГБ) в Modal Volume (один раз, кэшируется) и соберёт
CUDA-образ. Дальше — быстро. Весь бенч укладывается в центы от $30 бесплатных кредитов.
"""

from __future__ import annotations

import time
from pathlib import Path

import modal

# ─────────────────────────── пути локального репо ───────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_APP = _REPO_ROOT / "services" / "worker" / "app"
_SAMPLE_JOB = "job_17bb726bc1ec"
_SAMPLE_DIR = _REPO_ROOT / "services" / "worker" / "data" / _SAMPLE_JOB

# ─────────────── Modal per-second прайс (modal.com/pricing, сверено 2026-06-13) ───────────────
# ВЕРИФИЦИРОВАНО WebFetch'ем, не из памяти. Меняется — пересверить перед продом.
PRICE_PER_SEC: dict[str, float] = {
    "T4": 0.000164,  # $0.59/ч  — дешёвый, 16 ГБ VRAM, Turing fp16
    "L4": 0.000222,  # $0.80/ч  — value-король инференса, 24 ГБ, Ada
    "A10": 0.000306,  # $1.10/ч — быстрый, но дорогой для small-модели
}
CPU_CORE_SEC = 0.0000131  # $/физ.ядро/с ($0.047/ядро/ч)
MEM_GIB_SEC = 0.00000222  # $/ГиБ/с

# include_source=False — как в спайке: не авто-монтировать deploy/modal/ (там measure.py
# с `from app import` → шум). Функции serialized=True → cloudpickle по значению (всё в
# __main__ при `modal run`), modal.Volume/Secret внутри резолвятся графом объектов Modal.
app = modal.App("clipflow-bench", include_source=False)

# ───────────────────────── образ транскрипции (CUDA 12 + cuDNN 9) ─────────────────────────
# КЛЮЧЕВОЕ: берём nvidia/cuda:*-cudnn-runtime базу → libcudnn/libcublas уже в системных
# путях. Это убирает классическую боль faster-whisper «Could not load libcudnn_ops.so»
# (иначе пришлось бы pip-ставить nvidia-cudnn-cu12 и руками крутить LD_LIBRARY_PATH ДО
# старта процесса — ненадёжно). ctranslate2 (движок faster-whisper) требует CUDA12+cuDNN9.
_AUDIO_REMOTE = "/root/audio.wav"
fw_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.12"
    )
    .pip_install("faster-whisper>=1.1.0")
    .add_local_file(str(_SAMPLE_DIR / "source.wav"), _AUDIO_REMOTE, copy=True)
)
# Кэш модели large-v3 (~3 ГБ) — Volume, чтобы НЕ качать на каждый cold-start.
model_cache = modal.Volume.from_name("clipflow-whisper-cache", create_if_missing=True)
_CACHE_DIR = "/cache"


# ⚠️ КАЖДАЯ функция САМОДОСТАТОЧНА (тело инлайнено, без общего хелпера). Причина: при
# serialized=True Modal пиклит функцию cloudpickle'ом; ссылку на модульную ФУНКЦИЮ
# (_run_transcription) он сериализует ПО ИМЕНИ модуля → на удалёнке `import bench` падает
# (include_source=False срезал исходник). Спайк работал именно потому, что его функция была
# самодостаточной (ссылалась только на str-константы, не на хелперы). Возврат — СЫРЫЕ замеры;
# стоимость считаем ЛОКАЛЬНО в main() (там полный модуль с PRICE_PER_SEC). Дублирование тела
# осознанное: bench одноразовый, корректность важнее DRY.
@app.function(
    image=fw_image, gpu="T4", volumes={_CACHE_DIR: model_cache}, timeout=1800, serialized=True
)
def transcribe_t4() -> dict[str, object]:
    import time

    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    model = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=_CACHE_DIR)
    t_load = time.perf_counter() - t0
    t1 = time.perf_counter()
    segments, info = model.transcribe(_AUDIO_REMOTE, beam_size=5, word_timestamps=True, language=None)
    seg_list = list(segments)
    t_transcribe = time.perf_counter() - t1
    model_cache.commit()
    return {
        "gpu": "T4", "audio_sec": round(float(info.duration), 1), "lang": info.language,
        "n_segments": len(seg_list), "n_words": sum(len(s.words or []) for s in seg_list),
        "t_load_sec": round(t_load, 2), "t_transcribe_sec": round(t_transcribe, 2),
    }


@app.function(
    image=fw_image, gpu="L4", volumes={_CACHE_DIR: model_cache}, timeout=1800, serialized=True
)
def transcribe_l4() -> dict[str, object]:
    import time

    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    model = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=_CACHE_DIR)
    t_load = time.perf_counter() - t0
    t1 = time.perf_counter()
    segments, info = model.transcribe(_AUDIO_REMOTE, beam_size=5, word_timestamps=True, language=None)
    seg_list = list(segments)
    t_transcribe = time.perf_counter() - t1
    model_cache.commit()
    return {
        "gpu": "L4", "audio_sec": round(float(info.duration), 1), "lang": info.language,
        "n_segments": len(seg_list), "n_words": sum(len(s.words or []) for s in seg_list),
        "t_load_sec": round(t_load, 2), "t_transcribe_sec": round(t_transcribe, 2),
    }


@app.function(
    image=fw_image, gpu="A10", volumes={_CACHE_DIR: model_cache}, timeout=1800, serialized=True
)
def transcribe_a10() -> dict[str, object]:
    import time

    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    model = WhisperModel("large-v3", device="cuda", compute_type="float16", download_root=_CACHE_DIR)
    t_load = time.perf_counter() - t0
    t1 = time.perf_counter()
    segments, info = model.transcribe(_AUDIO_REMOTE, beam_size=5, word_timestamps=True, language=None)
    seg_list = list(segments)
    t_transcribe = time.perf_counter() - t1
    model_cache.commit()
    return {
        "gpu": "A10", "audio_sec": round(float(info.duration), 1), "lang": info.language,
        "n_segments": len(seg_list), "n_words": sum(len(s.words or []) for s in seg_list),
        "t_load_sec": round(t_load, 2), "t_transcribe_sec": round(t_transcribe, 2),
    }


# ─────────────────────── образ reframe на CPU (доказать: GPU не нужен) ───────────────────────
# Зеркало тяжёлого пути спайка, но torch — CPU-колесо (без cu124 index) и gpu=None.
# Анализ (analyze_source_range) = ffmpeg-кадры + MediaPipe FaceDetector + PySceneDetect + ASD.
_C_APP = "/root/app"
_C_SAMPLE = "/root/sample"
reframe_cpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "ffmpeg", "libgl1", "libglib2.0-0", "libegl1", "libgles2", "libglvnd0",
        "libsm6", "libxext6",
    )
    .pip_install("torch>=2.2", "torchaudio>=2.2")  # CPU-колёса (нет extra cu124 index)
    .pip_install(
        "mediapipe>=0.10.35", "scenedetect>=0.6.4", "numpy>=2.4.6", "scipy>=1.11",
        "pydantic>=2.13.4", "pydantic-settings>=2.14.1", "httpx>=0.28.1",
        "python_speech_features>=0.6",
    )
    .add_local_dir(str(_WORKER_APP), _C_APP, copy=True, ignore=["__pycache__", "*.pyc"])
    .add_local_dir(str(_SAMPLE_DIR), _C_SAMPLE, copy=True, ignore=["clips", "analysis"])
)

_REFRAME_CPU_CORES = 8.0  # запрашиваем 8 физ.ядер — reframe параллелится по кадрам


@app.function(image=reframe_cpu_image, cpu=_REFRAME_CPU_CORES, timeout=1800, serialized=True)
def reframe_analyze_cpu() -> dict[str, object]:
    """Тот же analyze→resolve, что в спайке, но на CPU-инстансе. Если время ≈ как на A10 (51с)
    → GPU под reframe не даёт ускорения = выброшенные деньги. Рендер НЕ гоняем (баг версии
    ffmpeg в образе — отдельный фикс; анализ от рендера не зависит)."""
    import json
    import sys
    import time

    if "/root" not in sys.path:
        sys.path.insert(0, "/root")

    from app.editor.reframe_cache import analyze_source_range, resolve_regions
    from app.models import CaptionStyle, CaptionTrack, ClipEdit, SourceInterval
    from app.pipeline.stage0_import import SourceMeta

    sample = Path(_C_SAMPLE)
    meta = SourceMeta.model_validate_json((sample / "meta.json").read_text(encoding="utf-8"))
    segments = json.loads((sample / "segments.json").read_text(encoding="utf-8"))
    seg_list = segments["segments"] if isinstance(segments, dict) else segments
    seg0 = seg_list[0]
    seg_start, seg_end = float(seg0["start"]), float(seg0["end"])
    clip_dur = round(seg_end - seg_start, 2)

    edit = ClipEdit(
        id="sample_clip",
        version=1,
        source_intervals=[SourceInterval(source_start=seg_start, source_end=seg_end)],
        captions=CaptionTrack(style=CaptionStyle()),
        reframe_overrides=[],
        aspect="9:16",
    )
    analysis_dir = Path("/tmp/analysis")

    t0 = time.perf_counter()
    raw = [
        analyze_source_range(
            sample / "source.mp4", iv.source_start, iv.source_end,
            cache_dir=analysis_dir, fps=25.0, cut_threshold=27.0,
        )
        for iv in edit.source_intervals
    ]
    t_analyze = round(time.perf_counter() - t0, 2)

    t1 = time.perf_counter()
    regions = resolve_regions(
        edit.source_intervals, raw, edit.reframe_overrides,
        src_w=meta.width, src_h=meta.height, smoothing=0.15, min_hold_sec=1.5,
        mode_setting="auto", wide_ratio=0.5, split_enabled=True,
    )
    t_resolve = round(time.perf_counter() - t1, 2)

    # Стоимость CPU = время × ядра × прайс/ядро/с (плюс память, но она копеечная).
    cpu_cost = (t_analyze + t_resolve) * _REFRAME_CPU_CORES * CPU_CORE_SEC
    return {
        "instance": f"CPU×{_REFRAME_CPU_CORES:g}",
        "clip_duration_sec": clip_dur,
        "n_face_samples": sum(len(r.faces) for r in raw),
        "n_cuts": sum(len(r.cuts) for r in raw),
        "n_regions": sum(len(r) for r in regions),
        "t_analyze_sec": t_analyze,
        "t_resolve_sec": t_resolve,
        "compute_sec": round(t_analyze + t_resolve, 2),
        "cost_this_clip": round(cpu_cost, 5),
    }


def _cost_per_60min(t_sec: float, gpu: str, audio_sec: float) -> float:
    """Стоимость за 60-мин видео = (время × прайс/с) экстраполировано на час аудио."""
    return (t_sec * PRICE_PER_SEC[gpu]) * (3600.0 / audio_sec) if audio_sec else 0.0


def _print_transcription_table(rows: list[dict[str, object]]) -> None:
    print("\n══════════════ ТРАНСКРИПЦИЯ: faster-whisper large-v3 по GPU ══════════════")
    print(f"  Аудио: {rows[0]['audio_sec']}с ({float(rows[0]['audio_sec'])/60:.1f} мин), "
          f"язык={rows[0]['lang']}, слов={rows[0]['n_words']}")
    print("  ─────────────────────────────────────────────────────────────────────────")
    print(f"  {'GPU':<6}{'$/ч':<9}{'transcribe':<12}{'realtime×':<11}"
          f"{'$/60мин(warm)':<16}{'$/60мин(cold)':<14}")
    best_gpu, best_cost = "", 1e9
    for r in rows:
        gpu = str(r["gpu"])
        audio_sec = float(r["audio_sec"])
        t_tr = float(r["t_transcribe_sec"])
        t_load = float(r["t_load_sec"])
        hourly = PRICE_PER_SEC[gpu] * 3600
        rt = round(audio_sec / t_tr, 2) if t_tr else 0.0
        warm = round(_cost_per_60min(t_tr, gpu, audio_sec), 4)
        cold = round(_cost_per_60min(t_load + t_tr, gpu, audio_sec), 4)
        if warm < best_cost:
            best_gpu, best_cost = gpu, warm
        print(f"  {gpu:<6}${hourly:<8.2f}{str(t_tr)+'с':<12}{str(rt)+'×':<11}"
              f"${str(warm):<15}${str(cold):<13}")
    print("  ─────────────────────────────────────────────────────────────────────────")
    print(f"  💸 Дешевле всего/60мин (warm): {best_gpu} = ${best_cost}")
    print("  📊 Сравнение: Deepgram = $0.258/60мин (наша текущая транскрипция)")


@app.local_entrypoint()
def main() -> None:
    """Прогнать все замеры на Modal и напечатать сравнительные таблицы + рекомендацию."""
    print("[bench] транскрипция large-v3: T4 → L4 → A10 (последовательно)…")
    rows = [transcribe_t4.remote(), transcribe_l4.remote(), transcribe_a10.remote()]
    _print_transcription_table(rows)

    print("\n[bench] reframe-анализ на CPU-инстансе (gpu=None)…")
    rf = reframe_analyze_cpu.remote()
    a10_analyze = 51.39  # из спайка clipflow_modal.py (A10, тот же сэмпл)
    a10_cost = a10_analyze * PRICE_PER_SEC["A10"]
    print("\n══════════════ REFRAME-АНАЛИЗ: CPU vs A10 (тот же сэмпл-клип) ══════════════")
    print(f"  {'Инстанс':<14}{'analyze':<11}{'лиц':<7}{'склеек':<9}{'$/клип':<10}")
    print(f"  {str(rf['instance']):<14}{str(rf['t_analyze_sec'])+'с':<11}"
          f"{str(rf['n_face_samples']):<7}{str(rf['n_cuts']):<9}${str(rf['cost_this_clip']):<9}")
    print(f"  {'A10 (спайк)':<14}{str(a10_analyze)+'с':<11}{'1385':<7}{'0':<9}${a10_cost:<.5f}")
    print("  ─────────────────────────────────────────────────────────────────────────")
    speedup = a10_analyze / float(rf["t_analyze_sec"]) if float(rf["t_analyze_sec"]) else 0.0
    print(f"  GPU-ускорение reframe: {speedup:.2f}×  "
          f"(≈1.0 → GPU бесполезен; CPU дешевле в {a10_cost/float(rf['cost_this_clip']):.1f}×)")
    print("\n[bench] готово. Рекомендация — в ответе агента.")
