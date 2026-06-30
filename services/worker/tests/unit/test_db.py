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


def test_progress_detail_counts_surfaced_and_coerced() -> None:
    # 0011: live-narration счётчики прокидываются в wire-Job с коэрсией типов (jsonb/SQLite).
    base = {"id": "j", "status": "selecting", "stage": "selecting", "progress": 60, "error": None}
    wire = row_to_wire(
        {**base, "source_minutes": "8.3", "transcript_words": "412", "moments_found": 9}
    )
    assert wire["source_minutes"] == 8.3
    assert wire["transcript_words"] == 412
    assert wire["moments_found"] == 9


def test_progress_detail_absent_is_none() -> None:
    # Старые строки / до проставления → None (фронт не рисует чип). Backward compat.
    base = {
        "id": "j",
        "status": "transcribing",
        "stage": "transcribing",
        "progress": 35,
        "error": None,
    }
    wire = row_to_wire(base)
    assert wire["source_minutes"] is None
    assert wire["transcript_words"] is None
    assert wire["moments_found"] is None


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


# ───────── H2: CDN cache-bust клипов грида (чёрный кадр после same-key rewrite) ─────────


def test_cache_token_from_updated_at() -> None:
    # Стабильный токен из updated_at (epoch→int) — меняется при ре-процессе, стабилен на готовом.
    assert db._cache_token({"updated_at": 1_700_000_000.7}) == 1_700_000_000
    assert db._cache_token({"updated_at": "1700000001"}) == 1_700_000_001


def test_cache_token_none_for_missing_or_zero() -> None:
    # Старая/незаполненная строка (None или 0/мусор) → None → без буста (как раньше, без регресса).
    assert db._cache_token({}) is None
    assert db._cache_token({"updated_at": None}) is None
    assert db._cache_token({"updated_at": 0.0}) is None
    assert db._cache_token({"updated_at": "nope"}) is None


def test_resolve_clip_urls_busts_http_grid_url_leaves_relative() -> None:
    # H2: http-URL клипа грида получает ?v=<token> (same-key rewrite → новый URL → CDN-miss свежих
    # байт); относительный (локалка /media) и пустой (pending) — без изменений.
    wire = {
        "clips": [
            {"id": "c1", "video_url": "https://cdn.quip.ink/job_x/clip_01.mp4"},
            {"id": "c2", "video_url": "media/job_x/clips/clip_02.mp4"},
            {"id": "c3", "video_url": ""},
        ]
    }
    out = db._resolve_clip_urls(wire, cache_token=42)
    assert out["clips"][0]["video_url"] == "https://cdn.quip.ink/job_x/clip_01.mp4?v=42"
    assert out["clips"][1]["video_url"] == "media/job_x/clips/clip_02.mp4"  # rel — без буста
    assert out["clips"][2]["video_url"] == ""  # pending не трогаем


def test_resolve_clip_urls_no_token_is_noop_on_http() -> None:
    wire = {"clips": [{"id": "c1", "video_url": "https://cdn/clip.mp4"}]}
    out = db._resolve_clip_urls(wire, cache_token=None)
    assert out["clips"][0]["video_url"] == "https://cdn/clip.mp4"


def test_get_job_appends_cache_bust_to_grid_clip(monkeypatch, tmp_path) -> None:
    # End-to-end (SQLite): готовый клип с http-URL получает ?v=<int(updated_at)> на чтении →
    # после ре-процесса (новый updated_at) URL меняется → CDN отдаёт свежие байты, не чёрный кадр.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    clip = {"id": "clip_01", "video_url": "https://cdn.quip.ink/job_h/clip_01.mp4"}
    import json as _json

    with db._conn() as c:
        c.execute(
            "INSERT INTO jobs (id,status,stage,progress,clips_json,cost_usd,duration_sec,"
            "elapsed_sec,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("job_h", "done", "done", 100, _json.dumps([clip]), 0.0, 0.0, 0.0, 0.0, 1700000500.0),
        )
    wire = db.get_job("job_h")
    assert wire is not None
    assert wire["clips"][0]["video_url"] == ("https://cdn.quip.ink/job_h/clip_01.mp4?v=1700000500")


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


# ─────────────────── Инкрементальная выдача клипов (SQLite-режим) ───────────────────


def _insert_queued_job(job_id: str) -> None:
    db.insert_job(job_id, "youtube", "https://x")


