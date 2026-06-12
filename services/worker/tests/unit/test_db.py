"""Тесты pure-маппинга строки SQLite → wire-Job (app.db.row_to_wire) + usage-адаптер (T6)."""

import json

from app import db
from app.db import row_to_wire


def test_done_row_rewrites_video_url_and_has_metrics() -> None:
    clip = {
        "id": "clip_01",
        "start": 1.0,
        "end": 20.0,
        "duration": 19.0,
        "reason": "r",
        "type": "hook",
        "score": 0.9,
        "video_url": "clips/clip_01.mp4",
        "thumbnail_url": None,
        "transcript": "...",
        "words": [],
    }
    row = {
        "id": "job_abc",
        "status": "done",
        "stage": "done",
        "progress": 100,
        "error": None,
        "clips_json": json.dumps([clip]),
        "cost_usd": 0.16,
        "duration_sec": 1987.0,
        "elapsed_sec": 200.0,
    }
    wire = row_to_wire(row)
    assert wire["status"] == "done"
    # video_url переписан на путь, который раздаёт воркер (/media/<job_id>/...)
    assert wire["clips"][0]["video_url"] == "media/job_abc/clips/clip_01.mp4"
    assert wire["metrics"] == {"cost_usd": 0.16, "duration_sec": 1987.0, "elapsed_sec": 200.0}


def test_in_progress_row_has_empty_clips_and_no_metrics() -> None:
    row = {
        "id": "job_x",
        "status": "transcribing",
        "stage": "transcribing",
        "progress": 45,
        "error": None,
        "clips_json": None,
        "cost_usd": None,
        "duration_sec": None,
        "elapsed_sec": None,
    }
    wire = row_to_wire(row)
    assert wire["clips"] == []
    assert wire["metrics"] is None
    assert wire["progress"] == 45


def test_failed_row_carries_error() -> None:
    row = {
        "id": "job_y",
        "status": "failed",
        "stage": "failed",
        "progress": 0,
        "error": "[import] boom",
        "clips_json": None,
        "cost_usd": None,
        "duration_sec": None,
        "elapsed_sec": None,
    }
    wire = row_to_wire(row)
    assert wire["status"] == "failed"
    assert wire["error"] == "[import] boom"
    assert wire["metrics"] is None


# ─────────────────────────── T6: usage-адаптер (SQLite-режим) ───────────────────────────


def test_record_and_aggregate_monthly_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "u.db")
    db.init_db()
    db.record_usage("user_1", "job_a", 10.0, "2026-06")
    db.record_usage("user_1", "job_b", 33.0, "2026-06")
    db.record_usage("user_1", "job_c", 5.0, "2026-07")  # другой месяц — не считается
    db.record_usage("user_2", "job_d", 99.0, "2026-06")  # другой юзер — не считается

    june = db.get_monthly_usage("user_1", "2026-06")
    assert june == {"videos": 2, "minutes": 43.0}


def test_monthly_usage_empty_is_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "u.db")
    db.init_db()
    assert db.get_monthly_usage("nobody", "2026-06") == {"videos": 0, "minutes": 0.0}
