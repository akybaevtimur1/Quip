"""Тест endpoint POST /jobs/upload: стриминг файла на диск + постановка фон-таска.

Фон-таск (run_upload_job) замокан — тест проверяет ТОЛЬКО wiring эндпоинта
(приём multipart, запись файла чанками, создание queued-задачи), без Deepgram/Gemini/ffmpeg.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db


def test_upload_streams_file_and_enqueues_job(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    db.init_db()

    import app.main as main

    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    captured: dict[str, object] = {}

    def fake_task(
        job_id: str,
        upload_path: str,
        title: str,
        max_clips: int | None,
        user_id: str | None = None,
        language: str | None = None,
    ) -> None:
        captured.update(job_id=job_id, upload_path=upload_path, title=title, max_clips=max_clips)

    monkeypatch.setattr(main, "run_upload_job", fake_task)

    client = TestClient(main.app)
    content = b"\x00\x01fake video payload bytes" * 1000  # >1 чанк не нужен, но не пусто
    r = client.post(
        "/jobs/upload",
        files={"file": ("My Clip.mov", content, "video/quicktime")},
        data={"max_clips": "3"},
    )

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    job_id = body["id"]

    # файл записан на диск под нормализованным именем upload.<ext>
    written = tmp_path / "data" / job_id / "upload.mov"
    assert written.exists()
    assert written.read_bytes() == content

    # фон-таск поставлен с верными аргументами
    assert captured["job_id"] == job_id
    assert captured["title"] == "My Clip.mov"
    assert captured["max_clips"] == 3
    assert str(captured["upload_path"]).endswith("upload.mov")

    # задача создана в БД
    assert db.get_job(job_id) is not None


def test_upload_without_max_clips_defaults_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    db.init_db()

    import app.main as main

    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    captured: dict[str, object] = {}
    monkeypatch.setattr(main, "run_upload_job", lambda *a: captured.update(max_clips=a[3]))

    client = TestClient(main.app)
    r = client.post("/jobs/upload", files={"file": ("v.mp4", b"abc", "video/mp4")})

    assert r.status_code == 202
    assert captured["max_clips"] is None


def test_upload_spawns_modal_job_when_enabled(monkeypatch, tmp_path: Path) -> None:
    # На Modal (MODAL_SPAWN=1): исходник заливается в R2 + spawn долгоживущей upload_job,
    # БЕЗ in-process BackgroundTask (web scale-to-zero убил бы фон-таск на полпути).
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    db.init_db()

    import app.main as main

    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    bg_called: list = []
    uploaded: dict = {}
    spawned: dict = {}
    monkeypatch.setattr(main, "run_upload_job", lambda *a: bg_called.append(a))
    monkeypatch.setattr(main.dispatch, "modal_spawn_enabled", lambda: True)
    monkeypatch.setattr(
        main.storage, "upload_source", lambda path, job_id: uploaded.update(job_id=job_id)
    )
    monkeypatch.setattr(main.dispatch, "spawn", lambda fn, *a: spawned.update(fn=fn, args=a))

    client = TestClient(main.app)
    r = client.post(
        "/jobs/upload",
        files={"file": ("clip.mp4", b"xyz", "video/mp4")},
        data={"max_clips": "4"},
    )

    assert r.status_code == 202
    job_id = r.json()["id"]
    assert uploaded["job_id"] == job_id  # исходник застейджен в R2
    assert spawned["fn"] == "upload_job"  # спавним именно upload_job
    assert spawned["args"][0] == job_id
    assert spawned["args"][1] == "clip.mp4"
    assert spawned["args"][2] == 4  # max_clips проброшен
    assert bg_called == []  # BackgroundTask НЕ использован на Modal


def test_upload_spawn_failure_marks_job_failed(monkeypatch, tmp_path: Path) -> None:
    # Сбой диспатча на Modal → джоб помечен failed + HTTP 500 (не вечная очередь, правило №8).
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "jobs.db")
    db.init_db()

    import app.main as main

    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main, "run_upload_job", lambda *a: None)
    monkeypatch.setattr(main.dispatch, "modal_spawn_enabled", lambda: True)
    monkeypatch.setattr(main.storage, "upload_source", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("modal down")

    monkeypatch.setattr(main.dispatch, "spawn", boom)
    failed: dict = {}
    monkeypatch.setattr(main.db, "set_failed", lambda jid, err: failed.update(job_id=jid, err=err))

    client = TestClient(main.app)
    r = client.post("/jobs/upload", files={"file": ("c.mp4", b"z", "video/mp4")})

    assert r.status_code == 500
    assert failed and "modal down" in failed["err"]
