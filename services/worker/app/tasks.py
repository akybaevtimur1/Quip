"""Оркестрация run_pipeline в фоне + статус в SQLite (план §4А F: склейка).

Единственное место склейки для REST-пути: ловит JobError/любое исключение → статус failed
(правило №8), на успехе — set_done. Логика стадий не дублируется (живёт в run_pipeline).
"""

from __future__ import annotations

from app import db
from app.errors import JobError
from app.models import JobStatus
from app.run import run_pipeline


def run_pipeline_job(job_id: str, source_type: str, source_ref: str) -> None:
    def on_status(status: JobStatus, progress: int) -> None:
        db.update_status(job_id, status.value, progress)

    try:
        job = run_pipeline(job_id, source_url=source_ref, on_status=on_status)
        db.set_done(job_id, job)
    except JobError as e:
        db.set_failed(job_id, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        db.set_failed(job_id, f"unexpected: {e}")
