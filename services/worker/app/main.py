"""FastAPI-входная точка воркера ClipFlow (этап J).

POST /jobs → создать задачу (BackgroundTask → tasks.run_pipeline_job), GET /jobs/{id} →
статус из SQLite (переживает рестарт), GET /healthz. Файлы клипов раздаются на /media.
CORS открыт для web (localhost:3000). Логика пайплайна — в app/pipeline/*, сюда не течёт.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import __version__, db
from app.run import DATA_ROOT
from app.tasks import run_pipeline_job


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    yield


app = FastAPI(title="clipflow-worker", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздача артефактов: data/<job_id>/clips/<clip>.mp4 → /media/<job_id>/clips/<clip>.mp4
DATA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(DATA_ROOT)), name="media")


class CreateJobBody(BaseModel):
    source_type: str
    source_ref: str


@app.get("/healthz")
def healthz() -> dict[str, bool | str]:
    """Liveness-проба. Выход: ``{"ok": True, "version": "..."}``. Без auth."""
    return {"ok": True, "version": __version__}


@app.post("/jobs", status_code=202)
def create_job(body: CreateJobBody, bg: BackgroundTasks) -> dict[str, Any]:
    """Создать задачу: запись queued в БД + фоновый прогон пайплайна. Возвращает id/статус."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    db.insert_job(job_id, body.source_type, body.source_ref)
    bg.add_task(run_pipeline_job, job_id, body.source_type, body.source_ref)
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Статус задачи (wire-Job) из SQLite. 404, если задачи нет."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
