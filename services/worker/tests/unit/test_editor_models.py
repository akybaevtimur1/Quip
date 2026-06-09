from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    ClipEdit,
    CropOverride,
    HighlightStyle,
    SourceInterval,
)


def test_clip_edit_defaults():
    edit = ClipEdit(
        id="clip_01",
        source_intervals=[SourceInterval(source_start=10.0, source_end=25.0)],
        captions=CaptionTrack(style=CaptionStyle(), highlight=HighlightStyle(), replies=[]),
    )
    assert edit.version == 1
    assert edit.aspect == "9:16"
    assert edit.reframe_overrides == []
    assert edit.source_intervals[0].source_end == 25.0
    assert edit.captions.style.font == "Montserrat"
    assert edit.captions.style.uppercase is True
    assert edit.captions.highlight.color == "#FFE000"


def test_caption_reply_and_override():
    r = CaptionReply(word_refs=[3, 4, 5])
    assert r.text_override is None and r.hidden is False
    ov = CropOverride(source_start=1.0, source_end=2.0, mode="fill", center=0.7)
    assert ov.mode == "fill" and ov.center == 0.7
