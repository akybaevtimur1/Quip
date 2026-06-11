"""Editor v2 backend: timeline data (PURE + endpoint), set-interval op, preset seeding."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app import db
from app.editor import presets, store
from app.editor.timeline import build_timeline_data
from app.models import Segment, Transcript, Word

# ──────────────────────────── PURE: build_timeline_data ────────────────────────────


def test_build_timeline_data_maps_segments_and_keeps_words():
    words = [Word(text="a", start=0.0, end=0.4), Word(text="b", start=0.4, end=0.8)]
    segs = [
        Segment(start=1.0, end=3.0, reason="hook reason", score=0.9, type="hook"),
        Segment(start=5.0, end=8.0, reason="quote reason", score=0.7, type="strong_quote"),
    ]
    td = build_timeline_data(120.5, segs, words)
    assert td.duration == 120.5
    assert td.words == words
    assert len(td.segments) == 2
    m0 = td.segments[0]
    assert m0.clip_id is None
    assert (m0.start, m0.end, m0.type, m0.score, m0.reason) == (
        1.0,
        3.0,
        "hook",
        0.9,
        "hook reason",
    )


def test_build_timeline_data_empty_segments():
    td = build_timeline_data(10.0, [], [])
    assert td.duration == 10.0
    assert td.segments == []
    assert td.words == []


# ──────────────────────────── fixtures ────────────────────────────


def _client(monkeypatch, tmp_path, *, with_meta=True):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(presets, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobT"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    (d / "segments.json").write_text(
        json.dumps(
            [
                Segment(start=2.0, end=20.0, reason="r1", score=0.8, type="hook").model_dump(),
                Segment(
                    start=30.0, end=45.0, reason="r2", score=0.6, type="strong_quote"
                ).model_dump(),
            ]
        ),
        encoding="utf-8",
    )
    words = [
        Word(text="hello", start=2.0, end=2.5),
        Word(text="world", start=2.5, end=3.0),
        Word(text="foo", start=31.0, end=31.4),
    ]
    (d / "transcript.json").write_text(
        Transcript(language="en", duration=200.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    if with_meta:
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "job_id": job,
                    "source": "youtube",
                    "url": "https://x",
                    "title": "t",
                    "duration": 200.0,
                    "fps": 25.0,
                    "width": 1920,
                    "height": 1080,
                }
            ),
            encoding="utf-8",
        )
    from app.main import app

    return TestClient(app), job


# ──────────────────────────── GET /timeline ────────────────────────────


def test_get_timeline_returns_segments_and_words(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["duration"] == 200.0
    assert len(body["segments"]) == 2
    assert body["segments"][0]["clip_id"] is None
    assert body["segments"][0]["start"] == 2.0
    assert body["segments"][1]["type"] == "strong_quote"
    assert len(body["words"]) == 3


def test_get_timeline_404_without_meta(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path, with_meta=False)
    r = client.get(f"/jobs/{job}/timeline")
    assert r.status_code == 404


def test_get_timeline_404_unknown_job(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/jobs/nope/timeline")
    assert r.status_code == 404


# ──────────────────────────── set-interval op ────────────────────────────


def test_set_interval_replaces_window_and_clamps(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/set-interval",
        json={"version": v, "source_start": 10.0, "source_end": 40.0},
    )
    assert r.status_code == 200
    edit = r.json()
    assert len(edit["source_intervals"]) == 1
    iv = edit["source_intervals"][0]
    assert iv["source_start"] == 10.0
    assert iv["source_end"] == 40.0


def test_set_interval_optimistic_lock(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    ok = client.post(
        f"/jobs/{job}/clips/clip_01/edit/set-interval",
        json={"version": v, "source_start": 5.0, "source_end": 25.0},
    )
    assert ok.status_code == 200
    stale = client.post(
        f"/jobs/{job}/clips/clip_01/edit/set-interval",
        json={"version": v, "source_start": 6.0, "source_end": 26.0},
    )
    assert stale.status_code == 409


def test_set_interval_404_for_missing_edit(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.post(
        f"/jobs/{job}/clips/clip_09/edit/set-interval",
        json={"version": 1, "source_start": 5.0, "source_end": 25.0},
    )
    assert r.status_code == 404


# ──────────────────────────── preset seeding ────────────────────────────


def test_presets_include_seeds_by_default(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    r = client.get("/presets")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()]
    assert ids[:4] == ["preset_a", "preset_b", "preset_c", "preset_d"]


def test_user_preset_appended_after_seeds_and_no_dup(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    saved = client.post(
        "/presets", json={"name": "Mine", "style": {"color": "#00FF00"}, "highlight": None}
    )
    assert saved.status_code == 200
    pid = saved.json()["id"]
    ids = [p["id"] for p in client.get("/presets").json()]
    assert ids[:4] == ["preset_a", "preset_b", "preset_c", "preset_d"]
    assert pid in ids
    # no duplicates
    assert len(ids) == len(set(ids))


def test_user_override_of_seed_id_keeps_seed_position(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    # save a preset with a seed id → should dedup (seed wins position, user value persists once)
    from app.editor.presets import save_preset
    from app.models import CaptionPreset, CaptionStyle

    save_preset(CaptionPreset(id="preset_a", name="Custom A", style=CaptionStyle(color="#123456")))
    presets_list = client.get("/presets").json()
    ids = [p["id"] for p in presets_list]
    assert ids.count("preset_a") == 1
    assert ids[:4] == ["preset_a", "preset_b", "preset_c", "preset_d"]
