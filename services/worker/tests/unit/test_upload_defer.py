"""Upload first-stage latency: аудио из СЫРОГО файла сразу, _ensure_mp4 ОТЛОЖЕН до рендера.

Цель фаундера #1: «transcribing» виден почти мгновенно, а не после скрытого видео-ре-энкода.
Меняется ТОЛЬКО ПОРЯДОК (quality-neutral): _ensure_mp4 (те же параметры) двигается с «до
транскрипции» на «после select, перед R2/фан-аутом». Здесь — TDD этого порядка с моками ffmpeg.

Покрываем:
- prepare_upload_audio: аудио из СЫРОГО src, meta из src, без source.mp4, _ensure_mp4 не зван.
- normalize_upload_source: зовёт _ensure_mp4(src→mp4) когда mp4 нет; идемпотентен когда есть.
- _ensure_mp4-лестница НЕ изменена: h264 → remux (без full ре-энкода); AV1/HEVC → full libx264.
- run_pipeline-КОНТРАКТ: source.mp4 валиден (создан normalize) ДО upload_source и ДО фан-аута.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.errors import JobError
from app.models import Segment, SourceKind, Transcript, Word
from app.pipeline import stage0_import as s0


def _probe(width: int = 1920, height: int = 1080) -> dict[str, Any]:
    return {
        "streams": [
            {"width": width, "height": height, "r_frame_rate": "30000/1001", "duration": "498.26"}
        ]
    }


# ─────────────────────── prepare_upload_audio: аудио из СЫРОГО файла, mp4 отложен ───────────────


def test_prepare_upload_audio_extracts_from_raw_and_defers_mp4(monkeypatch, tmp_path: Path) -> None:
    raw = tmp_path / "upload.webm"
    raw.write_bytes(b"raw-av1-bytes")
    out = tmp_path / "job"

    audio_calls: list[tuple[Path, Path]] = []
    ensure_calls: list[tuple[Path, Path]] = []

    monkeypatch.setattr(s0, "probe_video", lambda p: _probe())
    monkeypatch.setattr(s0, "extract_audio", lambda src, wav: audio_calls.append((src, wav)))
    monkeypatch.setattr(s0, "_ensure_mp4", lambda src, mp4: ensure_calls.append((src, mp4)))

    meta = s0.prepare_upload_audio(raw, out, job_id="job_x", title="T")

    # Аудио для транскрипции извлечено ИЗ СЫРОГО файла (а не из ре-энкоженного source.mp4).
    assert audio_calls == [(raw, out / "source.wav")]
    # Дорогая видео-нормализация ОТЛОЖЕНА — _ensure_mp4 здесь НЕ вызывался.
    assert ensure_calls == []
    assert not (out / "source.mp4").exists()
    # meta написан, probe'нут из СЫРОГО исходника (длина/размеры/fps → совпадут с будущим mp4).
    assert (out / "meta.json").exists()
    assert meta.source is SourceKind.upload
    assert (meta.width, meta.height, meta.fps) == (1920, 1080, 29.97)
    assert meta.duration == pytest.approx(498.26)


def test_prepare_upload_audio_missing_file_raises(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(s0, "probe_video", lambda p: _probe())
    monkeypatch.setattr(s0, "extract_audio", lambda src, wav: None)
    with pytest.raises(JobError):
        s0.prepare_upload_audio(tmp_path / "nope.mp4", tmp_path / "job", job_id="j", title="t")


def test_prepare_upload_audio_no_audio_track_surfaces_joberror(monkeypatch, tmp_path: Path) -> None:
    # extract_audio роняет JobError на видео без звука (Quip режет по речи) — не глотаем (#8).
    raw = tmp_path / "upload.mp4"
    raw.write_bytes(b"x")
    monkeypatch.setattr(s0, "probe_video", lambda p: _probe())

    def _no_audio(src: Path, wav: Path) -> None:
        raise JobError("import", "This video has no audio track.")

    monkeypatch.setattr(s0, "extract_audio", _no_audio)
    with pytest.raises(JobError, match="no audio track"):
        s0.prepare_upload_audio(raw, tmp_path / "job", job_id="j", title="t")


# ─────────────────────── normalize_upload_source: отложенный _ensure_mp4 ───────────────────────


def test_normalize_runs_ensure_mp4_when_mp4_absent(monkeypatch, tmp_path: Path) -> None:
    raw = tmp_path / "upload.mkv"
    raw.write_bytes(b"raw")
    out = tmp_path / "job"
    out.mkdir()
    calls: list[tuple[Path, Path]] = []

    def _fake_ensure(src: Path, mp4: Path) -> None:
        calls.append((src, mp4))
        mp4.write_bytes(b"mp4")  # имитируем создание source.mp4

    monkeypatch.setattr(s0, "_ensure_mp4", _fake_ensure)
    s0.normalize_upload_source(raw, out)
    assert calls == [(raw, out / "source.mp4")]
    assert (out / "source.mp4").exists()


def test_normalize_is_idempotent_when_mp4_exists(monkeypatch, tmp_path: Path) -> None:
    # Повторный прогон джоба: source.mp4 уже есть → НЕ перекодируем повторно (0 лишней работы).
    out = tmp_path / "job"
    out.mkdir()
    (out / "source.mp4").write_bytes(b"already")
    calls: list[Any] = []
    monkeypatch.setattr(s0, "_ensure_mp4", lambda *a: calls.append(a))
    s0.normalize_upload_source(tmp_path / "upload.mp4", out)
    assert calls == []  # _ensure_mp4 НЕ зван


def test_normalize_missing_src_raises(monkeypatch, tmp_path: Path) -> None:
    out = tmp_path / "job"
    out.mkdir()
    monkeypatch.setattr(s0, "_ensure_mp4", lambda *a: None)
    with pytest.raises(JobError):
        s0.normalize_upload_source(tmp_path / "gone.mp4", out)


def test_import_upload_wrapper_still_creates_all_artifacts(monkeypatch, tmp_path: Path) -> None:
    # Обратная совместимость: eager-обёртка делает и аудио (из raw), и нормализацию (source.mp4).
    raw = tmp_path / "upload.mp4"
    raw.write_bytes(b"raw")
    out = tmp_path / "job"
    order: list[str] = []

    monkeypatch.setattr(s0, "probe_video", lambda p: _probe())
    monkeypatch.setattr(s0, "extract_audio", lambda src, wav: order.append("audio"))

    def _fake_ensure(src: Path, mp4: Path) -> None:
        order.append("mp4")
        mp4.write_bytes(b"mp4")

    monkeypatch.setattr(s0, "_ensure_mp4", _fake_ensure)
    s0.import_upload(raw, out, job_id="j", title="t")
    # Аудио из сырого файла ПЕРЕД нормализацией; оба артефакта на месте.
    assert order == ["audio", "mp4"]
    assert (out / "source.mp4").exists() and (out / "meta.json").exists()


# ─────────────────────── _ensure_mp4-лестница НЕ изменена (quality-neutral) ───────────────────────


def test_ensure_mp4_h264_remux_fast_path_skips_full_reencode(monkeypatch, tmp_path: Path) -> None:
    # h264-совместимый источник → первый remux `-c copy` успешен → ПОЛНЫЙ ре-энкод (_run) НЕ зван.
    mp4 = tmp_path / "source.mp4"
    full_reencode_calls: list[Any] = []

    def _try(cmd: list[str], out: Path) -> bool:
        out.write_bytes(b"remuxed")  # remux создал файл
        return True  # первая (remux) попытка успешна

    monkeypatch.setattr(s0, "_try_ffmpeg", _try)
    monkeypatch.setattr(s0, "_run", lambda *a, **k: full_reencode_calls.append(a))
    s0._ensure_mp4(tmp_path / "in.mp4", mp4)
    assert full_reencode_calls == []  # дорогой libx264 ре-энкод НЕ запускался


def test_ensure_mp4_av1_falls_through_to_full_reencode(monkeypatch, tmp_path: Path) -> None:
    # AV1/HEVC: обе дешёвые попытки (remux, audio-only) проваливаются → ПОЛНЫЙ libx264 ре-энкод.
    mp4 = tmp_path / "source.mp4"
    run_cmds: list[list[str]] = []

    monkeypatch.setattr(s0, "_try_ffmpeg", lambda cmd, out: False)  # дешёвые пути не сработали

    def _run(cmd: list[str], **k: Any) -> None:
        run_cmds.append(cmd)
        mp4.write_bytes(b"reencoded")

    monkeypatch.setattr(s0, "_run", _run)
    s0._ensure_mp4(tmp_path / "in.webm", mp4)
    assert len(run_cmds) == 1
    assert "libx264" in run_cmds[0]  # именно полный ре-энкод (те же параметры, что и раньше)


# ─────────────────────── run_pipeline КОНТРАКТ: mp4 готов ДО R2/фан-аута ───────────────────────


def test_run_pipeline_normalizes_source_before_r2_upload_and_fanout(
    monkeypatch, tmp_path: Path
) -> None:
    """Главный контракт: source.mp4 материализуется (normalize) СТРОГО ДО upload_source/фан-аута.

    Имитируем отложенный аплоад: на диске meta.json + source.wav (НЕТ source.mp4) + кэш
    транскрипта/сегментов (Stage 1/2 — попадание в кэш, без Deepgram/Gemini). normalize_source
    создаёт source.mp4. upload_source и _render_all_clips АССЕРТЯТ, что mp4 уже существует.
    """
    import app.run as run_mod

    out = tmp_path / "job_x"
    out.mkdir(parents=True)
    # Stage 0: только meta + wav → ветка «prepared, source.mp4 deferred».
    meta = {
        "job_id": "job_x", "source": "upload", "url": None, "title": "t",
        "duration": 120.0, "fps": 30.0, "width": 1920, "height": 1080,
    }  # fmt: skip
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (out / "source.wav").write_bytes(b"wav")
    # Stage 1/2 cache hits (transcript.json + segments.json present).
    tr = Transcript(language="en", duration=120.0, words=[Word(text="hi", start=0.0, end=0.5)])
    (out / "transcript.json").write_text(tr.model_dump_json(), encoding="utf-8")
    seg = Segment(start=0.0, end=10.0, reason="r", score=0.7, type="complete_thought",
                  hook="h", why_works="w")  # fmt: skip
    (out / "segments.json").write_text(json.dumps([seg.model_dump()]), encoding="utf-8")

    events: list[str] = []
    mp4 = out / "source.mp4"

    def _normalize() -> None:
        events.append("normalize")
        mp4.write_bytes(b"mp4")  # отложенный _ensure_mp4 создаёт seekable source.mp4

    def _upload_source(path: Path, job_id: str) -> None:
        events.append("upload_source")
        assert mp4.exists(), "source.mp4 ОБЯЗАН существовать ДО заливки в R2"

    def _render_all(job_id, o, source_name, segments, m, user_id):  # noqa: ANN001
        events.append("render_all")
        assert (o / source_name).exists(), "source.mp4 ОБЯЗАН существовать ДО фан-аута рендера"
        return [{
            "clip_id": "clip_01", "clip_index": 1, "video_url": "u1",
            "reframe_lat": 0.0, "render_lat": 0.0, "face_found": True,
        }]  # fmt: skip

    class _S:  # минимальный stub настроек (что читает run_pipeline на этом пути)
        transcript_cache_enabled = False
        preview_height = 720
        preview_crf = 30
        transcription_provider = "deepgram"
        deepgram_model = "nova-3"

    monkeypatch.setattr(run_mod, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(run_mod, "get_settings", lambda: _S())
    monkeypatch.setattr(run_mod, "extract_loudness", lambda p: [])  # без ffmpeg
    monkeypatch.setattr(run_mod.dispatch, "modal_spawn_enabled", lambda: False)
    monkeypatch.setattr(run_mod, "_render_all_clips", _render_all)
    monkeypatch.setattr(run_mod, "build_preview_proxy", lambda *a, **k: None)
    monkeypatch.setattr("app.tasks.generate_video_map_job", lambda jid: None)
    # storage: upload_source ассертит порядок; preview — no-op.
    monkeypatch.setattr(run_mod.storage, "upload_source", _upload_source)
    monkeypatch.setattr(run_mod.storage, "upload_preview", lambda *a, **k: None)
    # db: все вызовы пути — no-op (проверяем ПОРЯДОК файлов, не БД).
    for fn in ("set_progress_detail", "put_job_artifact", "put_job_artifacts", "set_clips_pending"):
        monkeypatch.setattr(run_mod.db, fn, lambda *a, **k: None)

    job = run_mod.run_pipeline("job_x", source_url=None, normalize_source=_normalize)

    # ПОРЯДОК: normalize СТРОГО раньше upload_source, а тот — раньше фан-аута рендера.
    assert events == ["normalize", "upload_source", "render_all"]
    assert job.status.value == "done"
    assert mp4.exists()


def test_run_pipeline_raises_if_source_mp4_missing_after_normalize(
    monkeypatch, tmp_path: Path
) -> None:
    # Контракт жёсткий (правило №8): normalize отработал, но source.mp4 нет → явный JobError,
    # а не битый upload_source/фан-аут ниже.
    import app.run as run_mod

    out = tmp_path / "job_y"
    out.mkdir(parents=True)
    meta = {
        "job_id": "job_y", "source": "upload", "url": None, "title": "t",
        "duration": 60.0, "fps": 30.0, "width": 1280, "height": 720,
    }  # fmt: skip
    (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (out / "source.wav").write_bytes(b"wav")
    tr = Transcript(language="en", duration=60.0, words=[Word(text="hi", start=0.0, end=0.5)])
    (out / "transcript.json").write_text(tr.model_dump_json(), encoding="utf-8")
    seg = Segment(start=0.0, end=10.0, reason="r", score=0.7, type="complete_thought",
                  hook="h", why_works="w")  # fmt: skip
    (out / "segments.json").write_text(json.dumps([seg.model_dump()]), encoding="utf-8")

    class _S:
        transcript_cache_enabled = False
        preview_height = 720
        preview_crf = 30
        transcription_provider = "deepgram"
        deepgram_model = "nova-3"

    monkeypatch.setattr(run_mod, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(run_mod, "get_settings", lambda: _S())
    monkeypatch.setattr(run_mod, "extract_loudness", lambda p: [])
    monkeypatch.setattr(run_mod.dispatch, "modal_spawn_enabled", lambda: False)
    monkeypatch.setattr(
        run_mod, "_render_all_clips", lambda *a, **k: pytest.fail("fan-out reached")
    )
    monkeypatch.setattr(run_mod.storage, "upload_source", lambda *a, **k: pytest.fail("R2 reached"))
    for fn in ("set_progress_detail", "put_job_artifact", "put_job_artifacts", "set_clips_pending"):
        monkeypatch.setattr(run_mod.db, fn, lambda *a, **k: None)

    with pytest.raises(JobError, match="source.mp4 missing after normalization"):
        run_mod.run_pipeline(
            "job_y", source_url=None, normalize_source=lambda: None
        )  # no-op: mp4 не создаётся
