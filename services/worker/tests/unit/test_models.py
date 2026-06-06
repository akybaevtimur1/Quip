"""Контрактные smoke-тесты для app.models (единый источник типов).

Цель: зафиксировать инварианты контракта ДО кода — границы score, состав enum,
обязательные поля. Это страхует codegen-цепочку (models.py → contract.json → types.ts):
сломаем модель — упадёт тут, а не в проде.
"""

import pytest
from pydantic import ValidationError

from app.models import (
    Clip,
    ClipOut,
    ClipType,
    CropWindow,
    Job,
    JobStatus,
    Metrics,
    Segment,
    SourceKind,
    Transcript,
    Word,
)


def test_clip_type_enum_values() -> None:
    assert {t.value for t in ClipType} == {
        "hook",
        "emotional_peak",
        "complete_thought",
        "strong_quote",
    }


def test_job_status_enum_values() -> None:
    assert {s.value for s in JobStatus} == {
        "queued",
        "downloading",
        "transcribing",
        "selecting",
        "rendering",
        "done",
        "failed",
    }


def test_source_kind_enum_values() -> None:
    assert {k.value for k in SourceKind} == {"youtube", "upload"}


def test_word_roundtrips_in_seconds() -> None:
    w = Word(text="So", start=124.5, end=124.7)
    assert w.confidence is None
    assert w.end > w.start


def test_segment_score_must_be_in_unit_interval() -> None:
    ok = Segment(
        start=1.0, end=20.0, reason="clear standalone claim", score=0.9, type=ClipType.hook
    )
    assert ok.score == 0.9
    with pytest.raises(ValidationError):
        Segment(start=1.0, end=20.0, reason="x", score=1.5, type=ClipType.hook)
    with pytest.raises(ValidationError):
        Segment(start=1.0, end=20.0, reason="x", score=-0.1, type=ClipType.hook)


def test_transcript_holds_word_list() -> None:
    t = Transcript(
        language="en",
        duration=30.0,
        words=[Word(text="Hi", start=0.0, end=0.3)],
    )
    assert t.words[0].text == "Hi"


def test_crop_window_is_integer_pixels() -> None:
    c = CropWindow(t=5.0, x=420, y=0, w=1080, h=1920)
    assert (c.w, c.h) == (1080, 1920)


def test_clip_internal_shape() -> None:
    seg = Segment(start=1.0, end=20.0, reason="r", score=0.5, type=ClipType.strong_quote)
    clip = Clip(
        id="clip_01",
        segment=seg,
        crop=[CropWindow(t=1.0, x=0, y=0, w=1080, h=1920)],
        captions_ass_path="captions_clip_01.ass",
        output_path="clips/clip_01.mp4",
        cost_usd=0.1,
        latency_s=12.3,
    )
    assert clip.segment.type is ClipType.strong_quote


def test_job_defaults_empty_clips_and_no_metrics() -> None:
    job = Job(
        id="job_1",
        status=JobStatus.queued,
        stage=JobStatus.queued,
        progress=0,
        source_kind=SourceKind.youtube,
    )
    assert job.clips == []
    assert job.metrics is None
    assert job.error is None


def test_job_done_with_clip_and_metrics() -> None:
    job = Job(
        id="job_1",
        status=JobStatus.done,
        stage=JobStatus.done,
        progress=100,
        source_kind=SourceKind.youtube,
        clips=[
            ClipOut(
                id="clip_01",
                start=124.5,
                end=152.8,
                duration=28.3,
                reason="a concrete why",
                type=ClipType.strong_quote,
                score=0.91,
                video_url="http://x/clip_01.mp4",
                transcript="...snippet...",
                words=[Word(text="So", start=124.5, end=124.7)],
            )
        ],
        metrics=Metrics(cost_usd=0.58, duration_sec=750.0, elapsed_sec=142.3),
    )
    assert job.clips[0].thumbnail_url is None
    assert job.metrics is not None and job.metrics.cost_usd == 0.58
