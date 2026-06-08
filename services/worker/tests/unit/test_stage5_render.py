"""Тесты pure-сборки рендера Stage 5 (ОДИН проход: trim по кадрам + concat-фильтр) — тест-первым.

Ключевое: аудио НЕ режем (continuous -map 0:a → нет подлагов); видео-кроп режем trim ПО КАДРАМ
(frame-exact) от выровненного на границу кадра старта → кроп меняется ровно на склейке (нет
чёрных кадров). Заменили нарезку на файлы + concat-демуксер (давал подлаг аудио + чёрные кадры).
"""

import pytest

from app.errors import JobError
from app.pipeline.stage3_reframe import ShotPlan
from app.pipeline.stage5_render import build_reframe_filter, build_single_pass_cmd


class TestBuildReframeFilter:
    """filter_complex: split → per-shot trim по кадрам + crop/fit → concat → burn субтитров."""

    def test_single_fill_shot(self) -> None:
        fc = build_reframe_filter([ShotPlan(0.0, 5.0, "fill", 0.5)], 1920, 1080, 24.0, "cap.ass")
        assert "[0:v]setpts=PTS-STARTPTS,split=1[a0];" in fc
        assert "trim=start_frame=0:end_frame=120" in fc  # 5.0*24 = 120
        assert "crop=608:1080:656:0" in fc  # center 0.5 → x=656, w=608
        assert "scale=1080:1920:flags=lanczos" in fc
        assert "concat=n=1:v=1[cv];[cv]subtitles=cap.ass[outv]" in fc

    def test_trim_is_frame_exact_not_seconds(self) -> None:
        # t0=2.12, fps=24 → start_frame=round(50.88)=51 (целый кадр, не дробные секунды)
        shots = [ShotPlan(0.0, 2.12, "fill", 0.3), ShotPlan(2.12, 5.0, "fill", 0.7)]
        fc = build_reframe_filter(shots, 1920, 1080, 24.0, "c.ass")
        assert "trim=start_frame=0:end_frame=51" in fc
        assert "trim=start_frame=51:end_frame=120" in fc
        assert "concat=n=2:v=1" in fc

    def test_fit_shot_is_blur_overlay(self) -> None:
        fc = build_reframe_filter([ShotPlan(0.0, 5.0, "fit", None)], 1920, 1080, 24.0, "c.ass")
        assert "gblur" in fc
        assert "overlay=(W-w)/2:(H-h)/2" in fc

    def test_segments_normalize_sar(self) -> None:
        # concat требует одинаковый SAR у всех сегментов (fill/fit дают разный) → setsar=1 на каждом
        shots = [ShotPlan(0.0, 2.0, "fill", 0.3), ShotPlan(2.0, 5.0, "fit", None)]
        fc = build_reframe_filter(shots, 1920, 1080, 24.0, "c.ass")
        assert fc.count("setsar=1") == 2

    def test_fit_labels_unique_per_shot(self) -> None:
        # лейблы blur уникальны по шоту (иначе коллизия на 2+ fit-шотах)
        shots = [ShotPlan(0.0, 2.0, "fit", None), ShotPlan(2.0, 5.0, "fit", None)]
        fc = build_reframe_filter(shots, 1920, 1080, 24.0, "c.ass")
        assert "[bg0]" in fc and "[bg1]" in fc

    def test_fill_without_center_raises(self) -> None:
        with pytest.raises(JobError):
            build_reframe_filter([ShotPlan(0.0, 5.0, "fill", None)], 1920, 1080, 24.0, "c.ass")

    def test_empty_raises(self) -> None:
        with pytest.raises(JobError):
            build_reframe_filter([], 1920, 1080, 24.0, "c.ass")


class TestBuildSinglePassCmd:
    """ffmpeg: -ss ДО -i, filter_complex, видео [outv] + аудио непрерывным 0:a (нет подлагов)."""

    def test_ss_before_input(self) -> None:
        cmd = build_single_pass_cmd("source.mp4", 24.75, 31.57, "FC", "clips/clip_01.mp4")
        assert cmd.index("-ss") < cmd.index("-i")

    def test_filter_and_maps(self) -> None:
        cmd = build_single_pass_cmd("source.mp4", 24.75, 31.57, "FC", "out.mp4")
        s = " ".join(cmd)
        assert "-filter_complex FC" in s
        assert "-map [outv]" in s
        assert "-map 0:a" in s  # аудио единым потоком — НЕ режем

    def test_codecs_and_output(self) -> None:
        cmd = build_single_pass_cmd("source.mp4", 24.75, 31.57, "FC", "clips/clip_01.mp4")
        s = " ".join(cmd)
        assert "libx264" in s
        assert "-crf 20" in s
        assert "aac" in s
        assert "+faststart" in s
        assert cmd[-1] == "clips/clip_01.mp4"
