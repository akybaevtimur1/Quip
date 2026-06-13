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


def test_cloud_row_passes_through_absolute_r2_url_and_reads_clips_list() -> None:
    # Облачная строка (Postgres): clips — jsonb-список; video_url — полный R2-URL → отдаём как есть.
    r2 = "https://pub-x.r2.dev/job_z/clip_01.mp4"
    row = {
        "id": "job_z",
        "status": "done",
        "stage": "done",
        "progress": 100,
        "error": None,
        "clips": [{"id": "clip_01", "video_url": r2}],
        "cost_usd": 0.16,
        "duration_sec": 120.0,
        "elapsed_sec": 30.0,
    }
    wire = row_to_wire(row)
    assert wire["clips"][0]["video_url"] == r2  # без media/-префикса
    assert wire["metrics"] == {"cost_usd": 0.16, "duration_sec": 120.0, "elapsed_sec": 30.0}


# ─────────────────────────── T6: usage-адаптер (SQLite-режим) ───────────────────────────


def test_record_and_aggregate_monthly_usage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "u.db")
    db.init_db()
    db.record_usage("user_1", "job_a", 10.0, "2026-06")  # 1 кредит
    db.record_usage("user_1", "job_b", 90.0, "2026-06")  # 90 мин → 2 кредита
    db.record_usage("user_1", "job_c", 5.0, "2026-07")  # другой месяц — не считается
    db.record_usage("user_2", "job_d", 99.0, "2026-06")  # другой юзер — не считается

    june = db.get_monthly_usage("user_1", "2026-06")
    assert june == {"videos": 2, "minutes": 100.0, "credits": 3}


def test_monthly_usage_empty_is_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "u.db")
    db.init_db()
    assert db.get_monthly_usage("nobody", "2026-06") == {"videos": 0, "minutes": 0.0, "credits": 0}
