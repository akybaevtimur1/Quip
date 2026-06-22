"""FastAPI-входная точка воркера ClipFlow (этап J).

POST /jobs → создать задачу (BackgroundTask → tasks.run_pipeline_job), GET /jobs/{id} →
статус из SQLite (переживает рестарт), GET /healthz. Файлы клипов раздаются на /media.
CORS открыт для web (localhost:3000). Логика пайплайна — в app/pipeline/*, сюда не течёт.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__, auth, billing, db, dispatch, storage
from app.config import bootstrap_env, get_settings

# Локально активируем auth/billing-гейты из .env (как env-vars в проде). Под pytest НЕ
# грузим — тесты держат dual-mode (open) через monkeypatch отдельных переменных.
if "pytest" not in sys.modules:
    bootstrap_env()
from app.editor import presets as presets_mod
from app.editor import store, style_prefs
from app.editor.captions_v2 import compile_ass, compile_srt
from app.editor.ops import (
    add_section,
    apply_extend,
    apply_trim,
    clear_crop_overrides,
    set_crop_override,
    set_interval,
)
from app.editor.store import EditConflict
from app.editor.timeline import build_timeline_data
from app.editor.timemap import ClipTimeMap
from app.errors import JobError
from app.models import (
    AgentEvent,
    AgentRun,
    CaptionPreset,
    CaptionStyle,
    CaptionTrack,
    CropOverride,
    HighlightStyle,
)
from app.pipeline.stage5_render import aspect_to_dims
from app.run import DATA_ROOT
from app.tasks import (
    render_clip_edit_job,
    render_edit_to_file,
    run_pipeline_job,
    run_upload_job,
)

_UPLOAD_CHUNK = 1024 * 1024  # 1 МБ потоковой записи (не держим весь файл в памяти)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    yield


app = FastAPI(title="clipflow-worker", version=__version__, lifespan=lifespan)

# CORS: прод-домены quip.ink / www.quip.ink / app.quip.ink (апекс переехал на проект
# quip-app, см. docs/SEO_STRATEGY.md §4) + любые vercel-превью + локальный dev. Регулярка
# (не список), т.к. preview-домены Vercel динамические. Bearer-токен в заголовке (не cookie).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://((app\.|www\.)?quip\.ink|([a-z0-9-]+\.)*vercel\.app)|http://localhost:3000",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача артефактов: data/<job_id>/clips/<clip>.mp4 → /media/<job_id>/clips/<clip>.mp4
DATA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(DATA_ROOT)), name="media")


class CreateJobBody(BaseModel):
    source_type: str
    source_ref: str
    max_clips: int | None = Field(default=None, ge=1, le=30)  # UI-степпер; None → дефолт воркера


@app.get("/healthz")
def healthz() -> dict[str, bool | str]:
    """Liveness-проба. Выход: ``{"ok": True, "version": "..."}``. Без auth."""
    return {"ok": True, "version": __version__}


def _billing_enabled() -> bool:
    """Включён ли гейт квоты. Читаем env напрямую (не get_settings) → не триггерим
    валидацию ключей провайдеров и оставляем гейт инертным в тестах/без секретов."""
    return os.environ.get("BILLING_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _resolve_user(authorization: str | None, x_user_id: str | None) -> str | None:
    """user_id запроса. Auth включён (SUPABASE_URL задан) → из проверенного Supabase-JWT
    (401 при отсутствии/невалиде токена). Иначе dual-mode dev → заголовок X-User-Id (или None).

    ⚠️ Заменяет прежний плейсхолдер X-User-Id настоящей валидацией JWT (JWKS проекта).
    """
    if auth.supabase_auth_enabled():
        try:
            return auth.resolve_user_id(authorization)
        except auth.AuthError as e:
            raise HTTPException(status_code=401, detail=f"unauthorized: {e}") from e
    return x_user_id


def _enforce_free_identity(authorization: str | None, user_id: str | None) -> None:
    """Анти-абьюз free-плана: verified email + не одноразовый домен (серверно, авторитетно).

    Бесплатный план (2 видео) абьюзят пачками непроверенных/одноразовых ящиков. Гейт активен
    при включённых auth (SUPABASE_URL) И billing; ТОЛЬКО для FREE-плана — платные мимо (заплатил
    → не абьюз). Никогда не доверяем клиенту: email/verified берём из проверенного JWT (а где
    неоднозначно — из админ-lookup email_confirmed_at). Ошибки lookup всплывают (502), не «молча
    разрешить». Google OAuth уже verified Google → не блокируется (email_is_verified → True).

    Отказ 403 с actionable-сообщением: непроверенный email → «verify your inbox»; одноразовый
    домен → «use a real email». Зеркальная UX-валидация — на фронте (AuthForm), сервер — авторитет.
    """
    if not user_id or not _billing_enabled() or not auth.supabase_auth_enabled():
        return
    profile = db.get_profile(user_id)
    if billing.resolve_plan(profile["plan"]).id != "free":
        return  # платный план — анти-абьюз free-гейт не применяется
    try:
        # Сюда не должны дойти (quota-гейт уже валидировал токен), но без тихого пропуска.
        claims = auth.resolve_claims(authorization)
    except auth.AuthError as e:
        raise HTTPException(status_code=401, detail=f"unauthorized: {e}") from e
    email = auth.email_from_claims(claims)
    if email and billing.is_disposable_email(email):
        raise HTTPException(
            status_code=403,
            detail=(
                "Disposable email addresses aren't allowed on the free plan. "
                "Please sign up with a real email."
            ),
        )
    try:
        verified = auth.email_is_verified(claims)
    except Exception as e:  # noqa: BLE001 — админ-lookup упал → видимая ошибка, НЕ молчаливый пропуск
        raise HTTPException(status_code=502, detail=f"could not verify email status: {e}") from e
    if not verified:
        raise HTTPException(
            status_code=403,
            detail=(
                "Verify your email to use the free plan — check your inbox for the "
                "confirmation link, then try again."
            ),
        )


def _enforce_quota(user_id: str | None) -> None:
    """Create-time гейт: быстрый отказ, если месячные минуты + PAYG ПОЛНОСТЬЮ исчерпаны.

    Длину видео тут НЕ знаем (duration известна только после probe) → реальный лимит по
    длине применяется ПОСЛЕ импорта (``_quota_gate_after_probe`` в tasks.py, до транскрипции).
    No-op без BILLING_ENABLED/user_id. НИЧЕГО не списывает — списание только по факту
    готовых клипов (record_usage после set_done).
    """
    if not user_id or not _billing_enabled():
        return
    profile = db.get_profile(user_id)
    used = db.get_monthly_usage(user_id, billing.current_month())
    plan = billing.resolve_plan(profile["plan"])
    monthly_remaining = billing.plan_monthly_minutes(plan) - float(used["minutes"])
    payg_minutes = int(profile["payg_credits"]) * billing.MINUTES_PER_VIDEO
    if monthly_remaining <= 0 and payg_minutes <= 0:
        raise HTTPException(
            status_code=402,
            detail=(
                f"You're out of minutes on {plan.name} this month. "
                f"Upgrade your plan or top up to keep creating clips."
            ),
        )


@app.get("/usage")
def get_usage(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Живой расход для UsageMeter: план + остаток видео-кредитов в этом месяце + PAYG.

    Auth включён → данные пользователя из profiles/usage_events. Без юзера (dev) → дефолт free.
    """
    user_id = _resolve_user(authorization, x_user_id)
    plan = billing.resolve_plan(db.get_profile(user_id)["plan"] if user_id else "free")
    used_minutes = (
        float(db.get_monthly_usage(user_id, billing.current_month())["minutes"]) if user_id else 0.0
    )
    payg_videos = int(db.get_profile(user_id)["payg_credits"]) if user_id else 0
    return _usage_payload(plan, used_minutes, payg_videos)


