"""CLI E2E: Stage 0→5 для одного источника → клипы + job.json + runs.jsonl.

Запуск:
  uv run python -m app.run <job_id> [<youtube_url>]
  - есть data/<job_id>/source.mp4 → import пропускается (кэш);
  - есть transcript.json/segments.json → стадии 1/2 берутся из кэша (не платим повторно).

Это склейка (план §4А F): вся логика — в pure-функциях стадий, здесь только оркестрация
+ запись статуса/телеметрии. Артефакты — в data/<job_id>/ (см. README).
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import billing, db, dispatch, storage
from app.config import get_settings
from app.errors import JobError
from app.models import ClipOut, Job, JobStatus, Metrics, Segment, Transcript, Word
from app.pipeline.stage0_import import SourceMeta, build_preview_proxy, import_youtube
from app.pipeline.stage1_transcribe import DEEPGRAM_NOVA_USD_PER_MIN, transcribe_to_file
from app.pipeline.stage2_select import select_segments
from app.pipeline.stage3_reframe import reframe_segment
from app.pipeline.stage4_captions import words_in_segment
from app.pipeline.stage5_render import clamp_output_dims, render_clip
from app.transcript_cache import audio_sha, cache_key, evict, get_cached, put_cached

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"  # services/worker/data

# Gemini flash (прибл.): input $0.30/M, output (вкл. thoughts) $2.50/M.
_GEMINI_IN_USD_PER_TOK = 0.30 / 1_000_000
_GEMINI_OUT_USD_PER_TOK = 2.50 / 1_000_000


def _snippet(words: list[Word], start: float, end: float, limit: int = 240) -> str:
    return " ".join(w.text for w in words_in_segment(words, start, end))[:limit]


def transcript_cache_model(settings: Any) -> str:
    """PURE. Имя модели для ключа кэша транскрипта, ЗАВИСЯЩЕЕ от провайдера.

    Раньше run.py клал в ключ всегда ``deepgram_model`` — для assemblyai это мусорный слот
    (транскрипт помечался deepgram-моделью, смена assemblyai-модели не инвалидировала кэш).
    Берём модель выбранного провайдера; для assemblyai читаем ``assemblyai_model`` через
    getattr (поле опционально в config — провайдер ещё не реализован, дефолт безопасный).
    """
    provider = settings.transcription_provider
    if provider == "assemblyai":
        return str(getattr(settings, "assemblyai_model", None) or "assemblyai-default")
    return str(settings.deepgram_model)


def _gemini_cost(usage: dict[str, int]) -> float:
    if not usage:
        return 0.0
    out_tok = usage.get("output", 0) + usage.get("thoughts", 0)
    return round(
        usage.get("prompt", 0) * _GEMINI_IN_USD_PER_TOK + out_tok * _GEMINI_OUT_USD_PER_TOK, 4
    )


def clip_spawn_args(
    job_id: str, segments: list[Segment], meta: SourceMeta, user_id: str | None
) -> list[tuple[str, int, dict[str, Any], dict[str, Any], str | None]]:
    """Аргументы фан-аута: кортеж на сегмент ``(job_id, clip_index, seg, meta, user_id)``. PURE.

    ``clip_index`` 1-based (совпадает с ``clip_id`` ``clip_{i:02d}``). seg/meta — ``model_dump``
    для переноса через границу Modal (cloudpickle-дружелюбные dict'ы). ``user_id`` — владелец
    джоба: на фан-аут-контейнере по нему резолвится план (вотермарка/разрешение) СЕРВЕРНО.
    """
    md = meta.model_dump()
    return [(job_id, i, seg.model_dump(), md, user_id) for i, seg in enumerate(segments, start=1)]


def build_clip_out(
    clip_id: str, seg: Segment, transcript_words: list[Word], video_url: str
) -> ClipOut:
    """Сегмент + слова транскрипта + готовый ``video_url`` → ClipOut (wire). PURE.

    Сниппет/слова считаются по окну сегмента — НЕ зависят от того, где рендерился клип
    (локально или на фан-аут-контейнере).
    """
    return ClipOut(
        id=clip_id,
        start=seg.start,
        end=seg.end,
        duration=round(seg.end - seg.start, 2),
        reason=seg.reason,
        type=seg.type,
        score=seg.score,
        video_url=video_url,
        thumbnail_url=None,
        transcript=_snippet(transcript_words, seg.start, seg.end),
        words=words_in_segment(transcript_words, seg.start, seg.end),
        hook=seg.hook,
        why_works=seg.why_works,
        hook_style=seg.hook_style,
    )


def resolve_clip_render_policy(user_id: str | None) -> billing.RenderPolicy:
    """Владелец джоба → политика рендера (вотермарка/разрешение), резолвится СЕРВЕРНО. PURE-ish.

    План берётся из ``profiles.plan`` по ``user_id`` (db.get_user_plan, dual-mode Postgres/
    SQLite) — НИКОГДА из клиентского флага → обойти с фронта нельзя. Нет ``user_id`` (локальный
    dev на диске/SQLite) → local_dev-политика (без вотермарки, полное разрешение). В облаке
    (Modal) у джоба ВСЕГДА есть ``user_id``, поэтому free-юзер ВСЕГДА получает вотермарку.
    """
    if not user_id:
        return billing.resolve_render_policy(None, local_dev=True)
    plan_id = db.get_user_plan(user_id)
    return billing.resolve_render_policy(plan_id, local_dev=False)


def render_one_clip(
    out: Path,
    source_name: str,
    clip_index: int,
    seg: Segment,
    meta: SourceMeta,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Stages 3–5 для ОДНОГО клипа: reframe → render → upload. Возвращает picklable result.

    Общее ядро (DRY): локальный цикл И Modal-фан-аут зовут ЭТУ функцию. Настройки берём из
    ``get_settings()`` ВНУТРИ (на фан-аут-контейнере свой процесс/env). ``source_name`` —
    относительно ``out``. НЕ трогает stage3/stage5 — только вызывает (инвариант кадровой
    сетки docs/REFRAME_FPS_GRID_INVARIANT.md цел).

    ``user_id`` (владелец джоба) → политика рендера (вотермарка + потолок разрешения)
    резолвится СЕРВЕРНО из плана (см. resolve_clip_render_policy). Вотермарка/cap прожигаются
    в render_clip — обойти с клиента невозможно (план не приходит с фронта).
    """
    s = get_settings()
    policy = resolve_clip_render_policy(user_id)
    clip_id = f"clip_{clip_index:02d}"
    t0 = time.perf_counter()
    regions, face_found = reframe_segment(
        out / source_name, meta.width, meta.height, seg.start, seg.end,
        clip_id=clip_id, out_dir=out, fps=meta.fps, mode_setting=s.reframe_mode,
        speaker_crop_scale=s.reframe_speaker_crop_scale,
        face_fps=s.reframe_face_fps, smoothing=s.reframe_smoothing,
        min_hold_sec=s.reframe_min_hold_sec,
        speak_threshold=s.reframe_speak_threshold,
        scene_threshold=s.reframe_scene_threshold,
        split_enabled=s.reframe_split_enabled,
        wide_speak_min=s.reframe_wide_speak_min,
    )  # fmt: skip
    reframe_lat = round(time.perf_counter() - t0, 2)
    # Базовый клип-аспект 9:16; free капится по меньшей стороне (1080→720). Кадровая сетка
    # (trim по SOURCE-кадрам) от out_w/out_h НЕ зависит → Δ=0 инвариант цел.
    out_w, out_h = clamp_output_dims(1080, 1920, policy.max_resolution)
    render_lat = render_clip(
        out, source_name, seg.start, f"clips/{clip_id}.mp4",
        regions=regions, src_w=meta.width, src_h=meta.height, fps=meta.fps,
        engine=s.reframe_engine, out_w=out_w, out_h=out_h, watermark=policy.watermark,
        crf=policy.video_crf, preset=policy.video_preset,
    )  # fmt: skip
    video_url = storage.upload_clip(out / "clips" / f"{clip_id}.mp4", out.name, clip_id)
    # Инкрементальная выдача: атомарно проставляем video_url ЭТОГО клипа в строку джоба сразу
    # после заливки → GET /jobs отдаёт его готовым, пока остальные ещё рендерятся (status
    # остаётся "rendering" до set_done). out.name == job_id (на фан-аут-контейнере и локально).
    db.set_clip_ready(out.name, clip_index, video_url)
    n_fit = sum(1 for r in regions if r.mode == "fit")
    print(
        f"  {clip_id}: {seg.start:.1f}-{seg.end:.1f} face={face_found} "
        f"regions={len(regions)} fit={n_fit} render={render_lat}s"
    )
    return {
        "clip_id": clip_id,
        "clip_index": clip_index,
        "video_url": video_url,
        "reframe_lat": reframe_lat,
        "render_lat": render_lat,
        "face_found": face_found,
    }


def _render_all_clips(
    job_id: str,
    out: Path,
    source_name: str,
    segments: list[Segment],
    meta: SourceMeta,
    user_id: str | None,
) -> list[dict[str, Any]]:
    """Stages 3–5 для ВСЕХ клипов. Modal → фан-аут (контейнер на клип, ПАРАЛЛЕЛЬНО);
    локально → последовательный цикл (идентично прежнему поведению). Результаты — в порядке
    сегментов (стабильный ``clip_index`` для ассемблинга ClipOut). ``user_id`` несётся в каждый
    клип-контейнер → план владельца (вотермарка/разрешение) резолвится там СЕРВЕРНО.
    """
    if dispatch.modal_spawn_enabled():
        return dispatch.map_render_clips(clip_spawn_args(job_id, segments, meta, user_id))
    return [
        render_one_clip(out, source_name, i, seg, meta, user_id)
        for i, seg in enumerate(segments, start=1)
    ]


def run_pipeline(
    job_id: str,
    source_url: str | None = None,
    on_status: Callable[[JobStatus, int], None] | None = None,
    *,
    max_clips: int | None = None,
    on_meta: Callable[[SourceMeta], None] | None = None,
    on_cancellable: Callable[[bool], None] | None = None,
    user_id: str | None = None,
) -> Job:
    """Прогнать весь конвейер для job_id. Возвращает Job (также пишет job.json/runs.jsonl).

    on_status(status, progress) (опц.) вызывается на границах стадий — для статуса в БД (J1).
    max_clips (опц.) — сколько клипов запросил юзер (UI-степпер); None → дефолт из настроек.
    on_meta(meta) (опц.) — вызывается СРАЗУ после импорта (известна реальная длина), ДО
    транскрипции. Поднимет JobError → джоб падает до оплаты Deepgram (гейт квоты по длине).
    on_cancellable(value) (опц.) — Stop-кнопка: вызывается с ``False`` ПРЯМО перед началом
    транскрипции (граница FREE→PAID: download/probe бесплатны, транскрипция — первый платный
    шаг). Джоб стартует cancellable=True (insert_job), True эмитить не нужно.
    user_id (опц.) — владелец джоба: несётся в per-clip рендер → план (вотермарка/разрешение)
    резолвится СЕРВЕРНО из profiles.plan (free прожигает вотермарку, обойти с клиента нельзя).
    """
    s = get_settings()  # fail-fast на отсутствии ключей; также берём reframe_mode
    out = DATA_ROOT / job_id
    out.mkdir(parents=True, exist_ok=True)
    stages: dict[str, float] = {}
    t_start = time.perf_counter()

    def emit(status: JobStatus, progress: int) -> None:
        if on_status is not None:
            on_status(status, progress)

    # ── Stage 0: Import (кэш по наличию source.mp4 + meta.json) ──
    emit(JobStatus.downloading, 10)
    t0 = time.perf_counter()
    meta_path = out / "meta.json"
    if (out / "source.mp4").exists() and meta_path.exists():
        meta = SourceMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
        print(f"[0] import: cached ({meta.duration:.0f}s {meta.width}x{meta.height})")
    elif source_url:
        meta = import_youtube(
            source_url, out, job_id=job_id,
            cookies_browser=s.ytdlp_cookies_browser,
            cookies_file=s.ytdlp_cookies_file,
        )  # fmt: skip
        print(f"[0] import: {meta.duration:.0f}s {meta.width}x{meta.height}")
    else:
        raise JobError("import", f"no data/{job_id}/source.mp4 and no URL provided")
    stages["download"] = round(time.perf_counter() - t0, 2)
    db.set_progress_detail(job_id, source_minutes=round(meta.duration / 60, 1))  # live narration

    # ── Гейт квоты по РЕАЛЬНОЙ длине (до оплаты транскрипции). Поднимет JobError → failed,
    #    БЕЗ списания (record_usage идёт только после set_done). ──
    if on_meta is not None:
        on_meta(meta)

    # ── FREE→PAID граница: транскрипция — первый платный шаг. Гасим cancellable ДО неё, чтобы
    #    Stop больше не предлагался (отмена платной стадии = частичный заряд, недопустимо). ──
    if on_cancellable is not None:
        on_cancellable(False)

    # ── Stage 1: Transcribe (уровень 1: job-local transcript.json; уровень 2: hash-кэш) ──
    emit(JobStatus.transcribing, 35)
    t0 = time.perf_counter()
    tr_path = out / "transcript.json"
    transcribe_cost = 0.0
    cache_dir = DATA_ROOT / "_cache" / "transcripts"

    if tr_path.exists():
        # Level 1: job-local cache (same job_id re-run)
        transcript = Transcript.model_validate_json(tr_path.read_text(encoding="utf-8"))
        print(f"[1] transcribe: cached/local ({len(transcript.words)} words)")
    else:
        wav_path = out / "source.wav"
        # Level 2: content-addressed cache (same audio, different job_id).
        # cloud (Postgres transcript_cache) durable между Modal-контейнерами; локально диск.
        cached_tr: Transcript | None = None
        sha: str | None = None
        ck: str | None = None
        tr_model = transcript_cache_model(s)
        if s.transcript_cache_enabled:
            sha = audio_sha(wav_path)
            ck = cache_key(sha, s.transcription_provider, tr_model)
            cloud_tr = db.get_cached_transcript(sha, s.transcription_provider, tr_model)
            cached_tr = (
                Transcript.model_validate(cloud_tr)
                if cloud_tr is not None
                else get_cached(cache_dir, ck)
            )

        if cached_tr is not None:
            transcript = cached_tr
            tr_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
            print(f"[1] transcribe: cached/hash ({len(transcript.words)} words, $0)")
        else:
            transcript = transcribe_to_file(wav_path, tr_path)
            transcribe_cost = round(transcript.duration / 60 * DEEPGRAM_NOVA_USD_PER_MIN, 4)
            print(f"[1] transcribe: {len(transcript.words)} words (${transcribe_cost})")
            if s.transcript_cache_enabled and ck is not None:
                put_cached(cache_dir, ck, transcript)
                evict(
                    cache_dir,
                    max_entries=s.transcript_cache_max_entries,
                    max_age_days=s.transcript_cache_max_age_days,
                )
            if s.transcript_cache_enabled and sha is not None:
                db.put_cached_transcript(
                    sha, s.transcription_provider, tr_model, transcript.model_dump()
                )
    stages["transcription"] = round(time.perf_counter() - t0, 2)
    db.set_progress_detail(job_id, transcript_words=len(transcript.words))  # live narration

    # ── Stage 2: Select (кэш по segments.json) ──
    emit(JobStatus.selecting, 60)
    t0 = time.perf_counter()
    seg_path = out / "segments.json"
    usage: dict[str, int] = {}
    if seg_path.exists():
        segments = [
            Segment.model_validate(x) for x in json.loads(seg_path.read_text(encoding="utf-8"))
        ]
        print(f"[2] select: cached ({len(segments)} segments)")
    else:
        segments = select_segments(transcript, meta.title, max_clips=max_clips, usage_sink=usage)
        seg_path.write_text(
            json.dumps([s.model_dump() for s in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[2] select: {len(segments)} segments")
    stages["llm_select"] = round(time.perf_counter() - t0, 2)
    select_cost = _gemini_cost(usage)
    db.set_progress_detail(job_id, moments_found=len(segments))  # live narration

    # ── Артефакты (meta/segments/transcript) в Postgres job_artifacts ДО фан-аута: preview_job
    #    (и любой будущий клип-контейнер) читает meta из облака. Локально — no-op. ──
    db.put_job_artifacts(
        job_id,
        meta.model_dump(),
        [seg.model_dump() for seg in segments],
        transcript.model_dump(),
    )

    # ── Инкрементальная выдача СРАЗУ после select (а не на границе рендера): персистим ВСЕ клипы
    #    (метаданные хук/why/score/интервал + ПУСТОЙ video_url) в строку джоба ТЕПЕРЬ → GET /jobs
    #    отдаёт богатые карточки на ~60%, за МИНУТЫ до рендера (фронт встаёт на грид по наличию
    #    клипов). status="selecting" (честно), progress=60. Каждый per-clip контейнер позже
    #    атомарно проставит свой video_url (db.set_clip_ready). clip_id 1-based (clip_{i:02d})
    #    совпадает с порядком segments → idx фан-аута выровнен. ──
    pending_clips: list[ClipOut] = [
        build_clip_out(f"clip_{i:02d}", seg, transcript.words, "")
        for i, seg in enumerate(segments, start=1)
    ]
    db.set_clips_pending(job_id, pending_clips, progress=60, status=JobStatus.selecting)

    # ── Источник в R2 ДО фан-аута: каждый клип-контейнер скачивает source из R2
    #    (artifacts.ensure_source — тот же проверенный путь, что у editor-render). Локально
    #    upload_source = no-op (исходник остаётся на диске). ──
    storage.upload_source(out / "source.mp4", job_id)

    # ── #3 Preview-прокси СНЯТ с критического пути: на Modal — отдельная функция preview_job,
    #    спавним СЕЙЧАС → она строит прокси ПАРАЛЛЕЛЬНО с клипами и не держит set_done. Редактор
    #    фолбэчит на source, пока прокси не готов (storage.preview_read_url). Локально строим
    #    inline ПОСЛЕ клипов (dev: один процесс, клипы уже отданы). ──
    if dispatch.modal_spawn_enabled():
        dispatch.spawn("preview_job", job_id)

    # ── VideoMap pre-warm: на Modal спавним СЕЙЧАС (отдельный контейнер, durable в Postgres) →
    #    карта обычно готова, когда юзер открыл результаты. Локально — inline ПОСЛЕ клипов (ниже),
    #    чтобы НЕ блокировать рендер. НЕ держит set_done и не влияет на нарезку. ──
    if dispatch.modal_spawn_enabled():
        dispatch.spawn("generate_video_map_job", job_id)

    # ── Рендер реально стартует здесь: статус → rendering, progress 80. Клипы уже персистнуты
    #    выше (после select); тут только апдейт статуса/прогресса (клипы не переписываем). ──
    emit(JobStatus.rendering, 80)

    # ── Stages 3–5: #1 фан-аут per-clip по контейнерам Modal (параллельно) ЛИБО последовательный
    #    цикл локально. Результаты приходят в порядке сегментов → стабильный ClipOut. ──
    results = _render_all_clips(job_id, out, "source.mp4", segments, meta, user_id)
    results.sort(key=lambda r: r["clip_index"])
    clips: list[ClipOut] = [
        build_clip_out(r["clip_id"], seg, transcript.words, r["video_url"])
        for seg, r in zip(segments, results, strict=True)
    ]
    stages["reframe"] = round(sum(r["reframe_lat"] for r in results), 2)
    stages["render"] = round(sum(r["render_lat"] for r in results), 2)

    # Локально (нет Modal) preview строим inline ПОСЛЕ клипов (cloud уже спавнил preview_job выше).
    if not dispatch.modal_spawn_enabled():
        t0 = time.perf_counter()
        build_preview_proxy(
            out / "source.mp4", out / "preview.mp4",
            height=min(s.preview_height, meta.height), crf=s.preview_crf,
        )  # fmt: skip
        stages["preview_proxy"] = round(time.perf_counter() - t0, 2)
        storage.upload_preview(out / "preview.mp4", job_id)
        # VideoMap pre-warm локально: inline ПОСЛЕ клипов (dev: один процесс, клипы уже отданы →
        # не блокирует рендер). На Modal уже заспавнено выше отдельным контейнером.
        from app.tasks import generate_video_map_job

        generate_video_map_job(job_id)

    # ── job.json (wire-контракт) ──
    total_sec = round(time.perf_counter() - t_start, 2)
    total_usd = round(transcribe_cost + select_cost, 4)
    job = Job(
        id=job_id,
        status=JobStatus.done,
        stage=JobStatus.done,
        progress=100,
        source_kind=meta.source,
        clips=clips,
        metrics=Metrics(cost_usd=total_usd, duration_sec=meta.duration, elapsed_sec=total_sec),
    )
    (out / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")

    # ── runs.jsonl (телеметрия экономики) ──
    run_line = {
        "run_id": job_id,
        "source_minutes": round(meta.duration / 60, 2),
        "stages": stages,
        "total_sec": total_sec,
        "total_usd": total_usd,
        "n_clips": len(clips),
        # При параллельном фан-ауте per-clip TTFC с координатора не имеет смысла (клипы
        # рендерятся одновременно на отдельных контейнерах) → None. В локальном цикле тоже None
        # (упрощение: телеметрия экономики живёт в stages/total_sec).
        "time_to_first_clip_sec": None,
    }
    with (DATA_ROOT / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_line, ensure_ascii=False) + "\n")

    print(f"\nDONE: {len(clips)} clips, total ${total_usd}, {total_sec}s -> data/{job_id}/")
    return job


def main() -> None:
    args = sys.argv[1:]
    job_id = args[0] if args else "sample01"
    source_url = args[1] if len(args) > 1 else None
    run_pipeline(job_id, source_url)


if __name__ == "__main__":
    main()
