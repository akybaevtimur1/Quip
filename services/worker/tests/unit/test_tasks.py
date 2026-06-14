"""Тесты оркестрации (app/tasks.py): фон-таски и их статус-семантика.

Внешние вызовы (Gemini/Deepgram/ffmpeg) замоканы — проверяем ТОЛЬКО как таск
переводит результат/ошибку в статус (правило №8: никаких тихих успехов на пустом).
"""

from __future__ import annotations

from pathlib import Path

from app import tasks
from app.editor import chapters as chmod
from app.errors import JobError
from app.models import Chapter, Transcript, Word


def _stub_artifacts(monkeypatch, tmp_path: Path, job_id: str) -> Path:
    """Подменить artifacts.job_dir/load_transcript на tmp + готовый транскрипт."""
    from app import artifacts

    out = tmp_path / job_id
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(artifacts, "job_dir", lambda jid: out)
    monkeypatch.setattr(
        artifacts,
        "load_transcript",
        lambda jid: Transcript(
            language="ru", duration=10.0, words=[Word(text="a", start=0.0, end=0.5)]
        ),
    )
    return out


def test_chapters_job_empty_result_is_failed_not_silent_done(monkeypatch, tmp_path):
    # Gemini вернул 0 глав → НЕ status=done с пустым списком (фронт показал бы пустую
    # карту молча, правило №8), а failed с явной причиной.
    job = "job_empty"
    out = _stub_artifacts(monkeypatch, tmp_path, job)
    monkeypatch.setattr(chmod, "generate_chapters", lambda *a, **k: [])

    tasks.generate_chapters_job(job)

    data = chmod.load_chapters(out)
    assert data is not None
    assert data.status == "failed"
    assert data.error  # причина непустая
    assert data.chapters == []


def test_chapters_job_success_writes_done(monkeypatch, tmp_path):
    job = "job_ok"
    out = _stub_artifacts(monkeypatch, tmp_path, job)
    chs = [Chapter(start=0.0, end=10.0, title="Intro", summary="s")]
    monkeypatch.setattr(chmod, "generate_chapters", lambda *a, **k: chs)

    tasks.generate_chapters_job(job)

    data = chmod.load_chapters(out)
    assert data is not None
    assert data.status == "done"
    assert len(data.chapters) == 1


def test_transcript_cache_model_is_provider_aware():
    # Ключ кэша транскрипта должен зависеть от ВЫБРАННОГО провайдера, а не всегда от
    # deepgram_model. Иначе assemblyai-транскрипт помечается deepgram-моделью (мусорный
    # слот) и смена assemblyai-модели не инвалидировала бы кэш.
    from app.run import transcript_cache_model

    class _S:
        transcription_provider = "deepgram"
        deepgram_model = "nova-3"
        assemblyai_model = "best"

    s = _S()
    assert transcript_cache_model(s) == "nova-3"
    s.transcription_provider = "assemblyai"
    assert transcript_cache_model(s) == "best"


def test_chapters_job_joberror_is_failed_with_reason(monkeypatch, tmp_path):
    job = "job_err"
    out = _stub_artifacts(monkeypatch, tmp_path, job)

    def boom(*a, **k):
        raise JobError("chapters", "Gemini квота 0")

    monkeypatch.setattr(chmod, "generate_chapters", boom)

    tasks.generate_chapters_job(job)

    data = chmod.load_chapters(out)
    assert data is not None
    assert data.status == "failed"
    assert "квота" in (data.error or "")
