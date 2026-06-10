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
    # fill→fit mode change: uses xfade instead of video-concat
    assert "xfade=transition=fade" in fc
    assert "[cv]subtitles=captions_clip_01.ass[outv]" in fc
    assert "concat=n=2:v=0:a=1[outa]" in fc
    assert "[bg1]" in fc and "[fg1]" in fc  # fit-лейблы уникальны по индексу сегмента


def test_timeline_cmd_full_input_no_ss():
    cmd = build_timeline_cmd("source.mp4", "FILTER", "clips/clip_01.mp4")
    assert "-ss" not in cmd  # полный вход (не пред-слайс)
    assert cmd[:3] == ["ffmpeg", "-y", "-i"]
    assert "-map" in cmd and "[outv]" in cmd and "[outa]" in cmd
    assert cmd[-1] == "clips/clip_01.mp4"
