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


def test_regenerate_hook_updates_text_and_bumps_version(monkeypatch, tmp_path):
    # W4: ручка зовёт Gemini-реген (мокаем где он СВЯЗАН — hook_ops) и обновляет hook.text + версию.
    from app.editor import hook_ops

    monkeypatch.setattr(
        hook_ops, "regenerate_hook", lambda *a, **k: ("Новый цепляющий хук", "shock")
    )
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(f"/jobs/{job}/clips/clip_01/hook/regenerate", json={"version": v})
    assert r.status_code == 200
    edit = r.json()
    assert edit["captions"]["hook"]["text"] == "Новый цепляющий хук"
    assert edit["captions"]["hook"]["enabled"] is True
    assert edit["version"] == v + 1
    # optimistic-lock: повтор со старой версией → 409
    stale = client.post(f"/jobs/{job}/clips/clip_01/hook/regenerate", json={"version": v})
    assert stale.status_code == 409


def test_get_edit_404_for_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/edit")
    assert r.status_code == 404


def test_crop_split_override_rejected(monkeypatch, tmp_path):
    # MVP (2026-06-24): split удалён из API — запрос с mode="split" отклоняется (422).
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
    assert r.status_code == 422


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


def test_trim_bad_index_returns_400(monkeypatch, tmp_path):
    # ops.apply_trim рейзит JobError на индекс вне диапазона → эндпоинт ДОЛЖЕН отдать 400
    # (валидация ввода), а не 500. Транскрипт фикстуры = 3 слова (idx 0..2).
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/trim", json={"version": v, "word_indices": [99]}
    )
    assert r.status_code == 400
    assert "range" in r.json()["detail"]


def test_add_section_inverted_range_returns_400(monkeypatch, tmp_path):
    # add_section рейзит JobError, если source_end <= source_start → 400, не 500.
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/add-section",
        json={"version": v, "source_start": 5.0, "source_end": 2.0, "at_index": 1},
    )
    assert r.status_code == 400


def test_extend_unknown_edge_returns_400(monkeypatch, tmp_path):
    # apply_extend рейзит JobError на неизвестный край → 400, не 500.
    client, job = _client(monkeypatch, tmp_path)
    v = client.get(f"/jobs/{job}/clips/clip_01/edit").json()["version"]
    r = client.post(
        f"/jobs/{job}/clips/clip_01/edit/extend",
        json={"version": v, "edge": "middle", "new_value": 1.0},
    )
    assert r.status_code == 400


