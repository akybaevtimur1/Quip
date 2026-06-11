"""Оркестрация run_pipeline в фоне + статус в SQLite (план §4А F: склейка).

Единственное место склейки для REST-пути: ловит JobError/любое исключение → статус failed
(правило №8), на успехе — set_done. Логика стадий не дублируется (живёт в run_pipeline).
"""

from __future__ import annotations

from app import db
from app.errors import JobError
from app.models import JobStatus
from app.run import run_pipeline


def render_clip_edit_job(job_id: str, clip_id: str) -> None:
    """Собрать mp4 из текущего ClipEdit (фон). Статус рендера → clip_edits (правило №8)."""
    from app.config import get_settings
    from app.editor import store
    from app.editor.reframe_cache import analyze_source_range, resolve_regions
    from app.pipeline.stage0_import import SourceMeta
    from app.pipeline.stage5_render import render_timeline
    from app.run import DATA_ROOT

    try:
        s = get_settings()
        out = DATA_ROOT / job_id
        edit = store.load_edit(job_id, clip_id)
        if edit is None:
            raise JobError("render", f"нет edit для {clip_id}")
        meta = SourceMeta.model_validate_json((out / "meta.json").read_text(encoding="utf-8"))
        analysis_dir = out / "analysis"
        raw = [
            analyze_source_range(
                out / "source.mp4",
                iv.source_start,
                iv.source_end,
                cache_dir=analysis_dir,
                fps=s.reframe_face_fps,
                cut_threshold=s.reframe_scene_threshold,
            )
            for iv in edit.source_intervals
        ]
        regions = resolve_regions(
            edit.source_intervals,
            raw,
            edit.reframe_overrides,
            src_w=meta.width,
            src_h=meta.height,
            smoothing=s.reframe_smoothing,
            min_hold_sec=s.reframe_min_hold_sec,
            mode_setting=s.reframe_mode,
            wide_ratio=s.reframe_wide_ratio,
        )
        render_timeline(
            out,
            "source.mp4",
            edit.source_intervals,
            regions,
            f"clips/{clip_id}.mp4",
            src_w=meta.width,
            src_h=meta.height,
            fps=meta.fps,
            engine=s.reframe_engine,
        )
        db.set_render_status(job_id, clip_id, "done", f"clips/{clip_id}.mp4", None)
    except JobError as e:
        db.set_render_status(job_id, clip_id, "failed", None, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed
        db.set_render_status(job_id, clip_id, "failed", None, f"unexpected: {e}")


def run_pipeline_job(
    job_id: str, source_type: str, source_ref: str, max_clips: int | None = None
) -> None:
    def on_status(status: JobStatus, progress: int) -> None:
        db.update_status(job_id, status.value, progress)

    try:
        job = run_pipeline(job_id, source_url=source_ref, on_status=on_status, max_clips=max_clips)
        db.set_done(job_id, job)
    except JobError as e:
        db.set_failed(job_id, str(e))
    except Exception as e:  # noqa: BLE001 — фон-таск: любое падение → статус failed, не молча
        db.set_failed(job_id, f"unexpected: {e}")
