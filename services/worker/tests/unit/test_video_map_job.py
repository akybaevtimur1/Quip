"""Job + dual-mode storage tests for VideoMap (Task D1.5).

Covers: save_video_map → load_video_map disk round-trip, generate_video_map_job writes a
loadable done artifact (Gemini monkeypatched), and the failure path saves status=failed.
No real Gemini / cloud — local-disk mode only (cs.cloud_enabled() is False without env).

Run (from services/worker with PATH refresh):
    uv run pytest tests/unit/test_video_map_job.py -q
"""

from __future__ import annotations

import json

from app import db, tasks
from app.editor import store
from app.editor import video_map as vmmod
from app.models import (
    Segment,
    SourceKind,
    Transcript,
    VideoChapter,
    VideoMap,
    Word,
)
from app.pipeline.stage0_import import SourceMeta


def _setup(monkeypatch, tmp_path) -> str:
    """tmp DATA_ROOT + SQLite, with transcript/segments/meta on disk for one job."""
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobVM"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    (d / "segments.json").write_text(
        json.dumps([Segment(start=0.0, end=50.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    words = [Word(text=f"w{i}", start=float(i), end=float(i) + 0.8) for i in range(60)]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=120.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    (d / "meta.json").write_text(
        SourceMeta(
            job_id=job, source=SourceKind.upload, url=None, title="t",
            duration=120.0, fps=30.0, width=1920, height=1080,
        ).model_dump_json(),
        encoding="utf-8",
    )  # fmt: skip
    return job


def test_save_load_round_trips_on_disk(monkeypatch, tmp_path) -> None:
    job = _setup(monkeypatch, tmp_path)
    vm = VideoMap(
        status="done",
        narrative="overview",
        chapters=[VideoChapter(start=0.0, end=50.0, title="T", summary="S")],
    )
    vmmod.save_video_map(job, vm)
    # file written
    assert (tmp_path / "data" / job / "video_map.json").exists()
    loaded = vmmod.load_video_map(job)
    assert loaded is not None
    assert loaded.status == "done"
    assert loaded.narrative == "overview"
    assert len(loaded.chapters) == 1
    assert loaded.chapters[0].title == "T"


def test_load_missing_returns_none(monkeypatch, tmp_path) -> None:
    job = _setup(monkeypatch, tmp_path)
    assert vmmod.load_video_map(job) is None


def test_job_writes_loadable_done_artifact(monkeypatch, tmp_path) -> None:
    job = _setup(monkeypatch, tmp_path)
    fake = VideoMap(
        status="done",
        narrative="n",
        chapters=[VideoChapter(start=0.0, end=50.0, title="C", summary="s")],
    )
    monkeypatch.setattr(vmmod, "generate_video_map", lambda *a, **k: fake)
    tasks.generate_video_map_job(job)
    loaded = vmmod.load_video_map(job)
    assert loaded is not None
    assert loaded.status == "done"
    assert loaded.chapters[0].title == "C"


def test_job_empty_chapters_saves_failed(monkeypatch, tmp_path) -> None:
    job = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        vmmod, "generate_video_map", lambda *a, **k: VideoMap(status="done", chapters=[])
    )
    tasks.generate_video_map_job(job)
    loaded = vmmod.load_video_map(job)
    assert loaded is not None
    assert loaded.status == "failed"
    assert loaded.error


def test_job_exception_saves_failed(monkeypatch, tmp_path) -> None:
    job = _setup(monkeypatch, tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(vmmod, "generate_video_map", _boom)
    tasks.generate_video_map_job(job)
    loaded = vmmod.load_video_map(job)
    assert loaded is not None
    assert loaded.status == "failed"
    assert "gemini down" in (loaded.error or "")