def _usage_payload(
    plan: billing.PlanLimits, used_minutes: float, payg_videos: int
) -> dict[str, Any]:
    """Сборка ответа /usage в МИНУТАХ и «видео» (= минуты/60) для UsageMeter. PURE-ish."""
    monthly_minutes = billing.plan_monthly_minutes(plan)
    remaining_minutes = max(0.0, monthly_minutes - used_minutes)
    payg_minutes = payg_videos * billing.MINUTES_PER_VIDEO
    return {
        "plan": plan.id,
        "plan_name": plan.name,
        "monthly_videos": plan.monthly_videos,
        "monthly_minutes": monthly_minutes,
        "used_minutes": round(used_minutes, 1),
        "remaining_minutes": round(remaining_minutes, 1),
        "remaining_videos": billing.minutes_to_videos(remaining_minutes),
        "payg_videos": payg_videos,
        "payg_minutes": payg_minutes,
    }


@app.post("/jobs", status_code=202)
def create_job(
    body: CreateJobBody,
    bg: BackgroundTasks,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Создать задачу: auth (JWT) → анти-абьюз free → гейт квоты → queued + фоновый прогон."""
    user_id = _resolve_user(authorization, x_user_id)
    _enforce_free_identity(authorization, user_id)
    _enforce_quota(user_id)
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    db.insert_job(job_id, body.source_type, body.source_ref, user_id=user_id)
    # На Modal: spawn отдельной долгоживущей CPU-функции (web scale-to-zero убил бы фон-таск).
    # Локально: BackgroundTask, как в Phase 0.
    if dispatch.modal_spawn_enabled():
        # spawn упал ДО старта пайплайна → джоб застрял бы в "queued" навсегда. Помечаем
        # failed и поднимаем 500 (правило №8): юзер видит причину, а не вечную очередь.
        try:
            fc_id = dispatch.spawn(
                "run_job", job_id, body.source_type, body.source_ref, body.max_clips, user_id
            )
            db.set_function_call_id(job_id, fc_id)  # для Stop-кнопки (отмена джоба)
        except Exception as e:  # noqa: BLE001 — любой сбой диспатча = видимый failed
            db.set_failed(job_id, f"dispatch failed: {e}")
            raise HTTPException(status_code=500, detail=f"job dispatch failed: {e}") from e
    else:
        bg.add_task(
            run_pipeline_job, job_id, body.source_type, body.source_ref, body.max_clips, user_id
        )
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}


@app.post("/jobs/upload", status_code=202)
async def create_upload_job(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    max_clips: int | None = Form(default=None, ge=1, le=30),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Создать задачу из ЗАГРУЖЕННОГО файла: стримим на диск → фон-импорт → пайплайн.

    Файл пишется чанками в data/<job_id>/upload.<ext> (не держим в памяти); затем
    run_upload_job готовит source.mp4/wav/meta и гоняет тот же пайплайн, что и URL-путь.
    """
    user_id = _resolve_user(authorization, x_user_id)
    _enforce_free_identity(authorization, user_id)
    _enforce_quota(user_id)
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    out = DATA_ROOT / job_id
    out.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "upload.mp4"
    suffix = Path(filename).suffix.lower() or ".mp4"
    upload_path = out / f"upload{suffix}"
    with upload_path.open("wb") as fh:
        while chunk := await file.read(_UPLOAD_CHUNK):
            fh.write(chunk)
    db.insert_job(job_id, "upload", filename, user_id=user_id)
    # На Modal: web — scale-to-zero ASGI-контейнер; BackgroundTask умер бы на полпути (как и у
    # YouTube-пути). Поэтому стейджим исходник в R2 (upload_source) и spawn'им долгоживущую
    # upload_job (она скачает исходник из R2 на своём контейнере → run_upload_job). Локально/dev
    # (MODAL_SPAWN не задан) — BackgroundTask на этом же процессе, как в Phase 0.
    if dispatch.modal_spawn_enabled():
        try:
            storage.upload_source(upload_path, job_id)  # r2-режим; иначе no-op
            dispatch.spawn("upload_job", job_id, filename, max_clips, user_id)
        except Exception as e:  # noqa: BLE001 — любой сбой диспатча = видимый failed, не вечная очередь
            db.set_failed(job_id, f"dispatch failed: {e}")
            raise HTTPException(status_code=500, detail=f"upload dispatch failed: {e}") from e
    else:
        bg.add_task(run_upload_job, job_id, str(upload_path), filename, max_clips, user_id)
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}


class UploadUrlBody(BaseModel):
    filename: str = "upload.mp4"
    max_clips: int | None = Field(default=None, ge=1, le=30)
    # Размер файла (байты) — известен браузеру. >5 ГБ нельзя одним PUT (лимит R2), а крупные и
    # вообще выгоднее multipart (параллельные части + resume). None/малый → single-PUT (как раньше).
    size: int | None = Field(default=None, ge=0)


