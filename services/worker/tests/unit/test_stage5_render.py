"""Тесты pure-сборки ffmpeg-команды Stage 5 (cut+crop+burn+encode) — тест-первым.

Ключевое (R3, синк субтитров): -ss ДО -i (input seek сбрасывает PTS к 0) + setpts —
иначе subtitles= жжёт по исходному PTS и клип-тайминг .ass не совпадает.
"""

from app.models import CropWindow
from app.pipeline.stage5_render import (
    build_crop_x_expr,
    build_ffmpeg_cmd,
    build_vf,
    build_vf_dynamic,
    build_vf_fit,
)


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


class TestBuildCropXExpr:
    """Time-varying x для динамического кропа: 1 кф → константа, N → кусочно-линейно."""

    def test_single_keyframe_is_constant(self) -> None:
        assert build_crop_x_expr([(0.0, 656)]) == "656"

    def test_two_keyframes_linear_interp(self) -> None:
        # между t=0 и t=2 линейная интерполяция x: 100→300; после t=2 держим 300
        expr = build_crop_x_expr([(0.0, 100), (2.0, 300)])
        assert expr == "if(lt(t,2.0),(100+(300-100)*(t-0.0)/(2.0-0.0)),300)"

    def test_three_keyframes_nested(self) -> None:
        expr = build_crop_x_expr([(0.0, 100), (1.0, 200), (2.0, 150)])
        # вложенные if: сначала [0,1), потом [1,2), иначе последний x (две закрывающие скобки)
        assert expr.startswith("if(lt(t,1.0),")
        assert "if(lt(t,2.0)," in expr
        assert expr.endswith(",150))")

    def test_empty_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            build_crop_x_expr([])


class TestBuildVfDynamic:
    """FILL-динамика: setpts ПЕРВЫМ (crop.t = клип-время 0-based), запятые в expr экранированы."""

    def _crops(self) -> list[CropWindow]:
        return [
            CropWindow(t=0.0, x=100, y=0, w=608, h=1080),
            CropWindow(t=2.0, x=300, y=0, w=608, h=1080),
        ]

    def test_setpts_first_then_dynamic_crop(self) -> None:
        vf = build_vf_dynamic(self._crops(), "captions_clip_01.ass")
        # setpts ДО crop → crop видит 0-based t (синхрон с клип-таймингами)
        assert vf.startswith("setpts=PTS-STARTPTS,crop=608:1080:")
        assert vf.index("setpts") < vf.index("crop=")

    def test_commas_in_expr_escaped_for_filtergraph(self) -> None:
        vf = build_vf_dynamic(self._crops(), "c.ass")
        # запятые в if(...) экранированы \, — иначе filtergraph съест их как разделители фильтров
        assert "lt(t\\,2.0)" in vf
        assert "lt(t,2.0)" not in vf  # неэкранированной запятой в выражении быть не должно

    def test_chain_has_scale_and_subtitles(self) -> None:
        vf = build_vf_dynamic(self._crops(), "captions_clip_01.ass")
        assert "scale=1080:1920:flags=lanczos" in vf
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
