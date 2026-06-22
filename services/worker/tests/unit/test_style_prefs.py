"""Domain 5 — style memory: apply-to-all look copy + per-user preference seed. PURE tests."""

from __future__ import annotations

import pytest

from app.editor.replies import default_caption_track
from app.editor.style_prefs import (
    apply_style_to_edit,
    build_pref_blob,
    parse_pref,
)
from app.models import (
    CaptionReply,
    CaptionStyle,
    CaptionTrack,
    ClipEdit,
    HighlightStyle,
    HookOverlay,
    SourceInterval,
    Word,
)


def _edit() -> ClipEdit:
    return ClipEdit(
        id="clip_01",
        version=3,
        source_intervals=[SourceInterval(source_start=1.0, source_end=5.0)],
        captions=CaptionTrack(
            style=CaptionStyle(font="Anton", size=80, color="#FF0000", margin_v=300, pos_x=0.4),
            highlight=HighlightStyle(color="#00FF00", animation="pop"),
            replies=[CaptionReply(word_refs=[0, 1], text_override="hi there")],
            hook=HookOverlay(text="My hook", enabled=True, font="Rubik", size=50, margin_v=120),
        ),
    )


def test_apply_style_copies_look_keeps_content_and_position() -> None:
    edit = _edit()
    style = CaptionStyle(font="Poppins", size=120, color="#FFFFFF", margin_v=999, pos_x=0.9)
    highlight = HighlightStyle(color="#0000FF", animation="bounce")
    out = apply_style_to_edit(edit, style, highlight, {"font": "Bebas Neue", "size": 70})

    # look copied
    assert out.captions.style.font == "Poppins"
    assert out.captions.style.size == 120
    assert out.captions.style.color == "#FFFFFF"
    assert out.captions.highlight is not None
    assert out.captions.highlight.color == "#0000FF"
    assert out.captions.highlight.animation == "bounce"
    # hook look copied
    assert out.captions.hook is not None
    assert out.captions.hook.font == "Bebas Neue"
    assert out.captions.hook.size == 70

    # position PRESERVED (per-clip manual position is never overwritten by a style)
    assert out.captions.style.margin_v == 300
    assert out.captions.style.pos_x == 0.4
    assert out.captions.hook.margin_v == 120
    # content PRESERVED (replies + hook text + intervals untouched)
    assert out.captions.replies[0].text_override == "hi there"
    assert out.captions.hook.text == "My hook"
    assert out.captions.hook.enabled is True
    assert out.source_intervals == edit.source_intervals


def test_apply_style_highlight_none_clears_karaoke() -> None:
    out = apply_style_to_edit(_edit(), CaptionStyle(), None, None)
    assert out.captions.highlight is None


def test_apply_style_no_hook_is_noop_on_hook() -> None:
    edit = _edit().model_copy(
        update={"captions": _edit().captions.model_copy(update={"hook": None})}
    )
    out = apply_style_to_edit(edit, CaptionStyle(font="Poppins"), None, {"font": "Anton"})
    assert out.captions.hook is None  # no hook to style → stays None


def test_build_pref_blob_roundtrips_through_parse() -> None:
    edit = _edit()
    blob = build_pref_blob(edit.captions.style, edit.captions.highlight, edit.captions.hook)
    parsed = parse_pref(blob)
    assert parsed is not None
    style, highlight, hook_look = parsed
    assert style.font == "Anton"
    assert style.color == "#FF0000"
    assert highlight is not None and highlight.animation == "pop"
    assert hook_look is not None and hook_look["font"] == "Rubik"
    # hook_look carries ONLY look fields, not text/position
    assert "text" not in hook_look
    assert "margin_v" not in hook_look


def test_parse_pref_absent_returns_none() -> None:
    assert parse_pref(None) is None
    assert parse_pref({}) is None
    assert parse_pref({"highlight": {"color": "#fff"}}) is None  # no style → treated as absent


def test_parse_pref_malformed_raises() -> None:
    with pytest.raises(ValueError):
        parse_pref({"style": {"size": "not-an-int", "color": 123}})


def test_default_caption_track_seeds_from_preference() -> None:
    words = [Word(text="a", start=1.0, end=1.4), Word(text="b", start=1.5, end=1.9)]
    intervals = [SourceInterval(source_start=1.0, source_end=5.0)]
    pref_style = CaptionStyle(font="Luckiest Guy", size=111, color="#123456")
    track = default_caption_track(
        words, intervals, hook="Hooky", pref_style=pref_style, pref_hook_look={"font": "Anton"}
    )
    assert track.style.font == "Luckiest Guy"
    assert track.style.size == 111
    assert track.hook is not None
    assert track.hook.text == "Hooky"
    assert track.hook.font == "Anton"  # hook look from preference


def test_default_caption_track_falls_back_to_preset_a() -> None:
    from app.editor.preset_seeds import DEFAULT_PRESET_ID, seed_presets

    words = [Word(text="a", start=1.0, end=1.4)]
    intervals = [SourceInterval(source_start=1.0, source_end=5.0)]
    track = default_caption_track(words, intervals, hook=None)
    preset_a = next(p for p in seed_presets() if p.id == DEFAULT_PRESET_ID)
    assert track.style.font == preset_a.style.font
    assert track.style.size == preset_a.style.size
