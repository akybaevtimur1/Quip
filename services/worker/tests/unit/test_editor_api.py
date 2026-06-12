import json

from fastapi.testclient import TestClient

from app import db
from app.editor import store
from app.models import Segment, Transcript, Word


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(store, "DATA_ROOT", tmp_path / "data")
    db.init_db()
    job = "jobA"
    d = tmp_path / "data" / job
    d.mkdir(parents=True)
    (d / "segments.json").write_text(
        json.dumps([Segment(start=0.0, end=3.0, reason="r", score=0.5, type="hook").model_dump()]),
        encoding="utf-8",
    )
    words = [
        Word(text="a", start=0.0, end=0.4),
        Word(text="b", start=0.4, end=0.8),
        Word(text="c", start=1.0, end=1.4),
    ]
    (d / "transcript.json").write_text(
        Transcript(language="ru", duration=3.0, words=words).model_dump_json(),
        encoding="utf-8",
    )
    from app.main import app

    return TestClient(app), job


def test_get_edit_creates_default(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_01/edit")
    assert r.status_code == 200
    edit = r.json()
    assert edit["version"] == 1 and len(edit["source_intervals"]) == 1


def test_trim_makes_hole_and_optimistic_lock(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [1]}
    )
    assert r.status_code == 200
    assert len(r.json()["source_intervals"]) == 2  # hole punched
    stale = client.post(
        f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [0]}
    )
    assert stale.status_code == 409  # stale version


def test_get_edit_404_for_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/edit")
    assert r.status_code == 404


def test_crop_split_override_saved(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/crop",
        json={
            "version": v,
            "source_start": 0.0,
            "source_end": 3.0,
            "mode": "split",
            "center": 0.25,
            "center_b": 0.75,
        },
    )
    assert r.status_code == 200
    ovs = r.json()["reframe_overrides"]
    assert ovs[-1]["mode"] == "split" and ovs[-1]["center_b"] == 0.75


def test_crop_auto_clears_overrides(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r1 = client.post(
        f"/jobs/{job}/clips/clip_01/edit/crop",
        json={"version": v, "source_start": 0.0, "source_end": 3.0, "mode": "fit"},
    )
    assert len(r1.json()["reframe_overrides"]) == 1
    r2 = client.post(
        f"/jobs/{job}/clips/clip_01/edit/crop",
        json={
            "version": r1.json()["version"],
            "source_start": 0.0,
            "source_end": 3.0,
            "mode": "auto",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["reframe_overrides"] == []


def test_crop_invalid_mode_422(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/crop",
        json={"version": v, "source_start": 0.0, "source_end": 3.0, "mode": "zoom"},
    )
    assert r.status_code == 422


def test_preset_save_and_apply(monkeypatch, tmp_path):
    from app.editor import presets

    monkeypatch.setattr(presets, "DATA_ROOT", tmp_path / "data")
    client, job = _client(monkeypatch, tmp_path)
    saved = client.post(
        "/presets",
        json={"name": "Bold", "style": {"color": "#00FF00"}, "highlight": None},
    )
    assert saved.status_code == 200
    pid = saved.json()["id"]
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/apply-preset", json={"version": v, "preset_id": pid}
    )
    assert r.status_code == 200
    assert r.json()["captions"]["style"]["color"] == "#00FF00"


def test_get_ass_returns_valid_ass(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_01/ass")
    assert r.status_code == 200
    body = r.text
    assert "[Script Info]" in body
    assert "[Events]" in body
    assert "PlayResX: 1080" in body  # 9:16-холст


def test_get_ass_404_for_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/ass")
    assert r.status_code == 404


def test_export_srt_returns_attachment(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_01/export.srt")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd and "clip_01.srt" in cd
    body = r.text
    assert "-->" in body  # SRT-таймкод присутствует
    assert "{" not in body and "\\k" not in body  # без ASS-тегов


def test_export_srt_404_for_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/export.srt")
    assert r.status_code == 404


def test_export_clean_mp4_serves_file(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    from app.editor import store as store_mod

    def fake_render(job_id, clip_id, *, with_subtitles, out_rel):
        assert with_subtitles is False  # чистый mp4 = БЕЗ субтитров (экспорт-свобода)
        p = store_mod.data_root() / job_id / out_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00\x00fakeMP4")

    monkeypatch.setattr("app.main.render_edit_to_file", fake_render)
    r = client.get(f"/jobs/{job}/clips/clip_01/export/clean.mp4")
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"
    assert "clip_01_clean.mp4" in r.headers.get("content-disposition", "")


def test_export_clean_mp4_render_error_500(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    from app.errors import JobError

    def boom(job_id, clip_id, *, with_subtitles, out_rel):
        raise JobError("render", "ffmpeg сдох")

    monkeypatch.setattr("app.main.render_edit_to_file", boom)
    r = client.get(f"/jobs/{job}/clips/clip_01/export/clean.mp4")
    assert r.status_code == 500  # рендер упал → видимая ошибка (правило №8), не тихо
    assert "ffmpeg" in r.json()["detail"]


def test_export_clean_mp4_404_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/export/clean.mp4")
    assert r.status_code == 404
