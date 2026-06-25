"""Тесты pure-логики Stage 0 (Import): парсинг ffprobe → meta.

Багоопасное место — `fps` из `r_frame_rate` ("30000/1001" → 29.97) и фолбэк
длительности (stream → format). Поэтому тест-первым.
"""

from pathlib import Path

import pytest

from app.billing import MAX_VIDEO_MINUTES
from app.errors import JobError
from app.models import SourceKind
from app.pipeline.stage0_import import (
    build_preview_cmd,
    build_source_meta,
    build_youtube_cmd,
    classify_youtube_error,
    parse_fps,
)


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


class TestClassifyYoutubeError:
    """yt-dlp stderr-сигнатура → понятное ENG-сообщение юзеру. PURE (table-driven).

    Каждое сообщение ОБЯЗАНО заканчиваться actionable-подсказкой «download it yourself and
    upload» — фича best-effort: если автоскачивание не вышло, юзер всё равно может залить файл.
    """

    # Каждое user-facing сообщение должно содержать призыв «скачай сам и загрузи».
    _UPLOAD_GUIDANCE = "upload"

    @pytest.mark.parametrize(
        ("stderr", "expect_substr"),
        [
            # bot-gate / 429 / 403 → "YouTube blocked our server"
            (
                "ERROR: [youtube] dQw4: Sign in to confirm you’re not a bot. Use --cookies.",
                "blocked our server",
            ),
            (
                "ERROR: unable to download video data: HTTP Error 429: Too Many Requests",
                "blocked our server",
            ),
            ("ERROR: [youtube] abc: HTTP Error 403: Forbidden", "blocked our server"),
            # private / members-only
            (
                "ERROR: [youtube] xyz: Join this channel to get access to members-only content",
                "members-only",
            ),
            ("ERROR: [youtube] xyz: This video is private", "private"),
            # removed / unavailable
            ("ERROR: [youtube] xyz: Video unavailable", "no longer available"),
            (
                "ERROR: [youtube] xyz: This video has been removed by the uploader",
                "no longer available",
            ),
            # region-locked
            (
                "ERROR: [youtube] xyz: not made this video available in your country",
                "not available in",
            ),
            # age-gated / login required
            ("ERROR: [youtube] xyz: Sign in to confirm your age", "age-restricted"),
            (
                "ERROR: [youtube] xyz: This video may be inappropriate for some users. Sign in",
                "age-restricted",
            ),
            # live / premiere
            ("ERROR: [youtube] xyz: This live event will begin in 2 hours", "live stream"),
            ("ERROR: [youtube] xyz: Premieres in 30 minutes", "live stream"),
            # generic fallback (unknown signature)
            ("ERROR: something totally unexpected happened in yt-dlp internals", "could not fetch"),
            ("", "could not fetch"),
        ],
    )
    def test_signature_maps_to_message(self, stderr: str, expect_substr: str) -> None:
        msg = classify_youtube_error(stderr)
        assert expect_substr.lower() in msg.lower(), f"{stderr!r} → {msg!r}"
        # EVERY message must end with the actionable upload guidance.
        assert self._UPLOAD_GUIDANCE in msg.lower(), f"missing upload guidance: {msg!r}"

    def test_returns_plain_str(self) -> None:
        assert isinstance(classify_youtube_error("anything"), str)

    def test_case_insensitive_signature(self) -> None:
        # Сигнатуры yt-dlp иногда меняют регистр между версиями — матч регистронезависим.
        msg = classify_youtube_error("error: SIGN IN TO CONFIRM YOU'RE NOT A BOT")
        assert "blocked our server" in msg.lower()


class TestBuildYoutubeCmd:
    """Pure-билдер yt-dlp-команды: avc1-first, faststart, match-filter, no-playlist, proxy."""

    def _cmd(self, **kw: object) -> list[str]:
        return build_youtube_cmd("https://youtu.be/x", Path("/d"), **kw)  # type: ignore[arg-type]

    def test_avc1_first_format_le_1080p(self) -> None:
        cmd = self._cmd()
        fmt = cmd[cmd.index("-f") + 1]
        # avc1 (H.264) предпочитается ПЕРВЫМ — софт-декод AV1 в reframe ~2-5× медленнее.
        assert "vcodec^=avc1" in fmt
        assert fmt.index("avc1") < fmt.index("av01") if "av01" in fmt else True
        # Потолок 1080p (reframe-safety + стоимость).
        assert "height<=1080" in fmt

    def test_merge_to_mp4(self) -> None:
        cmd = self._cmd()
        assert cmd[cmd.index("--merge-output-format") + 1] == "mp4"

    def test_no_playlist_guard(self) -> None:
        assert "--no-playlist" in self._cmd()

    def test_faststart_postprocessor_args(self) -> None:
        # moov-atom в начало файла → preview range-requests работают мгновенно (gotcha).
        cmd = self._cmd()
        joined = " ".join(cmd)
        assert "--postprocessor-args" in cmd
        assert "+faststart" in joined

    def test_match_filter_rejects_live_and_overlength(self) -> None:
        cmd = self._cmd()
        mf = cmd[cmd.index("--match-filter") + 1]
        # Отклоняем лайвстримы и слишком длинные видео ДО скачивания.
        assert "is_live" in mf
        assert str(MAX_VIDEO_MINUTES * 60) in mf

    def test_no_proxy_by_default(self) -> None:
        assert "--proxy" not in self._cmd()

    def test_proxy_appended_when_set(self) -> None:
        cmd = self._cmd(proxy="http://1.2.3.4:8080")
        assert cmd[cmd.index("--proxy") + 1] == "http://1.2.3.4:8080"

    def test_cookies_file_takes_priority(self) -> None:
        cmd = self._cmd(cookies_file="/c.txt", cookies_browser="edge")
        assert cmd[cmd.index("--cookies") + 1] == "/c.txt"
        assert "--cookies-from-browser" not in cmd

    def test_cookies_browser_when_no_file(self) -> None:
        cmd = self._cmd(cookies_browser="firefox")
        assert cmd[cmd.index("--cookies-from-browser") + 1] == "firefox"

    def test_url_is_last(self) -> None:
        assert self._cmd()[-1] == "https://youtu.be/x"
