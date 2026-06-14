"""Тесты оркестрации (app/tasks.py): фон-таски и их статус-семантика.

Внешние вызовы (Gemini/Deepgram/ffmpeg) замоканы — проверяем ТОЛЬКО как таск
переводит результат/ошибку в статус (правило №8: никаких тихих успехов на пустом).
"""

from __future__ import annotations

from pathlib import Path

from app import db, tasks
from app.billing import QuotaDecision
from app.editor import chapters as chmod
from app.errors import JobError
from app.models import Chapter, Metrics, Transcript, Word


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


# ─────────────────────────── BE-H: метеринг расхода (PAYG split) ───────────────────────────
# Денежный инвариант: гейт считает split (месячный/PAYG), метеринг ОБЯЗАН его применить —
# списать PAYG-кредиты И записать в месячный счётчик ТОЛЬКО месячную часть (нет двойного учёта).


def _job_with_minutes(minutes: float) -> tasks.Job:
    from app.models import Job, JobStatus

    return Job(
        id="j",
        status=JobStatus.done,
        stage=JobStatus.done,
        progress=100,
        source_kind="youtube",
        metrics=Metrics(cost_usd=0.0, duration_sec=minutes * 60.0, elapsed_sec=0.0),
    )


def _capture_meter(monkeypatch):
    recorded: list[tuple] = []
    deducted: list[tuple] = []
    monkeypatch.setattr(db, "record_usage", lambda *a, **k: recorded.append((a, k)))
    monkeypatch.setattr(db, "deduct_payg", lambda *a, **k: deducted.append(a))
    return recorded, deducted


def test_meter_records_only_monthly_part_and_deducts_payg(monkeypatch):
    # Видео 65 мин: 5 мин с месячного пула, 60 мин из PAYG (1 кредит). Месячный счётчик
    # должен получить ТОЛЬКО 5 мин (не 65 → иначе двойной учёт), PAYG — списать 1.
    recorded, deducted = _capture_meter(monkeypatch)
    decision = QuotaDecision(True, None, minutes=65.0, from_monthly_min=5.0, from_payg_min=60.0)
    holder: dict = {"decision": decision}

    tasks._meter("user_1", "job_x", _job_with_minutes(65.0), holder)

    assert len(recorded) == 1
    args, _kw = recorded[0]
    # record_usage(user_id, job_id, source_minutes=from_monthly_min, month, ...)
    assert args[0] == "user_1" and args[1] == "job_x"
    assert args[2] == 5.0  # ТОЛЬКО месячная часть
    assert deducted == [("user_1", 1)]  # ceil(60/60) = 1 PAYG-кредит


def test_meter_all_monthly_does_not_touch_payg(monkeypatch):
    recorded, deducted = _capture_meter(monkeypatch)
    decision = QuotaDecision(True, None, minutes=40.0, from_monthly_min=40.0, from_payg_min=0.0)
    tasks._meter("user_1", "job_y", _job_with_minutes(40.0), {"decision": decision})
    assert len(recorded) == 1 and recorded[0][0][2] == 40.0
    assert deducted == []  # PAYG не трогаем


def test_meter_all_payg_records_zero_monthly(monkeypatch):
    # Месячные исчерпаны, видео целиком из PAYG → месячный счётчик получает 0 мин,
    # списываем PAYG. (record_usage всё равно вызывается для аудита job_id, но с 0 мин.)
    recorded, deducted = _capture_meter(monkeypatch)
    decision = QuotaDecision(True, None, minutes=30.0, from_monthly_min=0.0, from_payg_min=30.0)
    tasks._meter("user_1", "job_z", _job_with_minutes(30.0), {"decision": decision})
    assert recorded[0][0][2] == 0.0  # ноль месячных
    assert deducted == [("user_1", 1)]  # ceil(30/60)=1


def test_meter_no_decision_falls_back_to_full_monthly(monkeypatch):
    # Биллинг выключен (гейт не дал decision) → старое поведение: пишем полные минуты как
    # месячные, PAYG не трогаем (PAYG-баланс при выключенном биллинге не консультировался).
    recorded, deducted = _capture_meter(monkeypatch)
    tasks._meter("user_1", "job_q", _job_with_minutes(12.0), {"decision": None})
    assert recorded[0][0][2] == 12.0
    assert deducted == []


def test_meter_no_user_is_noop(monkeypatch):
    recorded, deducted = _capture_meter(monkeypatch)
    tasks._meter(None, "job", _job_with_minutes(10.0), {"decision": None})
    assert recorded == [] and deducted == []


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
