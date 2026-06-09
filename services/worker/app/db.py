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

from app.models import Job

_DB_PATH = Path(__file__).resolve().parents[1] / "tmp" / "jobs.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