def test_post_render_spawn_failure_marks_render_failed(monkeypatch, tmp_path):
    # На Modal-пути dispatch.spawn может упасть (modal import / lookup). Без перехвата клип
    # застрял бы в "rendering" навсегда. Эндпоинт ДОЛЖЕН перевести его в failed (правило №8).
    client, job = _client(monkeypatch, tmp_path)
    import app.main as main

    monkeypatch.setattr(main.dispatch, "modal_spawn_enabled", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("modal down")

    monkeypatch.setattr(main.dispatch, "spawn", boom)
    # клип должен существовать (ensure default edit)
    client.get(f"/jobs/{job}/clips/clip_01/edit")
    r = client.post(f"/jobs/{job}/clips/clip_01/render")
    assert r.status_code == 500
    status = client.get(f"/jobs/{job}/clips/clip_01/render").json()
    assert status["status"] == "failed"
    assert status["error"]


def test_reframe_endpoint_returns_flat_clip_time_regions(monkeypatch, tmp_path):
    # D2: /reframe считает план единым путём (resolve_regions_accurate) и отдаёт КЛИП-время.
    client, job = _client(monkeypatch, tmp_path)
    from app import artifacts
    from app.editor import reframe_cache
    from app.pipeline.stage0_import import SourceMeta
    from app.pipeline.stage3_reframe import TrackPoint, TrackRegion

    src = tmp_path / "data" / job / "source.mp4"
    src.write_bytes(b"\x00")
    monkeypatch.setattr(artifacts, "ensure_source", lambda jid: src)
    monkeypatch.setattr(
        artifacts,
        "load_meta",
        lambda jid: SourceMeta(
            job_id=jid,
            source="youtube",
            url=None,
            title="t",
            duration=30.0,
            fps=30.0,
            width=1920,
            height=1080,
        ),
    )

    def fake_accurate(*a, **k):
        # один интервал → один fill-регион (как для исходного сегмента)
        pt = TrackPoint(t=0.0, mode="fill", cx=0.4)
        return [[TrackRegion(t0=0.0, t1=3.0, mode="fill", points=(pt,))]]

    monkeypatch.setattr(reframe_cache, "resolve_regions_accurate", fake_accurate)
    r = client.get(f"/jobs/{job}/clips/clip_01/reframe")
    assert r.status_code == 200
    regions = r.json()["regions"]
    assert len(regions) == 1
    assert regions[0]["mode"] == "fill" and regions[0]["t0"] == 0.0
    assert regions[0]["points"][0]["cx"] == 0.4


def test_reframe_endpoint_404_missing_clip(monkeypatch, tmp_path):
    client, job = _client(monkeypatch, tmp_path)
    r = client.get(f"/jobs/{job}/clips/clip_09/reframe")
    assert r.status_code == 404


def test_export_captioned_mp4_serves_file(monkeypatch, tmp_path):
    # D1: "With captions" = on-demand рендер ТЕКУЩИХ правок С субтитрами в ОТДЕЛЬНЫЙ файл.
    client, job = _client(monkeypatch, tmp_path)
    from app.editor import store as store_mod

    seen = {}

    def fake_render(job_id, clip_id, *, with_subtitles, out_rel):
        seen["with_subtitles"] = with_subtitles
        seen["out_rel"] = out_rel
        p = store_mod.data_root() / job_id / out_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x00\x00fakeMP4")

    monkeypatch.setattr("app.main.render_edit_to_file", fake_render)
    r = client.get(f"/jobs/{job}/clips/clip_01/export/captioned.mp4")
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"
    assert seen["with_subtitles"] is True  # С субтитрами (в отличие от clean)
    assert seen["out_rel"] == "clips/clip_01_captioned.mp4"  # отдельный файл, не clip_01.mp4


def test_render_job_writes_captioned_never_overwrites_clean(monkeypatch, tmp_path):
    # D1-инвариант: фон-рендер редактора НИКОГДА не трогает чистый clips/<id>.mp4.
    client, job = _client(monkeypatch, tmp_path)  # noqa: F841 — поднимает DATA_ROOT/DB
    from app import storage, tasks
    from app.editor import store as store_mod

    clean = store_mod.data_root() / job / "clips" / "clip_01.mp4"
    clean.parent.mkdir(parents=True, exist_ok=True)
    clean.write_bytes(b"CLEAN-REFRAME-CLIP")  # как после batch-рендера

    seen = {}

    def fake_render(job_id, clip_id, *, with_subtitles, out_rel):
        seen["out_rel"] = out_rel
        (store_mod.data_root() / job_id / out_rel).write_bytes(b"BURNED")

    monkeypatch.setattr(tasks, "render_edit_to_file", fake_render)
    monkeypatch.setattr(storage, "upload_clip", lambda *a, **k: "clips/clip_01_captioned.mp4")
    captured = {}
    monkeypatch.setattr(
        db, "set_render_status", lambda j, c, st, url, err: captured.update(status=st, url=url)
    )

    tasks.render_clip_edit_job(job, "clip_01")

    assert seen["out_rel"] == "clips/clip_01_captioned.mp4"
    assert clean.read_bytes() == b"CLEAN-REFRAME-CLIP"  # чистый клип НЕ перетёрт
    assert captured["status"] == "done"
    assert captured["url"] == "clips/clip_01_captioned.mp4"
