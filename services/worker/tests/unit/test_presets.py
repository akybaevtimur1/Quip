from app.editor.defaults import default_clip_edit
from app.editor.presets import apply_preset
from app.models import CaptionPreset, CaptionStyle, HighlightStyle, Segment, Word


def test_apply_preset_sets_style_and_highlight():
    words = [Word(text="a", start=0.0, end=0.4)]
    edit = default_clip_edit(
        "clip_01",
        Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook"),
        words,
    )
    preset = CaptionPreset(
        id="p1",
        name="Hormozi",
        style=CaptionStyle(color="#00FF00", size=120),
        highlight=HighlightStyle(color="#FF00FF"),
    )
    out = apply_preset(edit, preset)
    assert out.captions.style.color == "#00FF00" and out.captions.style.size == 120
    assert out.captions.highlight is not None and out.captions.highlight.color == "#FF00FF"
    # replies untouched
    assert out.captions.replies == edit.captions.replies
