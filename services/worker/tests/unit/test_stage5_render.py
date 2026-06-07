"""Тесты pure-сборки ffmpeg-команды Stage 5 (cut+crop+burn+encode) — тест-первым.

Ключевое (R3, синк субтитров): -ss ДО -i (input seek сбрасывает PTS к 0) + setpts —
иначе subtitles= жжёт по исходному PTS и клип-тайминг .ass не совпадает.
"""

from app.models import CropWindow
from app.pipeline.stage5_render import build_ffmpeg_cmd, build_vf, build_vf_fit


def _crop() -> CropWindow:
    return CropWindow(t=170.0, x=880, y=0, w=608, h=1080)


class TestBuildVf:
    def test_filter_chain(self) -> None:
        vf = build_vf(_crop(), "captions_clip_01.ass")
        assert vf == (
            "crop=608:1080:880:0,scale=1080:1920:flags=lanczos,"
            "setpts=PTS-STARTPTS,subtitles=captions_clip_01.ass"
        )


class TestBuildVfFit:
    def test_fit_preserves_whole_frame_with_blur(self) -> None:
        vf = build_vf_fit("captions_clip_01.ass")
        # split на bg/fg, размытый зум-фон, вписать целиком, overlay по центру, субтитры
        assert "split=2[bg][fg]" in vf
        assert "force_original_aspect_ratio=increase" in vf  # bg заполняет
        assert "gblur" in vf  # фон размыт
        assert "force_original_aspect_ratio=decrease" in vf  # fg целиком, ничего не режет
        assert "overlay=(W-w)/2:(H-h)/2" in vf
        assert "subtitles=captions_clip_01.ass" in vf


class TestBuildCmd:
    def test_ss_before_input_for_pts_reset(self) -> None:
        cmd = build_ffmpeg_cmd("source.mp4", 170.0, 191.6, "VF", "clips/clip_01.mp4")
        assert cmd.index("-ss") < cmd.index("-i")  # input seek → PTS reset → синк субтитров

    def test_duration_via_t(self) -> None:
        cmd = build_ffmpeg_cmd("source.mp4", 170.0, 191.6, "VF", "out.mp4")
        assert "-t" in cmd
        assert "21.6" in cmd  # end - start

    def test_codecs_and_flags(self) -> None:
        cmd = build_ffmpeg_cmd("source.mp4", 170.0, 191.6, "VF", "clips/clip_01.mp4")
        s = " ".join(cmd)
        assert "libx264" in s
        assert "-crf 20" in s
        assert "-preset veryfast" in s
        assert "-pix_fmt yuv420p" in s
        assert "aac" in s
        assert "+faststart" in s

    def test_vf_and_output(self) -> None:
        cmd = build_ffmpeg_cmd("source.mp4", 170.0, 191.6, "MYVF", "out.mp4")
        assert "MYVF" in cmd
        assert cmd[-1] == "out.mp4"
