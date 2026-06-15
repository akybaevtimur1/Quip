"""Тесты pure-логики Stage 0 (Import): парсинг ffprobe → meta.

Багоопасное место — `fps` из `r_frame_rate` ("30000/1001" → 29.97) и фолбэк
длительности (stream → format). Поэтому тест-первым.
"""

from pathlib import Path

import pytest

from app.errors import JobError
from app.models import SourceKind
from app.pipeline.stage0_import import build_preview_cmd, build_source_meta, parse_fps


class TestBuildPreviewCmd:
    """Pure-билдер ffmpeg-команды для лёгкого preview-прокси редактора."""

    def test_h264_faststart_aac(self) -> None:
        src, dst = Path("/d/source.mp4"), Path("/d/preview.mp4")
        cmd = build_preview_cmd(src, dst, height=720, crf=30)
        assert cmd[0] == "ffmpeg"
        assert cmd[cmd.index("-c:v") + 1] == "libx264"  # H.264 → hw-декод в браузере (не AV1)
        assert cmd[cmd.index("-movflags") + 1] == "+faststart"  # moov вперёд → быстрый старт
        assert cmd[cmd.index("-c:a") + 1] == "aac"
        assert cmd[-1] == str(dst)  # str(Path) → OS-разделители (Windows \ vs POSIX /)
        assert str(src) in cmd

    def test_height_and_crf_parametrized(self) -> None:
        cmd = build_preview_cmd(Path("s.mp4"), Path("p.mp4"), height=540, crf=28)
        assert cmd[cmd.index("-vf") + 1] == "scale=-2:540"  # -2 = чётная ширина по аспекту
        assert cmd[cmd.index("-crf") + 1] == "28"


class TestParseFps:
    def test_ntsc_30(self) -> None:
        assert parse_fps("30000/1001") == 29.97

    def test_ntsc_24(self) -> None:
        assert parse_fps("24000/1001") == 23.976

    def test_integer_ratio(self) -> None:
        assert parse_fps("30/1") == 30.0

    def test_bare_number(self) -> None:
        assert parse_fps("25") == 25.0

    def test_zero_denominator_raises(self) -> None:
        with pytest.raises(JobError):
            parse_fps("30/0")

    def test_garbage_raises(self) -> None:
        with pytest.raises(JobError):
            parse_fps("abc")

    def test_empty_raises(self) -> None:
        with pytest.raises(JobError):
            parse_fps("")

    def test_zero_numerator_raises(self) -> None:
        # "0/1" → 0.0 fps ранее проходило молча; downstream round(start*fps)/fps
        # (stage5_render:454) делит на fps → ZeroDivisionError при рендере.
        with pytest.raises(JobError):
            parse_fps("0/1")

    def test_zero_bare_raises(self) -> None:
        with pytest.raises(JobError):
            parse_fps("0")

    def test_negative_raises(self) -> None:
        with pytest.raises(JobError):
            parse_fps("-30/1")


class TestBuildSourceMeta:
    def test_reads_stream_fields(self) -> None:
        probe = {
            "streams": [
                {
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30000/1001",
                    "duration": "754.320000",
                }
            ]
        }
        m = build_source_meta(
            probe, job_id="job_1", source=SourceKind.youtube, url="http://x", title="Test"
        )
        assert (m.width, m.height) == (1920, 1080)
        assert m.fps == 29.97
        assert m.duration == 754.32
        assert m.job_id == "job_1"
        assert m.source is SourceKind.youtube

    def test_duration_falls_back_to_format(self) -> None:
        probe = {
            "streams": [{"width": 1280, "height": 720, "r_frame_rate": "25/1"}],
            "format": {"duration": "12.5"},
        }
        m = build_source_meta(probe, job_id="j", source=SourceKind.upload, url=None, title="Local")
        assert m.duration == 12.5
        assert m.url is None

    def test_no_video_stream_raises(self) -> None:
        with pytest.raises(JobError):
            build_source_meta(
                {"streams": []}, job_id="j", source=SourceKind.youtube, url="u", title="t"
            )

    def test_missing_duration_everywhere_raises(self) -> None:
        probe = {"streams": [{"width": 100, "height": 100, "r_frame_rate": "30/1"}]}
        with pytest.raises(JobError):
            build_source_meta(probe, job_id="j", source=SourceKind.youtube, url="u", title="t")

    def test_zero_duration_raises(self) -> None:
        # duration=0 проходило молча → пустой клип/деление в downstream-математике.
        probe = {
            "streams": [{"width": 100, "height": 100, "r_frame_rate": "30/1", "duration": "0"}]
        }
        with pytest.raises(JobError):
            build_source_meta(probe, job_id="j", source=SourceKind.youtube, url="u", title="t")

    def test_zero_width_raises(self) -> None:
        probe = {"streams": [{"width": 0, "height": 720, "r_frame_rate": "25/1", "duration": "10"}]}
        with pytest.raises(JobError):
            build_source_meta(probe, job_id="j", source=SourceKind.upload, url=None, title="t")
