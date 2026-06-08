"""Тесты pure-сборки ffmpeg-команды Stage 5 (cut+crop+burn+encode) — тест-первым.

Ключевое (R3, синк субтитров): -ss ДО -i (input seek сбрасывает PTS к 0) + setpts —
иначе subtitles= жжёт по исходному PTS и клип-тайминг .ass не совпадает.
"""

import pytest

from app.errors import JobError
from app.models import CropWindow
from app.pipeline.stage5_render import (
    build_concat_burn_cmd,
    build_concat_list,
    build_crop_x_step_expr,
    build_ffmpeg_cmd,
    build_vf,
    build_vf_dynamic,
    build_vf_fill,
    build_vf_fit,
    build_vf_fit_shot,
)


def _crop() -> CropWindow:
    return CropWindow(t=170.0, x=880, y=0, w=608, h=1080)


class TestBuildVfFill:
    """Per-shot FILL (R1.3): crop+scale+setpts БЕЗ субтитров (их жжём после concat)."""

    def test_crop_scale_setpts_no_subtitles(self) -> None:
        vf = build_vf_fill(_crop())
        assert vf == "crop=608:1080:880:0,scale=1080:1920:flags=lanczos,setpts=PTS-STARTPTS"
        assert "subtitles" not in vf


class TestBuildVfFitShot:
    """Per-shot FIT (R1.3): весь кадр + блюр-рамки БЕЗ субтитров (b-roll показываем широко)."""

    def test_fit_no_subtitles(self) -> None:
        vf = build_vf_fit_shot()
        assert "split=2[bg][fg]" in vf
        assert "force_original_aspect_ratio=increase" in vf
        assert "gblur" in vf
        assert "force_original_aspect_ratio=decrease" in vf
        assert "overlay=(W-w)/2:(H-h)/2" in vf
        assert "subtitles" not in vf  # субтитры — отдельным проходом после concat


class TestBuildConcatList:
    """Контент файла-списка для ffmpeg concat-демуксера."""

    def test_one_file_per_line(self) -> None:
        out = build_concat_list(["_shot_clip_01_00.mp4", "_shot_clip_01_01.mp4"])
        assert out == "file '_shot_clip_01_00.mp4'\nfile '_shot_clip_01_01.mp4'\n"

    def test_empty_raises(self) -> None:
        with pytest.raises(JobError):
            build_concat_list([])


class TestBuildConcatBurnCmd:
    """Финальный проход: concat-демуксер шотов + burn субтитров (один re-encode видео)."""

    def test_demuxer_subtitles_and_output(self) -> None:
        cmd = build_concat_burn_cmd(
            "_concat_clip_01.txt", "captions_clip_01.ass", "clips/clip_01.mp4"
        )
        s = " ".join(cmd)
        assert "-f concat" in s
        assert "-safe 0" in s  # относительные пути в списке разрешены
        assert "-i _concat_clip_01.txt" in s
        assert "subtitles=captions_clip_01.ass" in s
        assert "libx264" in s
        assert "-crf 20" in s
        assert cmd[-1] == "clips/clip_01.mp4"


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


class TestBuildCropXStepExpr:
    """Ступенчатое x(t): константа внутри плана, мгновенный скачок на границе (hold & cut)."""

    def test_single_is_constant(self) -> None:
        assert build_crop_x_step_expr([(0.0, 656)]) == "656"

    def test_two_shots_step(self) -> None:
        # x держится 100 до t=2, затем мгновенно 300 (НЕ интерполяция)
        assert build_crop_x_step_expr([(0.0, 100), (2.0, 300)]) == "if(lt(t,2.0),100,300)"

    def test_three_shots_nested_step(self) -> None:
        expr = build_crop_x_step_expr([(0.0, 100), (2.0, 300), (5.0, 200)])
        assert expr == "if(lt(t,2.0),100,if(lt(t,5.0),300,200))"

    def test_collapses_consecutive_equal_x(self) -> None:
        # соседние планы с одинаковым x → без лишнего скачка (граница уезжает на смену x)
        expr = build_crop_x_step_expr([(0.0, 100), (2.0, 100), (5.0, 300)])
        assert expr == "if(lt(t,5.0),100,300)"

    def test_empty_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            build_crop_x_step_expr([])


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
