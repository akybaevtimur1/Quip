import pytest

from app.editor.timemap import ClipTimeMap
from app.errors import JobError
from app.models import SourceInterval


def _iv(a, b):
    return SourceInterval(source_start=a, source_end=b)


def test_single_interval():
    m = ClipTimeMap([_iv(10.0, 20.0)])
    assert m.clip_duration == 10.0
    assert m.source_to_clip(10.0) == 0.0
    assert m.source_to_clip(15.0) == 5.0
    assert m.source_to_clip(20.0) is None  # полуинтервал [start, end)
    assert m.clip_to_source(0.0) == (0, 10.0)
    assert m.clip_to_source(5.0) == (0, 15.0)
    assert m.interval_clip_band(0) == (0.0, 10.0)


def test_two_intervals_with_gap():
    m = ClipTimeMap([_iv(10.0, 20.0), _iv(30.0, 35.0)])  # дырка 20..30
    assert m.clip_duration == 15.0
    assert m.source_to_clip(19.0) == 9.0
    assert m.source_to_clip(25.0) is None  # в дырке
    assert m.source_to_clip(30.0) == 10.0
    assert m.source_to_clip(34.0) == 14.0
    assert m.clip_to_source(12.0) == (1, 32.0)
    assert m.interval_clip_band(1) == (10.0, 15.0)


def test_add_section_out_of_source_order():
    # интервал из ПОЗЖЕ по source стоит РАНЬШЕ в клипе (add-section)
    m = ClipTimeMap([_iv(30.0, 35.0), _iv(10.0, 20.0)])
    assert m.clip_duration == 15.0
    assert m.source_to_clip(32.0) == 2.0
    assert m.source_to_clip(15.0) == 10.0


def test_empty_raises():
    with pytest.raises(JobError):
        ClipTimeMap([])
