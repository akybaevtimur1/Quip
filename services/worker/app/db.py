"""SQLite-хранилище задач (план J1). Переживает рестарт процесса.

Pure-маппинг строки → wire-Job изолирован (``row_to_wire``) и покрыт unit-тестами.
Запись/чтение — тонкие обёртки над sqlite3.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app import cloud_state as cs
from app import supa
from app.billing import credits_per_video
from app.models import Job

_DB_PATH = Path(__file__).resolve().parents[1] / "tmp" / "jobs.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(c: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    """Добавить колонку, если её ещё нет (миграция старых SQLite-БД). Идемпотентно."""
    cols = {row["name"] for row in c.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db() -> None:
    if cs.cloud_enabled():
        # Облачный режим (Modal): стейт в Supabase (схема накатана миграцией, не из кода).
        # Локальную SQLite не создаём — она не используется.
        return
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT, stage TEXT, progress INTEGER,
                source_type TEXT, source_ref TEXT, error TEXT,
                clips_json TEXT, cost_usd REAL, duration_sec REAL, elapsed_sec REAL,
                function_call_id TEXT, cancellable INTEGER NOT NULL DEFAULT 1,
                created_at REAL, updated_at REAL
            )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS clip_edits (
                job_id TEXT, clip_id TEXT, version INTEGER, edit_json TEXT,
                render_status TEXT, render_url TEXT, render_error TEXT, updated_at REAL,
                PRIMARY KEY (job_id, clip_id)
            )"""
        )
        # W3: агент-чат редактора. Один ряд = один прогон агента над клипом (лента событий jsonb).
        # Зеркало migrations/0007_agent_runs.sql (cloud). cancellable/function_call_id — Stop.
        c.execute(
            """CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY, job_id TEXT, clip_id TEXT, user_id TEXT,
                status TEXT NOT NULL, events_json TEXT NOT NULL DEFAULT '[]',
                error TEXT, function_call_id TEXT, cancellable INTEGER NOT NULL DEFAULT 1,
                created_at REAL, updated_at REAL
            )"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_clip ON agent_runs (job_id, clip_id)")
        # Кредит-модель: учёт расхода для лимитов (зеркало Postgres usage_events, см.
        # migrations/0001_init_billing.sql). 1 строка = 1 обработанное видео + его кредиты.
        c.execute(
            """CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL, job_id TEXT,
                source_minutes REAL NOT NULL, credits INTEGER NOT NULL DEFAULT 1,
                month TEXT NOT NULL, created_at REAL
            )"""
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_user_month ON usage_events (user_id, month)"
        )
        # Профиль: план + не сгорающий баланс PAYG-кредитов (зеркало Postgres profiles).
        # Пишет вебхук оплаты Polar (set_user_plan / add_payg_credits) через service-role;
        # гейт квоты читает get_profile.
        c.execute(
            """CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY, plan TEXT NOT NULL,
                payg_credits INTEGER NOT NULL DEFAULT 0, updated_at REAL
            )"""
        )
        # Миграция существующих БД (CREATE TABLE IF NOT EXISTS не добавляет колонки):
        # добавить новые поля, если их ещё нет. Идемпотентно.
        _ensure_column(c, "usage_events", "credits", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(c, "profiles", "payg_credits", "INTEGER NOT NULL DEFAULT 0")
        # Stop-кнопка (зеркало migrations/0006_job_cancel.sql): id Modal-функции + флаг отмены.
        _ensure_column(c, "jobs", "function_call_id", "TEXT")
        _ensure_column(c, "jobs", "cancellable", "INTEGER NOT NULL DEFAULT 1")


def insert_job(
    job_id: str, source_type: str, source_ref: str, *, user_id: str | None = None
) -> None:
    if cs.cloud_enabled():
        cs.insert_job(job_id, source_type, source_ref, user_id=user_id)
        return
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO jobs"
            " (id,status,stage,progress,source_type,source_ref,cancellable,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, "queued", "queued", 0, source_type, source_ref, 1, now, now),
        )


def update_status(job_id: str, status: str, progress: int) -> None:
    if cs.cloud_enabled():
        cs.update_status(job_id, status, progress)
        return
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status=?, stage=?, progress=?, updated_at=? WHERE id=?",
            (status, status, progress, time.time(), job_id),
        )


def set_done(job_id: str, job: Job) -> None:
    m = job.metrics
    if cs.cloud_enabled():
        cs.set_done(
            job_id,
            [c.model_dump() for c in job.clips],
            m.cost_usd if m else 0.0,
            m.duration_sec if m else 0.0,
            m.elapsed_sec if m else 0.0,
        )
        return
    clips_json = json.dumps([c.model_dump() for c in job.clips], ensure_ascii=False)
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='done', stage='done', progress=100, clips_json=?,"
            " cost_usd=?, duration_sec=?, elapsed_sec=?, updated_at=? WHERE id=?",
            (
                clips_json,
                m.cost_usd if m else 0.0,
                m.duration_sec if m else 0.0,
                m.elapsed_sec if m else 0.0,
                time.time(),
                job_id,
            ),
        )


def set_failed(job_id: str, error: str) -> None:
    if cs.cloud_enabled():
        cs.set_failed(job_id, error)
        return
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=? WHERE id=?",
            (error, time.time(), job_id),
        )


# ─────────────────────────── Stop-кнопка: отмена джоба ───────────────────────────


def set_function_call_id(job_id: str, fc_id: str | None) -> None:
    """Сохранить id запущенного Modal-``FunctionCall`` (для последующей отмены джоба).

    ``fc_id is None`` (local/dev, нет Modal) → no-op. Обновляет ТОЛЬКО эту колонку (+
    updated_at), не трогая status/cancellable.
    """
    if fc_id is None:
        return
    if cs.cloud_enabled():
        cs.set_function_call_id(job_id, fc_id)
        return
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET function_call_id=?, updated_at=? WHERE id=?",
            (fc_id, time.time(), job_id),
        )


def set_cancellable(job_id: str, value: bool) -> None:
    """Переключить флаг отмены (воркер гасит в False при входе в платную стадию)."""
    if cs.cloud_enabled():
        cs.set_cancellable(job_id, value)
        return
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET cancellable=?, updated_at=? WHERE id=?",
            (1 if value else 0, time.time(), job_id),
        )


def set_cancelled(job_id: str) -> None:
    """Пометить джоб отменённым (Stop-кнопка). Guard ``status NOT IN ('done','failed')`` —
    не перетираем уже завершённый джоб (гонка отмены с финишем пайплайна)."""
    if cs.cloud_enabled():
        cs.set_cancelled(job_id)
        return
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='cancelled', stage='cancelled', cancellable=0, updated_at=?"
            " WHERE id=? AND status NOT IN ('done','failed')",
            (time.time(), job_id),
        )


def get_job_row(job_id: str) -> dict[str, Any] | None:
    """СЫРАЯ строка джоба (incl. user_id, cancellable, status, function_call_id).

    Эндпоинт отмены нуждается в колонках, которые ``row_to_wire`` отбрасывает (owner-check,
    флаг отмены, id Modal-функции). Cloud-путь переиспользует ``cs.get_job_row`` (select=*).
    """
    if cs.cloud_enabled():
        return cs.get_job_row(job_id)
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row is not None else None


def row_to_wire(row: dict[str, Any]) -> dict[str, Any]:
    """Строка БД → wire-Job (dict).

    ``video_url`` клипов: абсолютный http (R2 CDN/presigned) ИЛИ долговечный маркер ключа
    ``r2://<key>`` (D6) — отдаём КАК ЕСТЬ (маркер ре-подписывает I/O-слой get_job на чтении);
    относительный (локальный SQLite, ``clips/clip_01.mp4``) префиксим воркер-раздачей
    ``media/<job>/...``. Так одна pure-функция обслуживает и облако, и локальный dev.
    Клипы приходят либо jsonb-списком (Postgres ``clips``), либо строкой (SQLite ``clips_json``).
    """
    raw = row.get("clips")
    if raw is None:
        raw = json.loads(row["clips_json"]) if row.get("clips_json") else []
    clips: list[dict[str, Any]] = list(raw)
    for c in clips:
        u = str(c.get("video_url") or "")
        if u and not u.startswith("http") and not u.startswith("r2://"):
            c["video_url"] = f"media/{row['id']}/{u}"
    metrics = None
    if row.get("status") == "done":
        metrics = {
            "cost_usd": float(row.get("cost_usd") or 0.0),
            "duration_sec": float(row.get("duration_sec") or 0.0),
            "elapsed_sec": float(row.get("elapsed_sec") or 0.0),
        }
    # D5: source_kind отражает реальный источник (upload-джоб ≠ youtube). Берём из строки
    # (insert_job пишет source_type); неизвестное/пустое → youtube (безопасный дефолт).
    source_kind = "upload" if row.get("source_type") == "upload" else "youtube"
    return {
        "id": row["id"],
        "status": row["status"],
        "stage": row["stage"],
        "progress": row["progress"] or 0,
        "source_kind": source_kind,
        "error": row.get("error"),
        "clips": clips,
        "metrics": metrics,
        # Stop-кнопка: defense-in-depth — report cancellable ТОЛЬКО во FREE-фазе (queued/
        # downloading), даже если строка ещё несёт cancellable=1 (status — финальная истина).
        "cancellable": bool(row.get("cancellable"))
        and row.get("status") in ("queued", "downloading"),
    }


def _resolve_clip_urls(wire: dict[str, Any]) -> dict[str, Any]:
    """D6: ре-подписать долговечные R2-маркеры клипов СВЕЖИМ presigned URL на чтении.

    I/O-обёртка над pure row_to_wire: маркер ``r2://<key>`` → живой presign (TTL не успевает
    протухнуть между минтом и отдачей). http/относительный — без изменений. Так клипы не
    отдают 403 спустя час/неделю (старый код пёк presigned URL в строку джоба намертво).
    """
    from app import storage

    for c in wire.get("clips") or []:
        u = str(c.get("video_url") or "")
        if storage.is_r2_key_ref(u):
            c["video_url"] = storage.resolve_media_url(u)
    return wire


def get_job(job_id: str) -> dict[str, Any] | None:
    if cs.cloud_enabled():
        row = cs.get_job_row(job_id)
        return _resolve_clip_urls(row_to_wire(row)) if row is not None else None
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _resolve_clip_urls(row_to_wire(dict(row))) if row is not None else None


# ── артефакты пайплайна (meta/segments/transcript) — durable для лёгкого API на Modal ──


def put_job_artifacts(
    job_id: str, meta: dict[str, Any], segments: list[Any], transcript: dict[str, Any]
) -> None:
    """Сохранить артефакты в Postgres (cloud). Локально — no-op: артефакты читаются с диска."""
    if cs.cloud_enabled():
        cs.put_job_artifacts(job_id, meta, segments, transcript)


def get_job_artifacts(job_id: str) -> dict[str, Any] | None:
    """Артефакты из Postgres (cloud) → {meta, segments, transcript}. Локально → None (диск)."""
    if cs.cloud_enabled():
        return cs.get_job_artifacts(job_id)
    return None


def put_job_artifact(job_id: str, key: str, value: Any) -> None:
    """Сохранить ОДИН jsonb-артефакт (напр. video_map) в Postgres-строку job_artifacts (cloud).

    Cross-container: video_map генерится в ОТДЕЛЬНОМ Modal-контейнере, а отдаётся web-контейнером
    /video-map → диск-only артефакт невидим. Эта колонка делает его durable между контейнерами.
    Локально — no-op (артефакт читается с диска)."""
    if cs.cloud_enabled():
        cs.put_job_artifact(job_id, key, value)


def get_job_artifact(job_id: str, key: str) -> Any:
    """Прочитать ОДИН jsonb-артефакт job_artifacts[key] из Postgres (cloud); локально → None."""
    if cs.cloud_enabled():
        return cs.get_job_artifact(job_id, key)
    return None


# ── content-addressed transcript-кэш (бережёт Deepgram между контейнерами) ──


def get_cached_transcript(audio_sha: str, provider: str, model: str) -> dict[str, Any] | None:
    if cs.cloud_enabled():
        return cs.get_cached_transcript(audio_sha, provider, model)
    return None


def put_cached_transcript(
    audio_sha: str, provider: str, model: str, transcript: dict[str, Any]
) -> None:
    if cs.cloud_enabled():
        cs.put_cached_transcript(audio_sha, provider, model, transcript)


# ── clip_edits (атомарный optimistic-lock) ──


def get_clip_edit_row(job_id: str, clip_id: str) -> dict[str, Any] | None:
    if cs.cloud_enabled():
        return cs.get_clip_edit_row(job_id, clip_id)
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM clip_edits WHERE job_id=? AND clip_id=?", (job_id, clip_id)
        ).fetchone()
    return dict(row) if row is not None else None


def insert_clip_edit(job_id: str, clip_id: str, edit: dict[str, Any], version: int) -> None:
    """Первичная вставка edit-state (version=1). On conflict do nothing."""
    if cs.cloud_enabled():
        cs.insert_clip_edit(job_id, clip_id, edit, version)
        return
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO clip_edits (job_id,clip_id,version,edit_json,updated_at)"
            " VALUES (?,?,?,?,?)",
            (job_id, clip_id, version, json.dumps(edit, ensure_ascii=False), time.time()),
        )


def update_clip_edit_if_version(
    job_id: str, clip_id: str, edit: dict[str, Any], *, expected_version: int, new_version: int
) -> bool:
    """Атомарный optimistic-lock: UPDATE ... WHERE version=expected. True если применилось."""
    if cs.cloud_enabled():
        return cs.update_clip_edit_if_version(
            job_id, clip_id, edit, expected_version=expected_version, new_version=new_version
        )
    with _conn() as c:
        cur = c.execute(
            "UPDATE clip_edits SET edit_json=?, version=?, updated_at=?"
            " WHERE job_id=? AND clip_id=? AND version=?",
            (
                json.dumps(edit, ensure_ascii=False),
                new_version,
                time.time(),
                job_id,
                clip_id,
                expected_version,
            ),
        )
        return cur.rowcount == 1


def set_render_status(
    job_id: str, clip_id: str, status: str, url: str | None, error: str | None
) -> None:
    if cs.cloud_enabled():
        cs.set_render_status(job_id, clip_id, status, url, error)
        return
    with _conn() as c:
        c.execute(
            "UPDATE clip_edits SET render_status=?, render_url=?, render_error=?, updated_at=?"
            " WHERE job_id=? AND clip_id=?",
            (status, url, error, time.time(), job_id, clip_id),
        )


# ─────────────────────────── T6: учёт расхода (usage) ───────────────────────────
# Адаптер усреднён под обе СУБД: тот же интерфейс на SQLite (локально) и Postgres
# (Supabase). На Supabase эти две функции = INSERT в usage_events / SELECT агрегат
# (через service-role, RLS обходится сервером). См. docs/SUPABASE_SETUP.md.


def record_usage(
    user_id: str,
    job_id: str | None,
    source_minutes: float,
    month: str,
    credits: int | None = None,
) -> bool:
    """Записать расход одного обработанного видео (минуты + кредиты) в месячное окно.

    ``credits`` по умолчанию выводится из длины (``credits_per_video``); вызывающий
    может передать фактически списанное (месячный+PAYG) число для точного учёта.

    Возвращает ``True``, если строка реально записана; ``False``, если по этому ``job_id``
    расход УЖЕ учтён (идемпотентность: ретрай/повторный прогон одного джоба не должен
    заряжать дважды). ``job_id is None`` (аноним) дедупом не покрыт → всегда ``True``.
    Вызыватель (``_meter``) списывает PAYG ТОЛЬКО при ``True`` → нет двойного списания.
    """
    n = credits if credits is not None else credits_per_video(source_minutes)
    if supa.supa_enabled():
        return supa.record_usage(user_id, job_id, source_minutes, month, int(n))
    with _conn() as c:
        if job_id is not None:
            seen = c.execute(
                "SELECT 1 FROM usage_events WHERE job_id=? LIMIT 1", (job_id,)
            ).fetchone()
            if seen is not None:
                return False
        c.execute(
            "INSERT INTO usage_events (user_id, job_id, source_minutes, credits, month, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, job_id, source_minutes, int(n), month, time.time()),
        )
    return True


def get_monthly_usage(user_id: str, month: str) -> dict[str, float]:
    """Месячный расход → {"videos", "minutes", "credits"} (credits = списано с месячного лимита)."""
    if supa.supa_enabled():
        return supa.get_monthly_usage(user_id, month)
    with _conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS videos, COALESCE(SUM(source_minutes), 0) AS minutes,"
            " COALESCE(SUM(credits), 0) AS credits"
            " FROM usage_events WHERE user_id=? AND month=?",
            (user_id, month),
        ).fetchone()
    return {
        "videos": int(row["videos"]),
        "minutes": float(row["minutes"]),
        "credits": int(row["credits"]),
    }


# ─────────────────── Профиль: план + баланс PAYG (profiles) ───────────────────
# Тот же интерфейс на SQLite (локально) и Postgres (Supabase profiles, service-role).


def set_user_plan(user_id: str, plan: str) -> None:
    """Установить план пользователя (вебхук подписки Polar → plan). Upsert (PAYG не трогаем)."""
    if supa.supa_enabled():
        supa.set_user_plan(user_id, plan)
        return
    with _conn() as c:
        c.execute(
            "INSERT INTO profiles (user_id, plan, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " plan=excluded.plan, updated_at=excluded.updated_at",
            (user_id, plan, time.time()),
        )


def add_payg_credits(user_id: str, credits: int) -> None:
    """Начислить не сгорающие PAYG-кредиты (вебхук разовой оплаты Polar). Upsert (+=)."""
    if supa.supa_enabled():
        supa.add_payg_credits(user_id, credits)
        return
    with _conn() as c:
        c.execute(
            "INSERT INTO profiles (user_id, plan, payg_credits, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " payg_credits=profiles.payg_credits+excluded.payg_credits,"
            " updated_at=excluded.updated_at",
            (user_id, "free", int(credits), time.time()),
        )


def deduct_payg(user_id: str, credits: int) -> None:
    """Списать ``credits`` PAYG-кредитов (PAYG-покрытая часть обработанного видео).

    Атомарно, с полом 0 — баланс НИКОГДА не уходит в минус (защита от двойного учёта/
    гонки/ошибки округления). ``credits<=0`` → no-op. Нет профиля → нечего списывать
    (UPDATE затрагивает 0 строк — НЕ создаём строку с отрицательным балансом, в отличие
    от add_payg_credits/upsert: «минус-кредиты» бессмысленны).
    """
    if credits <= 0:
        return
    if supa.supa_enabled():
        supa.deduct_payg(user_id, credits)
        return
    with _conn() as c:
        c.execute(
            "UPDATE profiles SET payg_credits=MAX(0, payg_credits-?), updated_at=? WHERE user_id=?",
            (int(credits), time.time(), user_id),
        )


def get_user_plan(user_id: str) -> str:
    """План пользователя для гейта квоты. Нет записи → "free" (безопасный дефолт)."""
    if supa.supa_enabled():
        return supa.get_user_plan(user_id)
    with _conn() as c:
        row = c.execute("SELECT plan FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    return str(row["plan"]) if row is not None else "free"


def get_profile(user_id: str) -> dict[str, Any]:
    """Профиль для гейта квоты → {"plan", "payg_credits"}. Нет записи → free / 0."""
    if supa.supa_enabled():
        return supa.get_profile(user_id)
    with _conn() as c:
        row = c.execute(
            "SELECT plan, payg_credits FROM profiles WHERE user_id=?", (user_id,)
        ).fetchone()
    if row is None:
        return {"plan": "free", "payg_credits": 0}
    return {"plan": str(row["plan"]), "payg_credits": int(row["payg_credits"])}