@app.post("/jobs/upload-url")
def create_upload_url(
    body: UploadUrlBody,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Прямая загрузка браузер→R2: presigned PUT (мелкие) ИЛИ multipart-план (крупные) ИЛИ local.

    Большие видео через ОДИН долгий POST на Modal web рвались. Тут браузер льёт файл ПРЯМО в R2:
    - size ≤ part_size → один presigned PUT (как раньше);
    - size > part_size → multipart: создаём upload, отдаём presigned-URL на КАЖДУЮ часть; браузер
      грузит части параллельно и зовёт upload-complete с их ETag'ами → R2 собирает объект.
    Локально (нет R2) → {"local": true} → фронт шлёт обычный multipart POST /jobs/upload (dev ок).
    Квота гейтится ЗДЕСЬ (до загрузки). Джоб в БД создаётся в upload-complete (после PUT) —
    отменённая загрузка не оставляет «queued»-сироту.

    PERF: identity-гейт (verified email / disposable — несколько раунд-трипов в Supabase, вкл.
    Admin API) тут НЕ зовём — он висел на горячем пути и задерживал старт загрузки (presigned-URL
    сам по себе локальный). Защита НЕ ослаблена: identity отрабатывает в upload-complete (строка
    ниже) ДО spawn'а платной джобы — без подтверждённого email обработка не запустится, а presigned
    PUT отдаём мгновенно (байты в R2 пошли сразу). Квоту оставляем тут (fail-fast до заливки).
    """
    user_id = _resolve_user(authorization, x_user_id)
    _enforce_quota(user_id)
    if get_settings().storage_backend != "r2":
        return {"local": True}
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    size = body.size or 0
    if size > storage.MULTIPART_PART_SIZE:
        upload_id = storage.create_multipart_upload(job_id)
        n_parts = storage.plan_part_count(size, storage.MULTIPART_PART_SIZE)
        parts = [
            {"part_number": i, "url": storage.presigned_upload_part_url(job_id, upload_id, i)}
            for i in range(1, n_parts + 1)
        ]
        return {
            "id": job_id,
            "upload_id": upload_id,
            "part_size": storage.MULTIPART_PART_SIZE,
            "parts": parts,
        }
    return {"id": job_id, "put_url": storage.presigned_put_url(job_id)}


class CompletedPart(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str


class UploadCompleteBody(BaseModel):
    filename: str = "upload.mp4"
    max_clips: int | None = Field(default=None, ge=1, le=30)
    # Multipart-сборка (если грузили частями): upload_id + ETag'и частей. None → single-PUT
    # (объект уже в R2, собирать нечего).
    upload_id: str | None = None
    parts: list[CompletedPart] | None = None


@app.post("/jobs/{job_id}/upload-complete")
def complete_upload(
    job_id: str,
    body: UploadCompleteBody,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Браузер залил исходник в R2 (presigned PUT) → запустить пайплайн (spawn upload_job).

    upload_job скачает исходник из R2 (тот же ключ source) и гоняет run_upload_job — как раньше.

    Безопасность: квоту гейтим ЗДЕСЬ ТОЖЕ (не только в upload-url) — спавн платной джобы не должен
    проходить без проверки (consistency со старым POST /jobs/upload). Авторизация по job_id: id —
    серверный случайный uuid из upload-url, а залить файл в ``job_id/source.mp4`` можно только по
    per-job presigned PUT оттуда же → чужой job_id не угадать/не подделать (джоба всегда на своего).
    """
    user_id = _resolve_user(authorization, x_user_id)
    _enforce_free_identity(authorization, user_id)
    _enforce_quota(user_id)
    if not dispatch.modal_spawn_enabled():
        raise HTTPException(status_code=400, detail="direct upload only in cloud mode")
    db.insert_job(job_id, "upload", body.filename, user_id=user_id)
    # Multipart: сначала собрать объект из частей (иначе upload_job скачает пусто/битое).
    if body.upload_id and body.parts:
        try:
            storage.complete_multipart_upload(
                job_id,
                body.upload_id,
                [{"PartNumber": p.part_number, "ETag": p.etag} for p in body.parts],
            )
        except Exception as e:  # noqa: BLE001 — сборка не удалась → видимый failed, не тихо
            db.set_failed(job_id, f"multipart complete failed: {e}")
            raise HTTPException(status_code=500, detail=f"multipart complete failed: {e}") from e
    try:
        fc_id = dispatch.spawn("upload_job", job_id, body.filename, body.max_clips, user_id)
        db.set_function_call_id(job_id, fc_id)  # для Stop-кнопки (отмена джоба)
    except Exception as e:  # noqa: BLE001 — сбой диспатча = видимый failed, не вечная очередь
        db.set_failed(job_id, f"dispatch failed: {e}")
        raise HTTPException(status_code=500, detail=f"upload dispatch failed: {e}") from e
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}


class UploadAbortBody(BaseModel):
    upload_id: str


