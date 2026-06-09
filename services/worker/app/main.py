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
from pydantic import BaseModel, Field

from app import __version__, db
from app.editor import store
from app.editor.ops import add_section, apply_extend, apply_trim, set_crop_override
from app.editor.store import EditConflict
from app.models import CaptionTrack, CropOverride
from app.run import DATA_ROOT
from app.tasks import render_clip_edit_job, run_pipeline_job


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
    max_clips: int | None = Field(default=None, ge=1, le=10)  # UI-степпер; None → дефолт воркера


@app.get("/healthz")
def healthz() -> dict[str, bool | str]:
    """Liveness-проба. Выход: ``{"ok": True, "version": "..."}``. Без auth."""
    return {"ok": True, "version": __version__}


@app.post("/jobs", status_code=202)
def create_job(body: CreateJobBody, bg: BackgroundTasks) -> dict[str, Any]:
    """Создать задачу: запись queued в БД + фоновый прогон пайплайна. Возвращает id/статус."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    db.insert_job(job_id, body.source_type, body.source_ref)
    bg.add_task(run_pipeline_job, job_id, body.source_type, body.source_ref, body.max_clips)
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Статус задачи (wire-Job) из SQLite. 404, если задачи нет."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


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
    mode: str  # "fill" | "fit"
    center: float | None = None


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


@app.get("/jobs/{job_id}/clips/{clip_id}/edit")
def get_clip_edit(job_id: str, clip_id: str) -> dict[str, Any]:
    """ClipEdit клипа (создаёт дефолт из сегмента при первом обращении)."""
    try:
        return store.ensure_edit(job_id, clip_id).model_dump()
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e


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
    return _save_or_409(job_id, clip_id, apply_trim(edit, body.word_indices, words), body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/add-section")
def op_add_section(job_id: str, clip_id: str, body: AddSectionBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = add_section(edit, body.source_start, body.source_end, body.at_index, words)
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/extend")
def op_extend(job_id: str, clip_id: str, body: ExtendBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    new = apply_extend(edit, edge=body.edge, new_value=body.new_value, words=words)
    return _save_or_409(job_id, clip_id, new, body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/crop")
def op_crop(job_id: str, clip_id: str, body: CropBody) -> dict[str, Any]:
    edit = _load_or_404(job_id, clip_id)
    ov = CropOverride(
        source_start=body.source_start,
        source_end=body.source_end,
        mode=body.mode,
        center=body.center,
    )
    return _save_or_409(job_id, clip_id, set_crop_override(edit, ov), body.version)


@app.post("/jobs/{job_id}/clips/{clip_id}/render", status_code=202)
def post_render(job_id: str, clip_id: str, bg: BackgroundTasks) -> dict[str, Any]:
    """Async-рендер mp4 из edit-state. Статус — GET …/render."""
    _load_or_404(job_id, clip_id)
    db.set_render_status(job_id, clip_id, "rendering", None, None)
    bg.add_task(render_clip_edit_job, job_id, clip_id)
    return {"status": "rendering"}


@app.get("/jobs/{job_id}/clips/{clip_id}/render")
def get_render(job_id: str, clip_id: str) -> dict[str, Any]:
    row = db.get_clip_edit_row(job_id, clip_id)
    if row is None:
        raise HTTPException(status_code=404, detail="clip not found")
    url = row.get("render_url")
    return {
        "status": row.get("render_status"),
        "video_url": f"media/{job_id}/{url}" if url else None,
        "error": row.get("render_error"),
    }


@app.get("/jobs/{job_id}/clips/{clip_id}/analysis")
def get_analysis(job_id: str, clip_id: str) -> dict[str, Any]:
    """Интервалы + слова клипа (для клиент-превью субтитров/таймлайна)."""
    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    in_clip = [
        w.model_dump()
        for w in words
        if any(iv.source_start <= w.start < iv.source_end for iv in edit.source_intervals)
    ]
    return {"intervals": [iv.model_dump() for iv in edit.source_intervals], "words": in_clip}
