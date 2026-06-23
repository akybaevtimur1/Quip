from app.models import SourceInterval
from app.pipeline.stage3_reframe import TrackPoint, TrackRegion
from app.pipeline.stage5_render import build_timeline_cmd, build_timeline_filter, flatten_timeline

SRC_W, SRC_H, FPS = 1920, 1080, 25.0


def _fill(t0, t1, cx):
    return TrackRegion(t0=t0, t1=t1, mode="fill", points=(TrackPoint(t=t0, mode="fill", cx=cx),))


def _fit(t0, t1):
    return TrackRegion(t0=t0, t1=t1, mode="fit", points=())


def test_flatten_maps_to_source_frames():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    regions = [[_fill(0.0, 2.0, 0.5)]]
    segs = flatten_timeline(intervals, regions, FPS)
    assert len(segs) == 1
    assert segs[0].src_f0 == round(10.0 * FPS)  # 250
    assert segs[0].src_f1 == round(12.0 * FPS)  # 300
    assert segs[0].mode == "fill"


def test_filter_two_segments_fill_then_fit():
    intervals = [
        SourceInterval(source_start=10.0, source_end=12.0),
        SourceInterval(source_start=30.0, source_end=31.0),
    ]
    regions = [[_fill(0.0, 2.0, 0.5)], [_fit(0.0, 1.0)]]
    segs = flatten_timeline(intervals, regions, FPS)
    fc = build_timeline_filter(segs, SRC_W, SRC_H, FPS, "captions_clip_01.ass")
    assert "split=2" in fc and "asplit=2" in fc
    assert "trim=start_frame=250:end_frame=300" in fc
    assert "trim=start_frame=750:end_frame=775" in fc
    assert "atrim=start=10.000:end=12.000" in fc
    # fill→fit mode change: жёсткий cut (concat), без xfade
    assert "xfade" not in fc
    assert "concat=n=2:v=1:a=0" in fc
    assert "[cv]subtitles=captions_clip_01.ass[outv]" in fc
    assert "concat=n=2:v=0:a=1[outa]" in fc
    assert "[bg1]" in fc and "[fg1]" in fc  # fit-лейблы уникальны по индексу сегмента


def test_flatten_preserves_points_b():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    split = TrackRegion(
        t0=0.0,
        t1=2.0,
        mode="split",
        points=(TrackPoint(t=0.0, mode="split", cx=0.2),),
        points_b=(TrackPoint(t=0.0, mode="split", cx=0.8),),
    )
    segs = flatten_timeline(intervals, [[split]], FPS)
    assert segs[0].mode == "split"
    assert segs[0].points_b and segs[0].points_b[0].cx == 0.8


def test_filter_split_segment_vstack():
    intervals = [SourceInterval(source_start=10.0, source_end=12.0)]
    split = TrackRegion(
        t0=0.0,
        t1=2.0,
        mode="split",
        points=(TrackPoint(t=0.0, mode="split", cx=0.2),),
        points_b=(TrackPoint(t=0.0, mode="split", cx=0.8),),
    )
    fc = build_timeline_filter(flatten_timeline(intervals, [[split]], FPS), SRC_W, SRC_H, FPS, None)
    assert "vstack=inputs=2" in fc
    assert "scale=1080:960" in fc


def test_timeline_cmd_full_input_no_ss():
    cmd = build_timeline_cmd("source.mp4", "FILTER", "clips/clip_01.mp4")
    assert "-ss" not in cmd  # полный вход (не пред-слайс)
    assert cmd[:3] == ["ffmpeg", "-y", "-i"]
    assert "-map" in cmd and "[outv]" in cmd and "[outa]" in cmd
    assert cmd[-1] == "clips/clip_01.mp4"


def test_flatten_aligns_boundary_to_native_cut_frame_non25fps():
    """Regression — мульти-интервальный editor-флеш (REFRAME_FPS_GRID_INVARIANT, editor-путь).

    flatten_timeline ОБЯЗАН якорить source-кадры на тот же aligned origin, что reframe_segment
    (round(source_start*fps)/fps), а НЕ на сырой source_start. Реальная склейка на относительном
    кадре 23 у 23.976fps-клипа с интервалом, начинающимся НЕ на границе кадра (0.146с), должна
    лечь на ИСТИННЫЙ нативный кадр round(0.146*fps)+23 — ровно как одно-интервальный render_clip.
    Старый код (сырой source_start + округление до 3 знаков) клал на кадр раньше → флеш в 1 кадр.
    """
    fps = 23.976
    cut = 23
    t0 = cut / fps
    intervals = [
        SourceInterval(source_start=0.146, source_end=5.0),
        SourceInterval(source_start=30.0, source_end=31.0),
    ]
    regions = [[_fill(0.0, t0, 0.5), _fit(t0, 2.0)], [_fit(0.0, 1.0)]]
    segs = flatten_timeline(intervals, regions, fps)
    truth = round(0.146 * fps) + cut  # = 27; ровно туда садится render_clip
    assert segs[1].src_f0 == truth  # был 26 (на кадр раньше) до фикса
    assert segs[0].src_f1 == truth  # смежная граница держится на реальной склейке


def test_flatten_frame_grid_invariant_across_fps():
    """Δ=0 кадровая сетка timeline-пути на КАЖДОМ fps + off-grid старте.

    Та самая матрица фикстур, за которой прятался баг: 25fps + целые старты всегда удовлетворяли
    сломанному допущению. На любом f(ps) и любом 3-десятичном source_start кадр границы региона
    обязан равняться round(source_start*fps)+round(t*fps) — абсолютному кадру, на который садится
    render_clip (-ss aligned_start + trim round(t*fps)).
    """
    for fps in (23.976, 24.0, 25.0, 29.97, 30.0, 59.94, 60.0):
        for source_start in (0.146, 4.788, 17.35, 33.337):
            for cut in (0, 7, 50, 101, 499):
                t0 = cut / fps
                t1 = t0 + 1.0
                iv = SourceInterval(source_start=source_start, source_end=source_start + t1 + 1.0)
                segs = flatten_timeline([iv], [[_fill(t0, t1, 0.5)]], fps)
                base = round(source_start * fps)
                assert segs[0].src_f0 == base + round(t0 * fps), (fps, source_start, cut)
                assert segs[0].src_f1 == base + round(t1 * fps), (fps, source_start, cut)
