"""FastAPI-входная точка воркера ClipFlow (этап J).

POST /jobs → создать задачу (BackgroundTask → tasks.run_pipeline_job), GET /jobs/{id} →
статус из SQLite (переживает рестарт), GET /healthz. Файлы клипов раздаются на /media.
CORS открыт для web (localhost:3000). Логика пайплайна — в app/pipeline/*, сюда не течёт.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__, db
from app.config import get_settings
from app.editor import presets as presets_mod
from app.editor import store
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
    CaptionPreset,
    CaptionStyle,
    CaptionTrack,
    CropOverride,
    HighlightStyle,
    Segment,
)
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


@app.post("/jobs/upload", status_code=202)
async def create_upload_job(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    max_clips: int | None = Form(default=None, ge=1, le=10),
) -> dict[str, Any]:
    """Создать задачу из ЗАГРУЖЕННОГО файла: стримим на диск → фон-импорт → пайплайн.

    Файл пишется чанками в data/<job_id>/upload.<ext> (не держим в памяти); затем
    run_upload_job готовит source.mp4/wav/meta и гоняет тот же пайплайн, что и URL-путь.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    out = DATA_ROOT / job_id
    out.mkdir(parents=True, exist_ok=True)
    filename = file.filename or "upload.mp4"
    suffix = Path(filename).suffix.lower() or ".mp4"
    upload_path = out / f"upload{suffix}"
    with upload_path.open("wb") as fh:
        while chunk := await file.read(_UPLOAD_CHUNK):
            fh.write(chunk)
    db.insert_job(job_id, "upload", filename)
    bg.add_task(run_upload_job, job_id, str(upload_path), filename, max_clips)
    return {"id": job_id, "status": "queued", "stage": "queued", "progress": 0}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    """Статус задачи (wire-Job) из SQLite. 404, если задачи нет."""
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{job_id}/timeline")
def get_timeline(job_id: str) -> dict[str, Any]:
    """TimelineData: длительность источника + ВСЕ кандидаты ИИ + слова (для таймлайн-редактора).

    Собирается из готовых meta.json + segments.json + transcript.json. Дорогих ИИ-вызовов НЕТ.
    404, если артефактов нет (как /analysis).
    """
    import json

    from app.pipeline.stage0_import import SourceMeta

    out = store.data_root() / job_id
    meta_path = out / "meta.json"
    segs_path = out / "segments.json"
    if not meta_path.exists() or not segs_path.exists():
        raise HTTPException(status_code=404, detail="timeline data not found")
    meta = SourceMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    segments = [Segment.model_validate(s) for s in json.loads(segs_path.read_text("utf-8"))]
    words = store.load_transcript_words(job_id)
    return build_timeline_data(meta.duration, segments, words).model_dump()


@app.get("/jobs/{job_id}/chapters")
def get_chapters(job_id: str, bg: BackgroundTasks) -> dict[str, Any]:
    """AI-карта видео (главы с описаниями). Кэш data/<job>/chapters.json.

    Файла нет → пишем pending + стартуем фон-генерацию (Gemini, ~$0.01-0.03,
    платится один раз); фронт поллит до done/failed. 404 — нет транскрипта.
    Повторный GET при pending вторую генерацию НЕ стартует.
    """
    from app import tasks as tasks_mod
    from app.editor.chapters import load_chapters, save_chapters
    from app.models import ChaptersData

    out = store.data_root() / job_id
    if not (out / "transcript.json").exists():
        raise HTTPException(status_code=404, detail="transcript not found")
    cached = load_chapters(out)
    if cached is not None:
        return cached.model_dump()
    pending = ChaptersData(status="pending")
    save_chapters(out, pending)
    bg.add_task(tasks_mod.generate_chapters_job, job_id)
    return pending.model_dump()


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


@app.get("/jobs/{job_id}/clips/{clip_id}/ass")
def get_clip_ass(job_id: str, clip_id: str) -> Response:
    """ASS субтитров текущего edit-state (для libass-превью в браузере).

    Тот же компилятор, что и финальный экспорт (captions_v2.compile_ass) → превью
    субтитров через libass.wasm = экспорт пиксель-в-пиксель. Тайминги в КЛИП-времени.
    """
    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError) as e:
        raise HTTPException(status_code=404, detail="clip/segment not found") from e
    words = store.load_transcript_words(job_id)
    cmap = ClipTimeMap(edit.source_intervals)
    ass = compile_ass(edit.captions, words, cmap)
    return Response(content=ass, media_type="text/plain; charset=utf-8")


@app.get("/jobs/{job_id}/clips/{clip_id}/export.srt")
def export_clip_srt(job_id: str, clip_id: str) -> Response:
    """SRT субтитров текущего edit-state (экспорт-свобода: унести в любой редактор).

    compile_srt зеркалит compile_ass (те же реплики/тайминги) → скачанный SRT
    совпадает с прожжённым видео. Content-Disposition: attachment → браузер скачивает.
    """
    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError) as e:
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
    except (FileNotFoundError, KeyError) as e:
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


@app.post("/jobs/{job_id}/clips/{clip_id}/edit/set-interval")
def op_set_interval(job_id: str, clip_id: str, body: SetIntervalBody) -> dict[str, Any]:
    """Заменить первичный интервал клипа окном [start,end] (двигать/resize на таймлайне).

    Границы клампятся в [0,duration] и в [clip_min_sec, clip_max_sec] (set_interval, PURE).
    Optimistic-lock (409 при version mismatch).
    """
    from app.pipeline.stage0_import import SourceMeta

    edit = _load_or_404(job_id, clip_id)
    words = store.load_transcript_words(job_id)
    meta = SourceMeta.model_validate_json(
        (store.data_root() / job_id / "meta.json").read_text(encoding="utf-8")
    )
    s = get_settings()
    new = set_interval(
        edit,
        body.source_start,
        body.source_end,
        words,
        duration=meta.duration,
        min_sec=s.clip_min_sec,
        max_sec=s.clip_max_sec,
    )
    return _save_or_409(job_id, clip_id, new, body.version)


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
    try:
        edit = store.ensure_edit(job_id, clip_id)
    except (FileNotFoundError, KeyError) as e:
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
