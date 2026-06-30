"""Оркестрация run_pipeline в фоне + статус в SQLite (план §4А F: склейка).

Единственное место склейки для REST-пути: ловит JobError/любое исключение → статус failed
(правило №8), на успехе — set_done. Логика стадий не дублируется (живёт в run_pipeline).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app import billing, db
from app.errors import JobError
from app.models import Job, JobStatus
from app.pipeline.stage0_import import SourceMeta
from app.run import run_pipeline

_log = logging.getLogger("clipflow.billing")
_rlog = logging.getLogger("clipflow.render")


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


def _segment_bounds(job_id: str, clip_id: str) -> tuple[float, float] | None:
    """(start, end) сегмента клипа из артефактов (диск/cloud). None если индекс вне диапазона/нет.

    Дефолтный интервал клипа сидится из ЭТОГО сегмента (default_clip_edit). Совпадение текущего
    edit-интервала с этими границами = клип не тримили/не сдвигали → baked ``clips/<id>.mp4`` —
    валидная геометрия для composite-ASS fast-path (см. fast_export.edit_matches_baked).
    """
    from app import artifacts

    try:
        segs = artifacts.load_segments(job_id)
        idx = int(clip_id.split("_")[1]) - 1
    except (JobError, IndexError, ValueError):
        return None
    if idx < 0 or idx >= len(segs):
        return None
    seg = segs[idx]
    return (seg.start, seg.end)


def _ensure_baked_clip(job_id: str, clip_id: str, out: Path) -> Path | None:
    """Путь к чистому baked-клипу ``clips/<id>.mp4``: с диска (batch/local) или скачать из R2 (web).

    None → клипа нет нигде → composite-fast-path невозможен (НЕ тихо: причина логируется, вызыватель
    идёт полным путём). Скачивание клипа (~10–20 МБ) на порядок дешевле полного source + CV.
    """
    from app.cloud_state import cloud_enabled

    local = out / "clips" / f"{clip_id}.mp4"
    if local.exists():
        return local
    if not cloud_enabled():
        return None
    from app import storage

    try:
        local.parent.mkdir(parents=True, exist_ok=True)
        storage.download_clip(job_id, clip_id, local)
        return local
    except JobError as e:
        _rlog.info("composite fast-path: baked clip unavailable (%s) → full render: %s", e, clip_id)
        return None


def _composite_captions_onto_baked(
    job_id: str,
    clip_id: str,
    edit: Any,
    out: Path,
    baked: Path,
    *,
    out_w: int,
    out_h: int,
    out_rel: str,
    crf: int,
    preset: str,
) -> None:
    """FAST PATH: прожечь ASS текущего edit поверх baked-клипа ОДНИМ коротким энкодом.

    Пропускает ensure_source(полный source), resolve_regions_accurate(CV) и reframe-фильтрграф —
    baked уже 1080×1920 с вотермаркой и нужным кропом (геометрия/вотермарка сохраняются). ASS жжём
    тем же compile_ass/fontsdir, что и полный путь → WYSIWYG (как libass-превью над тем же клипом).
    """
    from app import fast_export
    from app.editor import store
    from app.editor.captions_v2 import write_caption_ass
    from app.editor.timemap import ClipTimeMap
    from app.pipeline.stage5_render import _fontsdir_rel, _run_ffmpeg, _subtitles_filter

    # PlayRes ASS = размеры выхода (out_w×out_h) → libass не растягивает субтитры (T5).
    words = store.load_transcript_words(job_id)
    cmap = ClipTimeMap(edit.source_intervals)
    ass_rel = f"clips/{clip_id}.ass"
    ass_path = out / ass_rel
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    write_caption_ass(edit.captions, words, cmap, ass_path, play_w=out_w, play_h=out_h)

    ass_filter = _subtitles_filter(ass_rel, _fontsdir_rel(out))
    baked_rel = baked.relative_to(out).as_posix()
    cmd = fast_export.build_composite_ass_cmd(
        baked_rel, ass_filter, out_rel, crf=crf, preset=preset
    )
    _rlog.info("composite-ASS fast path: job=%s clip=%s baked=%s", job_id, clip_id, baked_rel)
    _run_ffmpeg(cmd, out)  # JobError при сбое (правило №8)
    if not (out / out_rel).exists():
        raise JobError("render", f"composite-ASS produced no {out_rel}")


def render_edit_to_file(job_id: str, clip_id: str, *, with_subtitles: bool, out_rel: str) -> None:
    """Собрать mp4 из текущего ClipEdit в out_rel. Общее ядро рендера (правило «без дублей»).

    with_subtitles=True → прожигаем ASS выбранного стиля (обычный клип). False → чистый mp4
    без субтитров (экспорт-свобода: пере-монтаж в любом редакторе). Raises JobError при сбое;
    статус ставит вызыватель (фон-таск → clip_edits; sync-эндпоинт → HTTP).

    FAST PATH (with_subtitles, геометрия нетронута): если правка caption/hook-only поверх дефолтного
    интервала (без кропа/аспекта/трима) И baked ``clips/<id>.mp4`` доступен — прожигаем субтитры
    поверх него (composite-ASS), пропуская полный source-download + CV + reframe (минуты → секунды).
    Гейт явный, любой мискматч логируется и уходит в полный путь (правило №8 — без тихого фолбэка).
    """
    from app import artifacts, fast_export
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
    # disk-first / cloud: артефакты — из Postgres; source.mp4 НЕ качаем заранее (fast-path его не
    # трогает; полный путь скачает через ensure_source ниже). out = рабочая папка джоба.
    out = artifacts.job_dir(job_id)
    meta = artifacts.load_meta(job_id)
    # Серверная политика рендера от владельца джоба (jobs.user_id → profiles.plan): free
    # прожигает вотермарку + капится 720p. Тот же путь, что batch-рендер — обойти из редактора
    # (download «чистый»/«с субтитрами», pere-render) НЕЛЬЗЯ (план не приходит с клиента).
    job_row = db.get_job_row(job_id)
    owner_id = job_row.get("user_id") if job_row else None
    policy = resolve_clip_render_policy(owner_id)
    out_w, out_h = aspect_to_dims(edit.aspect)  # T5: размеры выхода соотношения сторон
    out_w, out_h = clamp_output_dims(out_w, out_h, policy.max_resolution)

    # ── FAST PATH: composite-ASS поверх baked-клипа (caption/hook-only, геометрия нетронута) ──
    if with_subtitles:
        seg = _segment_bounds(job_id, clip_id)
        if seg is not None and fast_export.edit_matches_baked(
            edit, seg_start=seg[0], seg_end=seg[1]
        ):
            baked = _ensure_baked_clip(job_id, clip_id, out)
            if baked is not None:
                _composite_captions_onto_baked(
                    job_id, clip_id, edit, out, baked,
                    out_w=out_w, out_h=out_h, out_rel=out_rel,
                    crf=policy.video_crf, preset=policy.video_preset,
                )  # fmt: skip
                return
            # baked-клипа нет → причина уже залогирована в _ensure_baked_clip; падаем в полный путь.
        else:
            _rlog.info(
                "composite fast-path skipped (edit changes geometry/trim or no segment) "
                "→ full render: job=%s clip=%s",
                job_id,
                clip_id,
            )

    # ── FULL PATH: source + frame-accurate reframe (CV) + полный энкод ──
    artifacts.ensure_source(job_id)  # web-контейнер: скачать source.mp4 из R2 (тяжело)
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
    """Фон-таск для загруженного файла: БЫСТРЫЙ импорт аудио → тот же run_pipeline (без скачивания).

    prepare_upload_audio готовит source.wav + meta.json ИЗ СЫРОГО файла (БЕЗ дорогого ре-энкода)
    → run_pipeline(source_url=None) видит их как кэш Stage 0 и СРАЗУ идёт на транскрипцию (юзер
    видит «transcribing» почти мгновенно, а не после скрытой нормализации видео). Видео-нормализация
    в seekable source.mp4 ОТЛОЖЕНА в normalize_source: run_pipeline выполнит её ПОСЛЕ select, ПЕРЕД
    заливкой в R2/фан-аутом (где впервые нужен mp4). Статус в БД (правило №8 — падение → failed).
    """
    from pathlib import Path

    from app.pipeline.stage0_import import normalize_upload_source, prepare_upload_audio
    from app.run import DATA_ROOT

    src = Path(upload_path)
    out_dir = DATA_ROOT / job_id

    def on_status(status: JobStatus, progress: int) -> None:
        db.update_status(job_id, status.value, progress)

    def on_cancellable(v: bool) -> None:
        db.set_cancellable(job_id, v)

    quota: dict[str, Any] = {}
    try:
        db.update_status(job_id, JobStatus.downloading.value, 8)
        # БЫСТРЫЙ Stage 0: аудио+meta из СЫРОГО файла (транскрипция стартует почти сразу). Видео-
        # нормализация (_ensure_mp4: remux/ре-энкод) ОТЛОЖЕНА — run_pipeline выполнит её перед R2.
        prepare_upload_audio(src, out_dir, job_id=job_id, title=title)
        job = run_pipeline(
            job_id,
            source_url=None,
            on_status=on_status,
            max_clips=max_clips,
            on_meta=_quota_gate(user_id, quota),
            on_cancellable=on_cancellable,
            user_id=user_id,
            language=language,
            normalize_source=lambda: normalize_upload_source(src, out_dir),
        )
        db.set_done(job_id, job)
        _meter(user_id, job_id, job, quota)
    except JobError as e:
        db.set_failed(job_id, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        db.set_failed(job_id, f"unexpected: {e}")
