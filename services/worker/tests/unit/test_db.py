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


def test_source_kind_reflects_upload_jobs() -> None:
    # D5: upload-джоб не должен врать source_kind="youtube".
    base = {"id": "j", "status": "queued", "stage": "queued", "progress": 0, "error": None}
    assert row_to_wire({**base, "source_type": "upload"})["source_kind"] == "upload"
    assert row_to_wire({**base, "source_type": "youtube"})["source_kind"] == "youtube"
    assert row_to_wire(base)["source_kind"] == "youtube"  # отсутствует → дефолт


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


def test_cloud_row_keeps_r2_key_ref_marker_untouched() -> None:
    # D6: долговечный маркер ключа r2://<key> (не presigned URL) НЕ префиксится media/ —
    # его резолвит I/O-слой (get_job) свежим presign'ом на каждом чтении (не протухает).
    row = {
        "id": "job_z",
        "status": "done",
        "stage": "done",
        "progress": 100,
        "error": None,
        "clips": [{"id": "clip_01", "video_url": "r2://job_z/clip_01.mp4"}],
        "cost_usd": 0.0,
        "duration_sec": 0.0,
        "elapsed_sec": 0.0,
    }
    wire = row_to_wire(row)
    assert wire["clips"][0]["video_url"] == "r2://job_z/clip_01.mp4"  # без media/-префикса


def test_get_job_re_presigns_r2_key_ref_on_read(monkeypatch, tmp_path) -> None:
    # D6: get_job ре-подписывает долговечный маркер r2://<key> СВЕЖИМ URL на КАЖДОМ чтении —
    # клип не отдаёт 403 спустя час/неделю (старый код пёк presigned URL намертво в строку).
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    clip = {"id": "clip_01", "video_url": "r2://job_q/clip_01.mp4"}
    import json as _json

    with db._conn() as c:
        c.execute(
            "INSERT INTO jobs (id,status,stage,progress,clips_json,cost_usd,duration_sec,"
            "elapsed_sec,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("job_q", "done", "done", 100, _json.dumps([clip]), 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    from app import storage

    calls: list[str] = []

    def fake_resolve(stored: str) -> str:
        calls.append(stored)
        return "https://signed.example/fresh?sig=NEW"

    monkeypatch.setattr(storage, "resolve_media_url", fake_resolve)
    wire = db.get_job("job_q")
    assert wire is not None
    assert wire["clips"][0]["video_url"] == "https://signed.example/fresh?sig=NEW"
    assert calls == ["r2://job_q/clip_01.mp4"]  # маркер прошёл через ре-подпись


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


def test_record_usage_is_idempotent_per_job(monkeypatch, tmp_path) -> None:
    # Повторный учёт того же job_id (ретрай/повторный прогон) не создаёт вторую строку и
    # возвращает False → вызыватель (_meter) не спишет PAYG дважды.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "u.db")
    db.init_db()
    assert db.record_usage("user_1", "job_a", 10.0, "2026-06") is True
    assert db.record_usage("user_1", "job_a", 10.0, "2026-06") is False  # дубль job_id
    june = db.get_monthly_usage("user_1", "2026-06")
    assert june == {"videos": 1, "minutes": 10.0, "credits": 1}  # одна запись, не две


def test_record_usage_without_job_id_is_not_deduped(monkeypatch, tmp_path) -> None:
    # job_id=None (аноним) дедупом не покрыт — каждая запись считается (NULL'ы различны).
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "u.db")
    db.init_db()
    assert db.record_usage("user_1", None, 10.0, "2026-06") is True
    assert db.record_usage("user_1", None, 10.0, "2026-06") is True
    assert db.get_monthly_usage("user_1", "2026-06")["videos"] == 2


# ─────────────────────────── BE-H: deduct_payg (списание PAYG) ───────────────────────────
# Денежный инвариант: PAYG-баланс убывает ровно на покрытый объём, НИКОГДА не отрицателен.


def test_deduct_payg_decrements_balance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "p.db")
    db.init_db()
    db.add_payg_credits("u1", 5)
    db.deduct_payg("u1", 2)
    assert db.get_profile("u1")["payg_credits"] == 3


def test_deduct_payg_floors_at_zero_never_negative(monkeypatch, tmp_path) -> None:
    # Списание больше баланса не должно уводить в минус (защита от двойного учёта/гонки).
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "p.db")
    db.init_db()
    db.add_payg_credits("u1", 1)
    db.deduct_payg("u1", 4)
    assert db.get_profile("u1")["payg_credits"] == 0


def test_deduct_payg_zero_is_noop(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "p.db")
    db.init_db()
    db.add_payg_credits("u1", 3)
    db.deduct_payg("u1", 0)
    assert db.get_profile("u1")["payg_credits"] == 3


def test_deduct_payg_missing_profile_is_safe(monkeypatch, tmp_path) -> None:
    # Нет профиля → нечего списывать, не падаем и не создаём отрицательный баланс.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "p.db")
    db.init_db()
    db.deduct_payg("ghost", 2)
    assert db.get_profile("ghost")["payg_credits"] == 0
