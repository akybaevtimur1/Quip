"""Тесты pure-гейта composite-ASS fast download path (app.fast_export).

I/O (скачать baked-клип, запустить ffmpeg) — в tasks.render_edit_to_file, не здесь.
"""

from app.fast_export import (
    build_composite_ass_cmd,
    can_composite_captions,
    edit_matches_baked,
)
from app.models import (
    CaptionStyle,
    CaptionTrack,
    ClipEdit,
    CropOverride,
    SourceInterval,
)

SEG_START, SEG_END = 24.325, 79.655


def _edit(
    *,
    intervals: list[SourceInterval] | None = None,
    overrides: list[CropOverride] | None = None,
    aspect: str = "9:16",
) -> ClipEdit:
    return ClipEdit(
        id="clip_01",
        version=1,
        source_intervals=intervals or [SourceInterval(source_start=SEG_START, source_end=SEG_END)],
        captions=CaptionTrack(style=CaptionStyle()),
        reframe_overrides=overrides or [],
        aspect=aspect,
    )


# ─────────────────────────── edit_matches_baked ───────────────────────────


def test_pristine_default_edit_matches_baked() -> None:
    # Один интервал == сегмент, без кропа, 9:16 → можно прожечь субтитры поверх baked-клипа.
    assert edit_matches_baked(_edit(), seg_start=SEG_START, seg_end=SEG_END)


def test_tiny_float_drift_within_tolerance_still_matches() -> None:
    iv = [SourceInterval(source_start=SEG_START + 0.02, source_end=SEG_END - 0.03)]
    assert edit_matches_baked(_edit(intervals=iv), seg_start=SEG_START, seg_end=SEG_END)


def test_trimmed_interval_does_not_match() -> None:
    # Юзер обрезал клип → границы ≠ сегмент → baked-геометрия уже не та → полный путь.
    iv = [SourceInterval(source_start=SEG_START + 5.0, source_end=SEG_END)]
    assert not edit_matches_baked(_edit(intervals=iv), seg_start=SEG_START, seg_end=SEG_END)


def test_multi_interval_does_not_match() -> None:
    iv = [
        SourceInterval(source_start=SEG_START, source_end=40.0),
        SourceInterval(source_start=50.0, source_end=SEG_END),
    ]
    assert not edit_matches_baked(_edit(intervals=iv), seg_start=SEG_START, seg_end=SEG_END)


def test_crop_override_does_not_match() -> None:
    ov = [CropOverride(source_start=SEG_START, source_end=SEG_END, mode="fit")]
    assert not edit_matches_baked(_edit(overrides=ov), seg_start=SEG_START, seg_end=SEG_END)


def test_non_9_16_aspect_does_not_match() -> None:
    # baked-клип всегда 9:16 → смена аспекта требует полного ре-рендера.
    assert not edit_matches_baked(_edit(aspect="1:1"), seg_start=SEG_START, seg_end=SEG_END)
    assert not edit_matches_baked(_edit(aspect="16:9"), seg_start=SEG_START, seg_end=SEG_END)


# ─────────────────────────── can_composite_captions (полный гейт) ───────────────────────────


def test_gate_true_only_when_baked_exists_and_edit_matches() -> None:
    assert can_composite_captions(
        _edit(), seg_start=SEG_START, seg_end=SEG_END, baked_clip_exists=True
    )


def test_gate_false_when_baked_missing_even_if_edit_matches() -> None:
    # Нет baked-клипа (старый джоб / клип не залит) → нечего композитить → полный путь.
    assert not can_composite_captions(
        _edit(), seg_start=SEG_START, seg_end=SEG_END, baked_clip_exists=False
    )


def test_gate_false_when_edit_changes_geometry_even_if_baked_exists() -> None:
    ov = [CropOverride(source_start=SEG_START, source_end=SEG_END, mode="fill", center=0.3)]
    assert not can_composite_captions(
        _edit(overrides=ov), seg_start=SEG_START, seg_end=SEG_END, baked_clip_exists=True
    )


# ─────────────────────────── build_composite_ass_cmd ───────────────────────────


def test_composite_cmd_burns_subs_and_copies_audio() -> None:
    cmd = build_composite_ass_cmd(
        "clips/clip_01.mp4",
        "subtitles=clips/clip_01.ass:fontsdir=../../fonts",
        "clips/clip_01_captioned.mp4",
        crf=18,
        preset="medium",
    )
    # Вход — baked-клип; видео ре-энкодим (прожиг субтитров), аудио копируем (без лишнего энкода).
    assert cmd[:4] == ["ffmpeg", "-y", "-i", "clips/clip_01.mp4"]
    assert "-vf" in cmd
    assert cmd[cmd.index("-vf") + 1] == "subtitles=clips/clip_01.ass:fontsdir=../../fonts"
    assert "libx264" in cmd
    assert cmd[cmd.index("-crf") + 1] == "18"
    assert cmd[cmd.index("-preset") + 1] == "medium"
    # аудио НЕ ре-энкодим (baked уже aac)
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    # faststart (moov вперёд) + выход последним аргументом
    assert "+faststart" in cmd
    assert cmd[-1] == "clips/clip_01_captioned.mp4"


def test_composite_cmd_defaults_crf_preset() -> None:
    cmd = build_composite_ass_cmd("a.mp4", "subtitles=a.ass", "b.mp4")
    assert cmd[cmd.index("-crf") + 1] == "20"
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