def _pending_clip(clip_id: str) -> dict:
    return {
        "id": clip_id,
        "start": 1.0,
        "end": 5.0,
        "duration": 4.0,
        "reason": "r",
        "type": "hook",
        "score": 0.9,
        "video_url": "",
        "thumbnail_url": None,
        "transcript": "...",
        "words": [],
    }


def test_set_clips_pending_writes_empty_video_urls(monkeypatch, tmp_path) -> None:
    # После Select персистим ВСЕ клипы с пустым video_url + status='rendering'.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    _insert_queued_job("job_inc")
    clips = [_pending_clip("clip_01"), _pending_clip("clip_02")]
    db.set_clips_pending("job_inc", clips, progress=80)

    wire = db.get_job("job_inc")
    assert wire is not None
    assert wire["status"] == "rendering"
    assert wire["progress"] == 80
    assert len(wire["clips"]) == 2
    # Пустой video_url остаётся пустым (НЕ префиксится media/) — клип "pending".
    assert [c["video_url"] for c in wire["clips"]] == ["", ""]
    assert wire["metrics"] is None  # ещё не done


def test_set_clip_ready_fills_only_target_index(monkeypatch, tmp_path) -> None:
    # Каждый клип-контейнер атомарно заполняет СВОЙ индекс; остальные остаются pending.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    _insert_queued_job("job_inc")
    db.set_clips_pending(
        "job_inc", [_pending_clip("clip_01"), _pending_clip("clip_02")], progress=80
    )
    # clip_index 1-based → пишем второй клип (idx 1).
    db.set_clip_ready("job_inc", 2, "https://cdn/clip_02.mp4")

    wire = db.get_job("job_inc")
    assert wire is not None
    assert wire["clips"][0]["video_url"] == ""  # первый ещё pending
    # H2: http-URL клипа грида несёт CDN cache-bust ?v=<updated_at> → сверяем базу (split на "?v=").
    assert wire["clips"][1]["video_url"].split("?v=")[0] == "https://cdn/clip_02.mp4"
    assert "?v=" in wire["clips"][1]["video_url"]  # буст применён (анти-протухание ре-процесса)
    assert wire["status"] == "rendering"  # set_clip_ready НЕ флипает в done


def test_set_clip_ready_all_clips_then_consistent_with_set_done(monkeypatch, tmp_path) -> None:
    # Заполняем оба клипа по одному → строка несёт обе ссылки ещё ДО set_done.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    _insert_queued_job("job_inc")
    db.set_clips_pending(
        "job_inc", [_pending_clip("clip_01"), _pending_clip("clip_02")], progress=80
    )
    db.set_clip_ready("job_inc", 1, "https://cdn/clip_01.mp4")
    db.set_clip_ready("job_inc", 2, "https://cdn/clip_02.mp4")

    wire = db.get_job("job_inc")
    assert wire is not None
    # H2: каждый http-URL грида несёт CDN cache-bust ?v=<updated_at> → сверяем базы (split "?v=").
    assert [c["video_url"].split("?v=")[0] for c in wire["clips"]] == [
        "https://cdn/clip_01.mp4",
        "https://cdn/clip_02.mp4",
    ]
    assert all("?v=" in c["video_url"] for c in wire["clips"])


def test_set_clip_ready_out_of_range_raises(monkeypatch, tmp_path) -> None:
    # idx за пределами массива клипов — реальный баг, не глушим (правило №8).
    from app.errors import JobError

    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    _insert_queued_job("job_inc")
    db.set_clips_pending("job_inc", [_pending_clip("clip_01")], progress=80)
    try:
        db.set_clip_ready("job_inc", 5, "https://cdn/x.mp4")
        raise AssertionError("expected JobError for out-of-range clip_index")
    except JobError:
        pass


def test_set_clip_ready_invalid_clip_index_raises(monkeypatch, tmp_path) -> None:
    # clip_index 0-based по ошибке → 1-based инвариант нарушен, явный ValueError.
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    _insert_queued_job("job_inc")
    db.set_clips_pending("job_inc", [_pending_clip("clip_01")], progress=80)
    try:
        db.set_clip_ready("job_inc", 0, "https://cdn/x.mp4")
        raise AssertionError("expected ValueError for clip_index < 1")
    except ValueError:
        pass


def test_set_clip_ready_no_row_is_cli_dev_noop(monkeypatch, tmp_path) -> None:
    # Bare-CLI dev (нет строки в SQLite) → пропуск без падения (job.json-only режим).
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "j.db")
    db.init_db()
    db.set_clip_ready("ghost_job", 1, "https://cdn/x.mp4")  # не должно бросать


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
