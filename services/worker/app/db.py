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
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT, stage TEXT, progress INTEGER,
                source_type TEXT, source_ref TEXT, error TEXT,
                clips_json TEXT, cost_usd REAL, duration_sec REAL, elapsed_sec REAL,
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


def insert_job(job_id: str, source_type: str, source_ref: str) -> None:
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO jobs"
            " (id,status,stage,progress,source_type,source_ref,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (job_id, "queued", "queued", 0, source_type, source_ref, now, now),
        )


def update_status(job_id: str, status: str, progress: int) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status=?, stage=?, progress=?, updated_at=? WHERE id=?",
            (status, status, progress, time.time(), job_id),
        )


def set_done(job_id: str, job: Job) -> None:
    clips_json = json.dumps([c.model_dump() for c in job.clips], ensure_ascii=False)
    m = job.metrics
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
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='failed', stage='failed', error=?, updated_at=? WHERE id=?",
            (error, time.time(), job_id),
        )


def row_to_wire(row: dict[str, Any]) -> dict[str, Any]:
    """Строка БД → wire-Job (dict). video_url клипов → путь, раздаваемый воркером (/media)."""
    clips: list[dict[str, Any]] = json.loads(row["clips_json"]) if row.get("clips_json") else []
    for c in clips:
        c["video_url"] = f"media/{row['id']}/{c['video_url']}"
    metrics = None
    if row.get("status") == "done":
        metrics = {
            "cost_usd": row.get("cost_usd") or 0.0,
            "duration_sec": row.get("duration_sec") or 0.0,
            "elapsed_sec": row.get("elapsed_sec") or 0.0,
        }
    return {
        "id": row["id"],
        "status": row["status"],
        "stage": row["stage"],
        "progress": row["progress"] or 0,
        "source_kind": "youtube",
        "error": row.get("error"),
        "clips": clips,
        "metrics": metrics,
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return row_to_wire(dict(row)) if row is not None else None


def get_clip_edit_row(job_id: str, clip_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM clip_edits WHERE job_id=? AND clip_id=?", (job_id, clip_id)
        ).fetchone()
    return dict(row) if row is not None else None


def put_clip_edit(job_id: str, clip_id: str, edit_json: str, version: int) -> None:
    now = time.time()
    with _conn() as c:
        exists = c.execute(
            "SELECT 1 FROM clip_edits WHERE job_id=? AND clip_id=?", (job_id, clip_id)
        ).fetchone()
        if exists:
            c.execute(
                "UPDATE clip_edits SET edit_json=?, version=?, updated_at=?"
                " WHERE job_id=? AND clip_id=?",
                (edit_json, version, now, job_id, clip_id),
            )
        else:
            c.execute(
                "INSERT INTO clip_edits (job_id,clip_id,version,edit_json,updated_at)"
                " VALUES (?,?,?,?,?)",
                (job_id, clip_id, version, edit_json, now),
            )


def set_render_status(
    job_id: str, clip_id: str, status: str, url: str | None, error: str | None
) -> None:
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
) -> None:
    """Записать расход одного обработанного видео (минуты + кредиты) в месячное окно.

    ``credits`` по умолчанию выводится из длины (``credits_per_video``); вызывающий
    может передать фактически списанное (месячный+PAYG) число для точного учёта.
    """
    n = credits if credits is not None else credits_per_video(source_minutes)
    if supa.supa_enabled():
        supa.record_usage(user_id, job_id, source_minutes, month, int(n))
        return
    with _conn() as c:
        c.execute(
            "INSERT INTO usage_events (user_id, job_id, source_minutes, credits, month, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (user_id, job_id, source_minutes, int(n), month, time.time()),
        )


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
