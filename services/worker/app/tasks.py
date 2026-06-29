"""Оркестрация run_pipeline в фоне + статус в SQLite (план §4А F: склейка).

Единственное место склейки для REST-пути: ловит JobError/любое исключение → статус failed
(правило №8), на успехе — set_done. Логика стадий не дублируется (живёт в run_pipeline).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from app import billing, db
from app.errors import JobError
from app.models import Job, JobStatus
from app.pipeline.stage0_import import SourceMeta
from app.run import run_pipeline

_log = logging.getLogger("clipflow.billing")


def _billing_on() -> bool:
    return os.environ.get("BILLING_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _quota_gate(user_id: str | None, holder: dict[str, Any]) -> Callable[[SourceMeta], None] | None:
    """on_meta-хук для run_pipeline: проверяет квоту по РЕАЛЬНОЙ длине (после probe, до
    транскрипции) и роняет JobError, если не хватает минут. Read-only — НИЧЕГО не списывает
    (списание = _meter только после готовых клипов). None, если биллинг/юзер не активны.

    Авторизованное ``QuotaDecision`` (split месячный/PAYG) кладётся в ``holder["decision"]`` →
    ``_meter`` применяет ИМЕННО его (нет дрейфа гейт↔метеринг: длина источника одна и та же —
    meta.duration == metrics.duration_sec, см. run.py).
    """
    if not user_id or not _billing_on():
        return None

    def check(meta: SourceMeta) -> None:
        minutes = meta.duration / 60.0
        profile = db.get_profile(user_id)
        used = db.get_monthly_usage(user_id, billing.current_month())
        payg_minutes = int(profile["payg_credits"]) * billing.MINUTES_PER_VIDEO
        decision = billing.check_quota(
            profile["plan"], float(used["minutes"]), payg_minutes, minutes
        )
        if not decision.allowed:
            raise JobError("limit", decision.reason or "Quota exceeded")
        holder["decision"] = decision  # авторизованный split → метеринг

    return check


def _meter(user_id: str | None, job_id: str, job: Job, holder: dict[str, Any]) -> None:
    """Списать расход обработанного видео для авторизованного юзера. Best-effort ПОСЛЕ
    set_done: не роняет готовый клип, но и не глотается молча — провал логируется (правило №8).

    Применяет split из ``holder["decision"]`` (авторизованного гейтом): в МЕСЯЧНЫЙ счётчик
    идёт ТОЛЬКО ``from_monthly_min`` (PAYG-минуты НЕ дублируются в месячный лимит — фикс
    двойного учёта), а PAYG-кредиты списываются по ``payg_credits_for_split``. Без decision
    (биллинг выключен → гейт не запускался) — старое поведение: полные минуты в месячный счёт,
    PAYG не трогаем (баланс не консультировался).
    """
    if not user_id:
        return
    # Денежный инвариант (фаундер): за результат с НАШЕЙ ошибкой минуты не списываем НИ ПРИ КАКОМ
    # раскладе. Структурно это уже даёт порядок try(run_pipeline→set_done→_meter)/except(set_failed)
    # — на исключении любой стадии _meter недостижим. Этот гард — второй слой (defense-in-depth): не
    # заряжаем, если НЕ отдали ни одного клипа (0 клипов = юзер получил пусто; и страховка от
    # вырожденного «успеха» при будущем рефакторе). Успешный прогон всегда имеет ≥1 клип.
    if not job.clips:
        _log.info("meter skipped: 0 clips delivered (no charge): job=%s user=%s", job_id, user_id)
        return
    full_minutes = (job.metrics.duration_sec / 60.0) if job.metrics else 0.0
    decision = holder.get("decision")
    if decision is not None:
        monthly_minutes = float(decision.from_monthly_min)
        payg_credits = billing.payg_credits_for_split(decision)
    else:
        monthly_minutes = full_minutes
        payg_credits = 0
    try:
        recorded = db.record_usage(user_id, job_id, monthly_minutes, billing.current_month())
        # recorded=False → этот job_id УЖЕ учтён (ретрай/повторный прогон одного джоба) →
        # PAYG второй раз НЕ списываем (идемпотентность по job_id: ноль двойного заряда).
        if recorded and payg_credits > 0:
            db.deduct_payg(user_id, payg_credits)
    except Exception:
        _log.exception("usage record failed: job=%s user=%s", job_id, user_id)


def render_edit_to_file(job_id: str, clip_id: str, *, with_subtitles: bool, out_rel: str) -> None:
    """Собрать mp4 из текущего ClipEdit в out_rel. Общее ядро рендера (правило «без дублей»).

    with_subtitles=True → прожигаем ASS выбранного стиля (обычный клип). False → чистый mp4
    без субтитров (экспорт-свобода: пере-монтаж в любом редакторе). Raises JobError при сбое;
    статус ставит вызыватель (фон-таск → clip_edits; sync-эндпоинт → HTTP).
    """
    from app import artifacts
    from app.config import get_settings
    from app.editor import store
    from app.editor.captions_v2 import write_caption_ass
    from app.editor.reframe_cache import resolve_regions_accurate
    from app.editor.timemap import ClipTimeMap
    from app.pipeline.stage5_render import aspect_to_dims, clamp_output_dims, render_timeline
    from app.run import resolve_clip_render_policy

    s = get_settings()
    edit = store.load_edit(job_id, clip_id)
    if edit is None:
        raise JobError("render", f"no edit for {clip_id}")
    # disk-first / cloud: на web-контейнере source.mp4 скачивается из R2, артефакты — из Postgres.
    out = artifacts.ensure_source(job_id).parent
    meta = artifacts.load_meta(job_id)
    # Серверная политика рендера от владельца джоба (jobs.user_id → profiles.plan): free
    # прожигает вотермарку + капится 720p. Тот же путь, что batch-рендер — обойти из редактора
    # (download «чистый»/«с субтитрами», pere-render) НЕЛЬЗЯ (план не приходит с клиента).
    job_row = db.get_job_row(job_id)
    owner_id = job_row.get("user_id") if job_row else None
    policy = resolve_clip_render_policy(owner_id)
    out_w, out_h = aspect_to_dims(edit.aspect)  # T5: размеры выхода соотношения сторон
    out_w, out_h = clamp_output_dims(out_w, out_h, policy.max_resolution)

    ass_rel: str | None = None
    if with_subtitles:
        # Субтитры выбранного пресета (edit.captions.style/highlight) → ASS-прожиг.
        # compile_ass сам пропускает нижние реплики при captions.burn=False (T4 #8), но
        # СОХРАНЯЕТ хук → ASS пишем всегда (пустой no-op безвреден).
        # PlayRes ASS = размеры выхода (out_w×out_h) → libass не растягивает субтитры (T5).
        words = store.load_transcript_words(job_id)
        cmap = ClipTimeMap(edit.source_intervals)
        ass_rel = f"clips/{clip_id}.ass"
        ass_path = out / ass_rel
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        write_caption_ass(edit.captions, words, cmap, ass_path, play_w=out_w, play_h=out_h)

    # ЕДИНЫЙ frame-accurate reframe (как batch): PySceneDetect + ASD + held-crop.
    # Убирает рывки/флеши старого editor-пути (cuts в секундах + 5fps без ASD на ≠25fps).
    regions = resolve_regions_accurate(
        out / "source.mp4",
        edit.source_intervals,
        edit.reframe_overrides,
        src_w=meta.width,
        src_h=meta.height,
        fps=meta.fps,
        clip_id=clip_id,
        out_dir=out,
        cache_dir=out / "analysis",
        mode_setting=s.reframe_mode,
        speaker_crop_scale=s.reframe_speaker_crop_scale,
        face_fps=s.reframe_face_fps,
        smoothing=s.reframe_smoothing,
        min_hold_sec=s.reframe_min_hold_sec,
        speak_threshold=s.reframe_speak_threshold,
        scene_threshold=s.reframe_scene_threshold,
        min_scene_sec=s.reframe_min_scene_sec,
        split_enabled=s.reframe_split_enabled,
        wide_speak_min=s.reframe_wide_speak_min,
    )
    render_timeline(
        out,
        "source.mp4",
        edit.source_intervals,
        regions,
        out_rel,
        ass_name=ass_rel,
        src_w=meta.width,
        src_h=meta.height,
        fps=meta.fps,
        engine=s.reframe_engine,
        out_w=out_w,
        out_h=out_h,
        watermark=policy.watermark,
        crf=policy.video_crf,
        preset=policy.video_preset,
    )


def render_clip_edit_job(job_id: str, clip_id: str) -> None:
    """Собрать прожжённый mp4 из ClipEdit (фон, С субтитрами). Статус → clip_edits (правило №8).

    D1: пишем в ОТДЕЛЬНЫЙ артефакт ``clips/<id>_captioned.mp4`` (R2-ключ ``_captioned``), НИКОГДА
    не перетирая чистый reframe-клип ``clips/<id>.mp4`` — он остаётся базой WYSIWYG, поверх
    которой грид и редактор рисуют libass. Так превью/грид/редактор/экспорт не расходятся и
    субтитры не двоятся (раньше overwrite → грид рисовал поверх прожжённых = двойные субтитры).
    """
    from app import artifacts, storage

    out_rel = f"clips/{clip_id}_captioned.mp4"
    try:
        render_edit_to_file(job_id, clip_id, with_subtitles=True, out_rel=out_rel)
        # local → "clips/<id>_captioned.mp4" (раздаётся на /media); r2 → публичный/presigned URL.
        url = storage.upload_clip(
            artifacts.job_dir(job_id) / out_rel, job_id, clip_id, variant="captioned"
        )
        db.set_render_status(job_id, clip_id, "done", url, None)
    except JobError as e:
        db.set_render_status(job_id, clip_id, "failed", None, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed
        db.set_render_status(job_id, clip_id, "failed", None, f"unexpected: {e}")


def agent_edit_job(run_id: str) -> None:
    """W3: фон-точка агент-чата (Modal-spawn / local-bg). Статус и события пишет run_clip_agent
    (правило №8). Биллинг НЕ трогаем — агент-путь минут не списывает."""
    from app.agent.clip_agent import run_clip_agent

    run_clip_agent(run_id)


def generate_chapters_job(job_id: str) -> None:
    """Сгенерировать AI-карту видео (главы) в фоне → data/<job>/chapters.json.

    Успех → status=done+chapters; падение → status=failed+error (правило №8,
    фронт показывает причину). Кэш-файл уже содержит pending (пишет endpoint).
    """
    from app import artifacts
    from app.editor import chapters as chmod
    from app.models import ChaptersData

    out = artifacts.job_dir(job_id)
    out.mkdir(parents=True, exist_ok=True)
    try:
        transcript = artifacts.load_transcript(job_id)
        chapters = chmod.generate_chapters(
            transcript.words, transcript.duration, transcript.language
        )
        if not chapters:
            # Пустой результат Gemini → НЕ тихий done с пустой картой (правило №8): фронт
            # показал бы «нет глав» без объяснения. Поднимаем явный failed с причиной, чтобы
            # сработал retry-путь (GET /chapters?retry=true) и юзер видел, что произошло.
            chmod.save_chapters(
                out,
                ChaptersData(
                    status="failed",
                    error="AI map is empty (the model returned no chapters). Please try again.",
                ),
            )
            return
        chmod.save_chapters(out, ChaptersData(status="done", chapters=chapters))
    except JobError as e:
        chmod.save_chapters(out, ChaptersData(status="failed", error=str(e)))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        chmod.save_chapters(out, ChaptersData(status="failed", error=f"unexpected: {e}"))


def generate_video_map_job(job_id: str) -> None:
    """Сгенерировать нарративную VideoMap (главы+моменты) → диск + Postgres (dual-mode).

    КРИТИЧНО: запускается в ОТДЕЛЬНОМ Modal-контейнере (dispatch.spawn), результат отдаёт
    web-контейнер /video-map → save_video_map пишет durable в Postgres job_artifacts (см.
    editor/video_map.py). Успех → status=done; пусто/падение → status=failed+error (правило
    №8 — фронт видит причину, retry-путь GET /video-map?retry=true перезапускает).
    """
    from app import artifacts
    from app.editor import video_map as vmmod
    from app.models import VideoMap

    try:
        transcript = artifacts.load_transcript(job_id)
        segments = artifacts.load_segments(job_id)
        result = vmmod.generate_video_map(
            transcript.words, transcript.duration, transcript.language, segments
        )
        if not result.chapters:
            # Пустая карта → НЕ тихий done (правило №8): явный failed с причиной → видно на фронте.
            vmmod.save_video_map(
                job_id,
                VideoMap(
                    status="failed",
                    error="AI map is empty (the model returned no chapters). Please try again.",
                ),
            )
            return
        vmmod.save_video_map(job_id, result)
    except JobError as e:
        vmmod.save_video_map(job_id, VideoMap(status="failed", error=str(e)))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        vmmod.save_video_map(job_id, VideoMap(status="failed", error=f"unexpected: {e}"))


def run_pipeline_job(
    job_id: str,
    source_type: str,
    source_ref: str,
    max_clips: int | None = None,
    user_id: str | None = None,
    language: str | None = None,
) -> None:
    def on_status(status: JobStatus, progress: int) -> None:
        db.update_status(job_id, status.value, progress)

    def on_cancellable(v: bool) -> None:
        db.set_cancellable(job_id, v)

    # Холдер несёт авторизованный гейтом QuotaDecision (split) от on_meta до метеринга —
    # один источник истины списания (нет дрейфа гейт↔метеринг).
    quota: dict[str, Any] = {}
    try:
        job = run_pipeline(
            job_id,
            source_url=source_ref,
            on_status=on_status,
            max_clips=max_clips,
            on_meta=_quota_gate(user_id, quota),
            on_cancellable=on_cancellable,
            user_id=user_id,
            language=language,
        )
        db.set_done(job_id, job)
        _meter(user_id, job_id, job, quota)
    except JobError as e:
        db.set_failed(job_id, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        db.set_failed(job_id, f"unexpected: {e}")


def run_upload_job(
    job_id: str,
    upload_path: str,
    title: str,
    max_clips: int | None = None,
    user_id: str | None = None,
    language: str | None = None,
) -> None:
    """Фон-таск для загруженного файла: импорт файла → тот же run_pipeline (без скачивания).

    import_upload готовит source.mp4/wav/meta.json → run_pipeline(source_url=None) видит их
    как кэш Stage 0 и сразу идёт на транскрипцию. Статус в БД (правило №8 — падение → failed).
    """
    from pathlib import Path

    from app.pipeline.stage0_import import import_upload
    from app.run import DATA_ROOT

    def on_status(status: JobStatus, progress: int) -> None:
        db.update_status(job_id, status.value, progress)

    def on_cancellable(v: bool) -> None:
        db.set_cancellable(job_id, v)

    quota: dict[str, Any] = {}
    try:
        db.update_status(job_id, JobStatus.downloading.value, 8)
        import_upload(Path(upload_path), DATA_ROOT / job_id, job_id=job_id, title=title)
        job = run_pipeline(
            job_id,
            source_url=None,
            on_status=on_status,
            max_clips=max_clips,
            on_meta=_quota_gate(user_id, quota),
            on_cancellable=on_cancellable,
            user_id=user_id,
            language=language,
        )
        db.set_done(job_id, job)
        _meter(user_id, job_id, job, quota)
    except JobError as e:
        db.set_failed(job_id, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        db.set_failed(job_id, f"unexpected: {e}")