@app.post("/jobs/{job_id}/upload-abort")
def abort_upload(
    job_id: str,
    body: UploadAbortBody,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Браузер отменил/уронил multipart-загрузку → удалить залитые части из R2 (не копить мусор).

    Best-effort: чистка не должна ронять и без того ошибочный флоу — сбой самой abort возвращаем
    как ``{"ok": false}`` (а не 500). Auth обязателен (чужой upload не отменить).
    """
    _resolve_user(authorization, x_user_id)
    try:
        storage.abort_multipart_upload(job_id, body.upload_id)
    except Exception:  # noqa: BLE001 — cleanup best-effort; незавершённые части подберёт lifecycle R2
        return {"ok": False}
    return {"ok": True}


@app.post("/webhooks/polar")
async def polar_webhook(request: Request) -> dict[str, Any]:
    """Вебхук оплаты Polar.sh → profiles.plan. Проверяет подпись Standard Webhooks
    (webhook-id/timestamp/signature по POLAR_WEBHOOK_SECRET), маппит product→план, пишет
    set_user_plan (service-role на Postgres). Не сконфигурирован → 503; плохая подпись →
    401; чужой/непонятный ивент → 200 applied=false (Polar не ретраит).
    См. docs/SUPABASE_SETUP.md §4.
    """
    import json

    from app import billing, polar

    secret = os.environ.get("POLAR_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Polar webhook not configured")
    body = await request.body()
    if not polar.verify_signature(
        secret,
        body,
        webhook_id=request.headers.get("webhook-id", ""),
        webhook_timestamp=request.headers.get("webhook-timestamp", ""),
        signature_header=request.headers.get("webhook-signature", ""),
    ):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid JSON body") from e
    change = polar.parse_plan_change(
        payload,
        product_starter=os.environ.get("POLAR_PRODUCT_STARTER", ""),
        product_pro=os.environ.get("POLAR_PRODUCT_PRO", ""),
    )
    if change is not None:
        user_id, plan = change
        db.set_user_plan(user_id, plan)
        return {"ok": True, "applied": True, "user_id": user_id, "plan": plan}

    # Разовая оплата PAYG → начислить не сгорающие кредиты.
    payg = polar.parse_payg_order(
        payload,
        product_payg=os.environ.get("POLAR_PRODUCT_PAYG", ""),
        credits_per_order=billing.PAYG_CREDITS_PER_ORDER,
    )
    if payg is not None:
        user_id, credits = payg
        db.add_payg_credits(user_id, credits)
        return {"ok": True, "applied": True, "user_id": user_id, "payg_credits": credits}

    return {"ok": True, "applied": False}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Статус задачи (wire-Job) из SQLite. 404, если задачи нет."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Stop-кнопка: отменить джоб во FREE-фазе (download/probe, до транскрипции) — $0 заряда.

    Отмена возможна ТОЛЬКО пока ``cancellable`` (воркер гасит флаг перед платной транскрипцией).
    Идемпотентна на done/failed/cancelled. На Modal отменяем ОТДЕЛЬНУЮ долгоживущую функцию по
    её ``function_call_id`` (``terminate_containers=False`` → внутри неё рейзится
    ``InputCancellation``, она выходит ДО set_done/_meter → ничего не списывается).
    """
    user_id = _resolve_user(authorization, x_user_id)
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    # Ownership: при включённом auth джоб может отменить только его владелец. Старые джобы без
    # user_id (None) не привязаны → не блокируем (dual-mode/legacy).
    if auth.supabase_auth_enabled() and row.get("user_id") not in (None, user_id):
        raise HTTPException(status_code=403, detail="not your job")
    status = row.get("status")
    if status in ("done", "failed", "cancelled"):
        # Уже в терминале → отменять нечего (идемпотентно, не ошибка).
        return {"id": job_id, "status": status, "cancelled": False}
    if not row.get("cancellable"):
        raise HTTPException(
            status_code=409,
            detail="job has entered a paid stage and can no longer be stopped",
        )
    fc_id = row.get("function_call_id")
    if fc_id:
        try:
            import modal

            modal.FunctionCall.from_id(str(fc_id)).cancel(terminate_containers=False)
        except Exception as e:  # noqa: BLE001 — отмена Modal не удалась → НЕ молча (правило №8)
            # Всё равно фиксируем cancelled в БД (поллинг остановится), но сигналим 502, чтобы
            # фронт знал: фон-функция могла не остановиться (нет тихого фолбэка).
            db.set_cancelled(job_id)
            raise HTTPException(status_code=502, detail=f"cancel failed: {e}") from e
    db.set_cancelled(job_id)
    return {"id": job_id, "status": "cancelled", "cancelled": True}


@app.get("/jobs/{job_id}/source.mp4")
def get_source(job_id: str) -> Response:
    """Полный исходник (редактор-рендер / фолбэк превью). local → диск; r2 → 302 на CDN (или
    presigned). Раньше всегда presigned-origin без кэша = медленно; теперь CDN при R2_PUBLIC_URL."""
    s = get_settings()
    if s.storage_backend == "r2":
        from fastapi.responses import RedirectResponse

        from app.storage import source_read_url

        return RedirectResponse(source_read_url(job_id))
    path = DATA_ROOT / job_id / "source.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="source not found")
    return FileResponse(str(path), media_type="video/mp4")


@app.get("/jobs/{job_id}/preview.mp4")
def get_preview(job_id: str) -> Response:
    """Лёгкий preview-прокси для БЫСТРОЙ загрузки видео в редакторе (≤720p H.264 faststart, пара МБ
    вместо 50-100МБ source; H.264 = hw-декод, не софт-AV1). Нет прокси (старый джоб до фичи) →
    прозрачный фолбэк на полный source. local → диск; r2 → 302 на CDN/presigned."""
    s = get_settings()
    if s.storage_backend == "r2":
        from fastapi.responses import RedirectResponse

        from app.storage import preview_read_url

        return RedirectResponse(preview_read_url(job_id))
    prev = DATA_ROOT / job_id / "preview.mp4"
    if prev.exists():
        return FileResponse(str(prev), media_type="video/mp4")
    src = DATA_ROOT / job_id / "source.mp4"
    if src.exists():
        return FileResponse(str(src), media_type="video/mp4")
    raise HTTPException(status_code=404, detail="preview/source not found")


@app.get("/jobs/{job_id}/timeline")
def get_timeline(job_id: str) -> dict[str, Any]:
    """TimelineData: длительность источника + ВСЕ кандидаты ИИ + слова (для таймлайн-редактора).

    Собирается из готовых meta/segments/transcript (диск локально, Postgres на Modal).
    Дорогих ИИ-вызовов НЕТ. 404, если артефактов нет (как /analysis).
    """
    from app import artifacts

    try:
        meta = artifacts.load_meta(job_id)
        segments = artifacts.load_segments(job_id)
        words = artifacts.load_transcript_words(job_id)
    except JobError as e:
        raise HTTPException(status_code=404, detail="timeline data not found") from e
    return build_timeline_data(meta.duration, segments, words).model_dump()


@app.get("/jobs/{job_id}/chapters")
def get_chapters(job_id: str, bg: BackgroundTasks, retry: bool = False) -> dict[str, Any]:
    """AI-карта видео (главы с описаниями). Кэш data/<job>/chapters.json.

    Файла нет → пишем pending + стартуем фон-генерацию (Gemini, ~$0.01-0.03,
    платится один раз); фронт поллит до done/failed. 404 — нет транскрипта.
    Повторный GET при pending вторую генерацию НЕ стартует.

    retry=true (T4 #9): если кэш — failed (квота Gemini free-tier 20/день), перезапускаем
    генерацию (перетираем failed → pending). На done/pending retry игнорируется (не дёргаем).
    """
    from app import artifacts
    from app import tasks as tasks_mod
    from app.editor.chapters import load_chapters, save_chapters
    from app.models import ChaptersData

    out = artifacts.job_dir(job_id)
    out.mkdir(parents=True, exist_ok=True)
    try:
        artifacts.load_transcript(job_id)  # 404, если транскрипта нет нигде (диск/Postgres)
    except JobError as e:
        raise HTTPException(status_code=404, detail="transcript not found") from e
    # NB: кэш chapters.json — на scratch-диске контейнера; на Modal может перегенериться на
    # холодном web-контейнере (Gemini-вызов). Перенос кэша в Postgres — follow-up (Phase C).
    cached = load_chapters(out)
    if cached is not None and not (retry and cached.status == "failed"):
        return cached.model_dump()
    pending = ChaptersData(status="pending")
    save_chapters(out, pending)
    bg.add_task(tasks_mod.generate_chapters_job, job_id)
    return pending.model_dump()


@app.get("/jobs/{job_id}/video-map")
def get_video_map(job_id: str, bg: BackgroundTasks, retry: bool = False) -> dict[str, Any]:
    """Нарративная VideoMap (главы+моменты+связный разбор). Durable в Postgres (cross-container).

    Нет карты → пишем pending + триггерим генерацию (Gemini, платится один раз); фронт поллит до
    done/failed. 404 — нет транскрипта. Повторный GET при pending вторую генерацию НЕ стартует.

    ⚠️ Cloud: генерация идёт в ОТДЕЛЬНОМ Modal-контейнере (dispatch.spawn — bg.add_task сдох бы на
    scale-to-zero web). save/load_video_map round-trip'ят через Postgres job_artifacts, поэтому этот
    web-контейнер видит результат чужого контейнера. Локально (нет Modal) — bg.add_task + диск.

    retry=true: кэш failed → перезапуск (перетираем failed → pending). На done/pending игнор.
    """
    from app import artifacts
    from app import tasks as tasks_mod
    from app.editor.video_map import load_video_map, save_video_map
    from app.models import VideoMap

    try:
        artifacts.load_transcript(job_id)  # 404, если транскрипта нет нигде (диск/Postgres)
    except JobError as e:
        raise HTTPException(status_code=404, detail="transcript not found") from e
    cached = load_video_map(job_id)
    if cached is not None and not (retry and cached.status == "failed"):
        return cached.model_dump()
    pending = VideoMap(status="pending")
    save_video_map(job_id, pending)
    if dispatch.modal_spawn_enabled():
        dispatch.spawn("generate_video_map_job", job_id)
    else:
        bg.add_task(tasks_mod.generate_video_map_job, job_id)
    return pending.model_dump()


@app.get("/jobs/{job_id}/preview-moments")
def get_preview_moments(job_id: str) -> dict[str, Any]:
    """Косметические co-watch-маркеры (Part 4): список {t,kind,intensity} из job_artifacts.

    ⚠️ ЧИСТО ВИЗУАЛЬНО — НЕ влияет на отбор клипов (LLM-отбор от них не зависит). Пусто, пока
    transcribe не закончил, на старых джобах, или в локальном dev (артефакты — только в облаке).
    """
    moments = db.get_job_artifact(job_id, "preview_moments")
    return {"moments": moments or []}


# ──────────────────────────── Editor endpoints ────────────────────────────


class PatchEditBody(BaseModel):
    version: int
    captions: CaptionTrack


class TrimBody(BaseModel):
    version: int
    word_indices: list[int]


class AddSectionBody(BaseModel):
    version: int
    source_start: float
    source_end: float
    at_index: int


class ExtendBody(BaseModel):
    version: int
    edge: str  # "start" | "end"
    new_value: float


class CropBody(BaseModel):
    version: int
    source_start: float
    source_end: float
    mode: Literal["fill", "fit", "split", "auto"]  # auto = снять override (вернуть авто)
    center: float | None = Field(default=None, ge=0.0, le=1.0)
    center_b: float | None = Field(default=None, ge=0.0, le=1.0)  # split: нижняя половина


class SetIntervalBody(BaseModel):
    version: int
    source_start: float
    source_end: float


class RegenerateHookBody(BaseModel):
    version: int


class AgentStartBody(BaseModel):
    message: str


def _save_or_409(job_id: str, clip_id: str, new_edit: Any, version: int) -> dict[str, Any]:
    try:
        return store.save_edit(job_id, clip_id, new_edit, expected_version=version).model_dump()
    except EditConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _load_or_404(job_id: str, clip_id: str) -> Any:
    edit = store.load_edit(job_id, clip_id)
    if edit is None:
        raise HTTPException(status_code=404, detail="edit not found")
    return edit


def _op_or_400(fn: Callable[[], Any]) -> Any:
    """Прогнать pure-операцию редактора (ops.py), переведя её доменный JobError в HTTP 400.

    ops.py рейзит JobError на НЕВАЛИДНЫЙ ввод (индекс вне диапазона, перевёрнутый интервал,
    неизвестный край). Без перехвата это всплывало 500 (баг сервера) вместо 400 (ошибка
    клиента). Зеркалит трансляцию GET-хендлеров (JobError → 404 там, где это «не найдено»)."""
    try:
        return fn()
    except JobError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/jobs/{job_id}/clips/{clip_id}/edit")
def get_clip_edit(job_id: str, clip_id: str) -> dict[str, Any]:
    """ClipEdit клипа (создаёт дефолт из сегмента при первом обращении)."""
    try:
        return store.ensure_edit(job_id, clip_id).model_dump()
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e


@app.get("/jobs/{job_id}/clips/{clip_id}/ass")
def get_clip_ass(job_id: str, clip_id: str) -> Response:
    """ASS субтитров текущего edit-state (для libass-превью в браузере).

    Тот же компилятор, что и финальный экспорт (captions_v2.compile_ass) → превью
    субтитров через libass.wasm = экспорт пиксель-в-пиксель. Тайминги в КЛИП-времени.
    """
    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    words = store.load_transcript_words(job_id)
    cmap = ClipTimeMap(edit.source_intervals)
    pw, ph = aspect_to_dims(edit.aspect)  # T5: PlayRes = размеры выхода аспекта
    ass = compile_ass(edit.captions, words, cmap, play_w=pw, play_h=ph)
    return Response(content=ass, media_type="text/plain; charset=utf-8")


@app.get("/jobs/{job_id}/clips/{clip_id}/export.srt")
def export_clip_srt(job_id: str, clip_id: str) -> Response:
    """SRT субтитров текущего edit-state (экспорт-свобода: унести в любой редактор).

    compile_srt зеркалит compile_ass (те же реплики/тайминги) → скачанный SRT
    совпадает с прожжённым видео. Content-Disposition: attachment → браузер скачивает.
    """
    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    words = store.load_transcript_words(job_id)
    cmap = ClipTimeMap(edit.source_intervals)
    srt = compile_srt(edit.captions, words, cmap)
    return Response(
        content=srt,
        media_type="application/x-subrip; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{clip_id}.srt"'},
    )


@app.get("/jobs/{job_id}/clips/{clip_id}/export/clean.mp4")
def export_clip_clean_mp4(job_id: str, clip_id: str) -> FileResponse:
    """Чистый mp4 БЕЗ прожжённых субтитров (экспорт-свобода: пере-монтаж где угодно).

    Рендерит текущий edit-state с ass_name=None в clips/{clip}_clean.mp4 и отдаёт файл.
    Синхронно: рендер ~секунды (FastAPI крутит sync-эндпоинт в threadpool). Очередь/статус —
    на этапе масштаба (infra-план §2.3). Сбой рендера → HTTP 500 (правило №8, не тихо).
    """
    try:
        store.ensure_edit(job_id, clip_id)  # из грида (без открытия редактора) тоже работает
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    out_rel = f"clips/{clip_id}_clean.mp4"
    try:
        render_edit_to_file(job_id, clip_id, with_subtitles=False, out_rel=out_rel)
    except JobError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    path = store.data_root() / job_id / out_rel
    if not path.exists():
        raise HTTPException(status_code=500, detail="render produced no clean mp4")
    return FileResponse(str(path), media_type="video/mp4", filename=f"{clip_id}_clean.mp4")


@app.get("/jobs/{job_id}/clips/{clip_id}/export/captioned.mp4")
def export_clip_captioned_mp4(job_id: str, clip_id: str) -> FileResponse:
    """Прожжённый mp4 С субтитрами текущего edit-state (download «С субтитрами»).

    D1-унификация: рендерит ТЕКУЩИЕ правки (тот же ASS, что в libass-превью) → скачанный
    файл всегда совпадает с превью (WYSIWYG), доступен без отдельного «Рендер» и НЕ трогает
    чистый ``clips/{clip}.mp4``. Синхронно (FastAPI threadpool). Сбой рендера → HTTP 500
    (правило №8). Один путь и для грида, и для редактора — нет расхождения «с субтитрами».
    """
    try:
        store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    out_rel = f"clips/{clip_id}_captioned.mp4"
    try:
        render_edit_to_file(job_id, clip_id, with_subtitles=True, out_rel=out_rel)
    except JobError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    path = store.data_root() / job_id / out_rel
    if not path.exists():
        raise HTTPException(status_code=500, detail="render produced no captioned mp4")
    return FileResponse(str(path), media_type="video/mp4", filename=f"{clip_id}.mp4")


@app.patch("/jobs/{job_id}/clips/{clip_id}/edit")
def patch_clip_edit(job_id: str, clip_id: str, body: PatchEditBody) -> dict[str, Any]:
    """Прямая правка субтитров (стиль/текст/highlight). Интервалы не трогает."""
    edit = _load_or_404(job_id, clip_id)
    return _save_or_409(
        job_id, clip_id, edit.model_copy(update={"captions": body.captions}), body.version
    )


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/trim")
def op_trim(job_id: str, clip_id: str, body: TrimBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = _op_or_400(lambda: apply_trim(edit, body.word_indices, words))
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/add-section")
def op_add_section(job_id: str, clip_id: str, body: AddSectionBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = _op_or_400(
        lambda: add_section(edit, body.source_start, body.source_end, body.at_index, words)
    )
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/extend")
def op_extend(job_id: str, clip_id: str, body: ExtendBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = _op_or_400(
        lambda: apply_extend(edit, edge=body.edge, new_value=body.new_value, words=words)
    )
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/crop")
def op_crop(job_id: str, clip_id: str, body: CropBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    if body.mode == "auto":
        new = clear_crop_overrides(edit, body.source_start, body.source_end)
        return _save_or_409(job_id, clip_id, new, body.version)
    ov = CropOverride(
        source_start=body.source_start,
        source_end=body.source_end,
        mode=body.mode,
        center=body.center,
        center_b=body.center_b,
    )
    return _save_or_409(job_id, clip_id, set_crop_override(edit, ov), body.version)


class AspectBody(BaseModel):
    version: int
    aspect: Literal["9:16", "1:1", "4:5", "16:9"]


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/aspect")
def op_set_aspect(job_id: str, clip_id: str, body: AspectBody) -> dict[str, Any]:
    """Сменить соотношение сторон клипа (T5). Меняет только выход — reframe-регионы (cx)
    переносятся, временная кадровая сетка не трогается (Δ=0 инвариант цел)."""
    edit = _load_or_404(job_id, clip_id)
    return _save_or_409(
        job_id, clip_id, edit.model_copy(update={"aspect": body.aspect}), body.version
    )


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/set-interval")
def op_set_interval(job_id: str, clip_id: str, body: SetIntervalBody) -> dict[str, Any]:
    """Заменить первичный интервал клипа окном [start,end] (двигать/resize на таймлайне).

    Границы клампятся в [0,duration] и в [clip_min_sec, clip_max_sec] (set_interval, PURE).
    Optimistic-lock (409 при version mismatch).
    """
    from app import artifacts

    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    meta = artifacts.load_meta(job_id)
    s = get_settings()
    new = _op_or_400(
        lambda: set_interval(
            edit,
            body.source_start,
            body.source_end,
            words,
            duration=meta.duration,
            min_sec=s.clip_min_sec,
            max_sec=s.clip_max_sec,
        )
    )
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/hook/regenerate")
def op_regenerate_hook(job_id: str, clip_id: str, body: RegenerateHookBody) -> dict[str, Any]:
    """W4: перегенерировать ТЕКСТ хука под текущий интервал клипа (узкий Gemini-вызов, НЕ чат).

    Хук — хранимый текст; сдвиг клипа на таймлайне его не меняет → устаревает. Эта ручка
    (явная кнопка в редакторе = opt-in, не перетираем молча) берёт транскрипт ТОЛЬКО этого клипа
    (слова в его интервалах) и просит Gemini новый хук в стиле W2. Меняем лишь ``hook.text`` —
    стиль/позицию/плашку (W5) НЕ трогаем. Цена sub-cent → НЕ метрим (как прочие правки редактора).
    Optimistic-lock (409 при version mismatch).
    """
    from app.editor.hook_ops import regenerate_hook_for_clip

    edit = _load_or_404(job_id, clip_id)
    try:
        new_edit, _hook_text = regenerate_hook_for_clip(job_id, edit)
    except JobError as e:
        # нет слов (400) / Gemini недоступен (502) — явная причина, не тихий фолбэк (правило №8).
        code = 400 if "no words" in str(e) else 502
        raise HTTPException(status_code=code, detail=f"hook regeneration failed: {e}") from e
    return _save_or_409(job_id, clip_id, new_edit, body.version)


# ─────────────────────────── W3: агентный чат-редактор клипа ───────────────────────────

_AGENT_TERMINAL = ("done", "failed", "cancelled")
_AGENT_MSG_MAX = 2000
_AGENT_HISTORY_SEED_MAX = 40  # сколько прошлых событий ленты подсевать в новый run (история чата)


def _seed_events(prior: dict[str, Any] | None) -> list[dict[str, Any]]:
    """События прошлого прогона клипа для подсева в новый run (история чата, #1). Кап последних
    N → UI показывает непрерывный тред без безграничного роста ленты."""
    if not prior:
        return []
    evs = prior.get("events") or []
    return list(evs[-_AGENT_HISTORY_SEED_MAX:])


def _agent_payload(run: dict[str, Any]) -> dict[str, Any]:
    """Ряд agent_run → wire-AgentRun (без внутреннего function_call_id)."""
    return AgentRun(
        run_id=run["run_id"],
        job_id=run["job_id"],
        clip_id=run["clip_id"],
        status=run["status"],
        events=[AgentEvent(**e) for e in run["events"]],
        error=run.get("error"),
        cancellable=run["cancellable"],
    ).model_dump()


def _run_agent_bg(run_id: str) -> None:
    from app.agent.clip_agent import run_clip_agent

    run_clip_agent(run_id)


@app.post("/jobs/{job_id}/clips/{clip_id}/agent/start")
def agent_start(
    job_id: str,
    clip_id: str,
    body: AgentStartBody,
    bg: BackgroundTasks,
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """W3: запустить агента на клипе. Один активный run на клип (идемпотентно). Спавн как у джоба;
    отмена — `function_call_id`. Биллинг не трогаем. Сбой диспатча → failed."""
    from app.agent import runs_store

    try:
        store.ensure_edit(job_id, clip_id)  # создаём дефолт из сегмента, если ещё нет
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="empty message")
    msg = msg[:_AGENT_MSG_MAX]
    existing = runs_store.running_run(job_id, clip_id)
    if existing is not None:
        return _agent_payload(existing)  # уже работает → не плодим (дабл-клик/гонка)
    # История чата (#1): прошлый прогон клипа ДО создания нового (latest_run иначе вернёт пустой
    # новый). Засеваем его ленту в новый run → UI = непрерывный тред, агент = память (run_clip_agent
    # берёт prior из ленты). Берём ДО create_run.
    prior = runs_store.latest_run(job_id, clip_id)
    run_id = runs_store.new_run_id()
    runs_store.create_run(run_id, job_id, clip_id, x_user_id)
    for ev in _seed_events(prior):
        runs_store.append_event(run_id, ev)
    runs_store.append_event(run_id, AgentEvent(role="user", text=msg).model_dump())
    if dispatch.modal_spawn_enabled():
        try:
            fc_id = dispatch.spawn("agent_edit_job", run_id)
        except Exception as e:  # noqa: BLE001 — сбой диспатча видим (правило №8)
            runs_store.set_status(run_id, "failed", f"dispatch failed: {e}")
            raise HTTPException(status_code=500, detail=f"agent dispatch failed: {e}") from e
        if fc_id:
            runs_store.set_function_call_id(run_id, fc_id)
    else:
        bg.add_task(_run_agent_bg, run_id)
    run = runs_store.get_run(run_id)
    assert run is not None
    return _agent_payload(run)


@app.get("/jobs/{job_id}/clips/{clip_id}/agent/active")
def agent_active(job_id: str, clip_id: str) -> dict[str, Any] | None:
    """Активный (running) прогон для клипа — реконнект после перезагрузки вкладки."""
    from app.agent import runs_store

    run = runs_store.running_run(job_id, clip_id)
    return _agent_payload(run) if run is not None else None


@app.get("/jobs/{job_id}/clips/{clip_id}/agent/{run_id}")
def agent_get(job_id: str, clip_id: str, run_id: str) -> dict[str, Any]:
    """Статус+лента прогона (поллинг фронтом)."""
    from app.agent import runs_store

    run = runs_store.get_run(run_id)
    if run is None or run["job_id"] != job_id or run["clip_id"] != clip_id:
        raise HTTPException(status_code=404, detail="agent run not found")
    return _agent_payload(run)


@app.post("/jobs/{job_id}/clips/{clip_id}/agent/{run_id}/cancel")
def agent_cancel(job_id: str, clip_id: str, run_id: str) -> dict[str, Any]:
    """Stop: отменить прогон агента. Идемпотентно на терминале. $0 (агент минут не списывает)."""
    from app.agent import runs_store

    run = runs_store.get_run(run_id)
    if run is None or run["job_id"] != job_id or run["clip_id"] != clip_id:
        raise HTTPException(status_code=404, detail="agent run not found")
    if run["status"] in _AGENT_TERMINAL:
        return _agent_payload(run)
    fc_id = run.get("function_call_id")
    if fc_id:
        try:
            import modal

            modal.FunctionCall.from_id(str(fc_id)).cancel(terminate_containers=False)
        except Exception as e:  # noqa: BLE001 — отмена Modal не удалась → НЕ молча (правило №8)
            runs_store.set_cancelled(run_id)
            raise HTTPException(status_code=502, detail=f"cancel failed: {e}") from e
    runs_store.set_cancelled(run_id)
    updated = runs_store.get_run(run_id)
    assert updated is not None
    return _agent_payload(updated)


@app.post("/jobs/{job_id}/clips/{clip_id}/render", status_code=202)
def post_render(job_id: str, clip_id: str, bg: BackgroundTasks) -> dict[str, Any]:
    """Async-рендер mp4 из edit-state. Статус — GET …/render.

    На Modal — spawn отдельной CPU-функции (web scale-to-zero убил бы фон-рендер); локально — bg.
    """
    _load_or_404(job_id, clip_id)
    db.set_render_status(job_id, clip_id, "rendering", None, None)
    if dispatch.modal_spawn_enabled():
        # spawn может упасть (modal import/lookup) ДО старта рендера → клип застрял бы в
        # "rendering" навсегда. Переводим в failed и поднимаем 500 (правило №8, не молча).
        try:
            dispatch.spawn("render_job", job_id, clip_id)
        except Exception as e:  # noqa: BLE001 — любой сбой диспатча = видимый failed
            db.set_render_status(job_id, clip_id, "failed", None, f"dispatch failed: {e}")
            raise HTTPException(status_code=500, detail=f"render dispatch failed: {e}") from e
    else:
        bg.add_task(render_clip_edit_job, job_id, clip_id)
    return {"status": "rendering"}


@app.get("/jobs/{job_id}/clips/{clip_id}/render")
def get_render(job_id: str, clip_id: str) -> dict[str, Any]:
    from app import storage

    row = db.get_clip_edit_row(job_id, clip_id)
    if row is None:
        raise HTTPException(status_code=404, detail="clip not found")
    url = row.get("render_url")
    # D6: долговечный маркер ключа r2://<key> → СВЕЖИЙ presign на чтении (не протухает);
    # абсолютный http (R2 CDN/presigned) — как есть; относительный → воркер-раздача /media.
    if url:
        url = str(url)
        if storage.is_r2_key_ref(url):
            url = storage.resolve_media_url(url)
        elif not url.startswith("http"):
            url = f"media/{job_id}/{url}"
        # Cache-bust the stable CDN URL by the edit version so a RE-render (same R2 key,
        # overwritten) isn't served stale from Cloudflare's edge cache → the new hook size /
        # caption edits actually reach the download. No-op for relative/local URLs.
        url = storage.with_cache_bust(url, row.get("version"))
    return {
        "status": row.get("render_status"),
        "video_url": url or None,
        "error": row.get("render_error"),
    }


@app.get("/jobs/{job_id}/clips/{clip_id}/reframe")
def get_clip_reframe(job_id: str, clip_id: str) -> dict[str, Any]:
    """Reframe-план клипа (fit/fill/split + центры) для честного превью кадра в редакторе.

    D2: раньше фронт тянул ``media/<job>/reframe_<clip>.json`` напрямую со StaticFiles —
    на облаке (Modal/R2) этот файл лежит только на scratch-диске batch-контейнера → 404 →
    превью откатывалось в центр-кроп (≠ рендер). Теперь план считает ЕДИНЫЙ frame-accurate
    путь ``resolve_regions_accurate`` (тот же, что у рендера; кэш ``analysis/acc_*.json``,
    источник из R2 через artifacts.ensure_source) для ТЕКУЩИХ интервалов edit-state →
    превью-план == рендер-план, и в обоих средах, и после сдвига/трима интервала.
    """
    from app import artifacts
    from app.editor.reframe_cache import (
        build_persist_payload,
        intervals_match_default,
        regions_from_persisted,
        regions_to_clip_time,
        resolve_regions_accurate,
    )

    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e

    # ── Домен 1: FAST-PATH — реальные границы шотов из persist (без CV, без скачивания source) ──
    # batch-пайплайн уже посчитал PySceneDetect-границы дефолтного интервала и сохранил их. Если
    # клип НЕ тримили/не сдвигали (один интервал == дефолт), отдаём их МГНОВЕННО (+ перекрас под
    # ручные override'ы). Это и есть фикс «полоса шотов = равные чанки»: на холодном контейнере
    # /reframe больше не гоняет тяжёлый CV (который тормозил/падал 500) для нетронутого клипа.
    persisted = db.get_reframe_regions(job_id, clip_id)
    if persisted and intervals_match_default(
        edit.source_intervals, persisted.get("default_start", -1), persisted.get("default_end", -1)
    ):
        iv = edit.source_intervals[0]
        return {"regions": regions_from_persisted(persisted, iv, edit.reframe_overrides)}

    out = artifacts.ensure_source(job_id).parent
    meta = artifacts.load_meta(job_id)
    s = get_settings()
    try:
        region_lists = resolve_regions_accurate(
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
            split_enabled=s.reframe_split_enabled,
            # WYSIWYG: тот же гибрид-порог, что у рендера/батча (render_edit_to_file его передаёт).
            # Без него превью бралось дефолтом resolve_regions_accurate (0.3) ≠ настройке → широкий
            # план в гриде показан горизонтально (fit), а в редакторе-превью — кропом (fill).
            wide_speak_min=s.reframe_wide_speak_min,
        )
    except Exception as e:  # noqa: BLE001 — тяжёлый CV мог упасть/таймаутнуть на холодном
        # Явная ошибка вместо непрозрачного 500 (правило №8): фронт отличит «не смогли посчитать»
        # от «считается». Без тихого фолбэка — состояние видно.
        raise HTTPException(
            status_code=503, detail="reframe analysis unavailable (try again shortly)"
        ) from e

    # Backfill (старые джобы до миграции): только что посчитали реальные регионы on-demand →
    # сохраним, чтобы следующий (холодный) контейнер взял fast-path. ЖЁСТКИЕ условия безопасности:
    #   • persisted is None — НИКОГДА не перетираем канонический batch-entry (или чужой shift);
    #   • без reframe_overrides — region_lists ЧИСТЫЕ авто-регионы (fast-path наложит override сам);
    #   • один интервал — payload хранит ровно один дефолтный интервал.
    if persisted is None and not edit.reframe_overrides and len(region_lists) == 1:
        iv = edit.source_intervals[0]
        try:
            db.put_reframe_regions(
                job_id,
                clip_id,
                build_persist_payload(region_lists[0], iv.source_start, iv.source_end),
            )
        except Exception as e:  # noqa: BLE001 — backfill best-effort, ответ важнее
            print(
                f"[get_clip_reframe] WARN backfill persist failed job={job_id} clip={clip_id}: {e}"
            )

    return {"regions": regions_to_clip_time(region_lists, edit.source_intervals)}


@app.get("/jobs/{job_id}/clips/{clip_id}/analysis")
def get_analysis(job_id: str, clip_id: str) -> dict[str, Any]:
    """Интервалы + слова клипа (для клиент-превью субтитров/таймлайна)."""
    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError, JobError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    words = store.load_transcript_words(job_id)
    in_clip = [
        w.model_dump()
        for w in words
        if any(iv.source_start <= w.start < iv.source_end for iv in edit.source_intervals)
    ]
    return {"intervals": [iv.model_dump() for iv in edit.source_intervals], "words": in_clip}


# ──────────────────────────── Preset endpoints ────────────────────────────


class SavePresetBody(BaseModel):
    name: str
    style: CaptionStyle
    highlight: HighlightStyle | None = None


class ApplyPresetBody(BaseModel):
    version: int
    preset_id: str


@app.get("/presets")
def get_presets() -> list[dict[str, Any]]:
    return [p.model_dump() for p in presets_mod.list_presets()]


@app.post("/presets")
def create_preset(body: SavePresetBody) -> dict[str, Any]:
    preset = CaptionPreset(
        id=f"preset_{uuid.uuid4().hex[:8]}",
        name=body.name,
        style=body.style,
        highlight=body.highlight,
    )
    return presets_mod.save_preset(preset).model_dump()


@app.post("/jobs/{job_id}/clips/{clip_id}/apply-preset")
def apply_preset_to_clip(job_id: str, clip_id: str, body: ApplyPresetBody) -> dict[str, Any]:
    preset = presets_mod.get_preset(body.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="preset not found")
    edit = _load_or_404(job_id, clip_id)
    return _save_or_409(job_id, clip_id, presets_mod.apply_preset(edit, preset), body.version)


# ──────────────────────── Style memory (domain 5) ────────────────────────


class StylePrefBody(BaseModel):
    """Saved/applied LOOK = caption style + karaoke highlight + hook style fields (partial dict)."""

    style: CaptionStyle
    highlight: HighlightStyle | None = None
    hook_style: dict[str, Any] | None = None


@app.post("/jobs/{job_id}/apply-style-all")
def apply_style_all(
    job_id: str,
    body: StylePrefBody,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Apply ONE clip's look (caption style + highlight + hook style) to EVERY clip of the job.

    Per-clip content & position are preserved (replies, intervals, reframe, margins, hook text).
    Owner-only. Returns how many clips were updated.
    """
    user_id = _resolve_user(authorization, x_user_id)
    row = db.get_job_row(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    # Owner-only массовая мутация — fail-CLOSED: при включённом auth правим ВСЕ клипы джобы
    # ТОЛЬКО владельцу. _resolve_user уже бросает 401 без валидного токена; здесь deny, если
    # владелец джобы не совпадает с юзером — ВКЛЮЧАЯ owner=None (ничья/legacy-джоба не
    # принадлежит никому → массово править нельзя, иначе IDOR). В dev (auth off) — пропускаем.
    owner = row.get("user_id") or None
    if auth.supabase_auth_enabled() and owner != user_id:
        raise HTTPException(status_code=403, detail="not your job")
    job = db.get_job(job_id) or {}
    clip_ids = [c["id"] for c in (job.get("clips") or []) if c.get("id")]
    applied = 0
    for clip_id in clip_ids:
        # ensure_edit so a not-yet-opened clip also gets the look (lazy default created first).
        try:
            edit = store.ensure_edit(job_id, clip_id)
        except (FileNotFoundError, KeyError, JobError):
            continue  # clip without a segment artifact → skip (explicit, not silent fallback)
        styled = style_prefs.apply_style_to_edit(edit, body.style, body.highlight, body.hook_style)
        try:
            store.save_edit(job_id, clip_id, styled, expected_version=edit.version)
        except EditConflict:
            # Concurrent edit on this clip → refetch once and reapply on the fresh version.
            fresh = store.load_edit(job_id, clip_id)
            if fresh is None:
                continue
            store.save_edit(
                job_id,
                clip_id,
                style_prefs.apply_style_to_edit(fresh, body.style, body.highlight, body.hook_style),
                expected_version=fresh.version,
            )
        applied += 1
    return {"applied": applied, "total": len(clip_ids)}


@app.get("/me/style-preference")
def get_my_style_preference(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """The user's saved default look (or null). New clips of future jobs seed from this."""
    user_id = _resolve_user(authorization, x_user_id)
    if not user_id:
        return {"preference": None}
    return {"preference": db.get_style_preference(user_id)}


@app.put("/me/style-preference")
def put_my_style_preference(
    body: StylePrefBody,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Save the current look as the user's default → future videos start from it (not preset_a)."""
    user_id = _resolve_user(authorization, x_user_id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to save a default style")
    blob: dict[str, Any] = {
        "style": body.style.model_dump(),
        "highlight": body.highlight.model_dump() if body.highlight is not None else None,
        "hook_style": body.hook_style,
    }
    db.set_style_preference(user_id, blob)
    return {"ok": True}
