"""Domain 5 — style memory: apply-to-all look copy + per-user preference seed. PURE tests."""

from __future__ import annotations

import pytest

from app.editor.replies import default_caption_track
from app.editor.style_prefs import (
    apply_style_to_edit,
    build_pref_blob,
    build_template,
    default_template_id,
    delete_template,
    get_default_look,
    list_templates,
    parse_pref,
    set_default_template,
    upsert_template,
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


def test_apply_style_copies_look_position_keeps_content() -> None:
    """Founder ask: a template now REMEMBERS position + size, so applying it MOVES the
    caption + hook geometry. CONTENT (replies / hook text / intervals) is still preserved."""
    edit = _edit()
    style = CaptionStyle(font="Poppins", size=120, color="#FFFFFF", margin_v=999, pos_x=0.9)
    highlight = HighlightStyle(color="#0000FF", animation="bounce")
    out = apply_style_to_edit(
        edit,
        style,
        highlight,
        {
            "font": "Bebas Neue",
            "size": 70,
            "full_clip": False,
            "duration_sec": 2.0,
            "enabled": False,
            "margin_v": 88,
            "pos_x": 0.25,
            "pos_y": 0.1,
            "wrap_width": 0.7,
        },
    )

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

    # POSITION + SIZE now MOVED by the template (the relaxed founder rule)
    assert out.captions.style.margin_v == 999
    assert out.captions.style.pos_x == 0.9
    assert out.captions.hook.margin_v == 88
    assert out.captions.hook.pos_x == 0.25
    assert out.captions.hook.pos_y == 0.1
    assert out.captions.hook.wrap_width == 0.7
    # hook TIMING now copied by the template
    assert out.captions.hook.full_clip is False
    assert out.captions.hook.duration_sec == 2.0
    assert out.captions.hook.enabled is False
    # content PRESERVED (replies + hook text + intervals untouched)
    assert out.captions.replies[0].text_override == "hi there"
    assert out.captions.hook.text == "My hook"
    assert out.source_intervals == edit.source_intervals


def test_apply_style_old_shape_look_applies_cleanly() -> None:
    """BACK-COMPAT: an OLD saved blob (no new hook keys) must still apply without error —
    absent key = leave that field unchanged (no required-field validation explosion)."""
    edit = _edit()  # hook full_clip=True (default), margin_v=120, enabled=True
    out = apply_style_to_edit(
        edit,
        CaptionStyle(font="Poppins"),
        None,
        {"font": "Bebas Neue", "size": 70},  # legacy hook_style: look fields ONLY
    )
    assert out.captions.hook is not None
    assert out.captions.hook.font == "Bebas Neue"
    assert out.captions.hook.size == 70
    # absent new keys → hook timing/position left exactly as they were
    assert out.captions.hook.full_clip is True
    assert out.captions.hook.duration_sec == 4.0
    assert out.captions.hook.enabled is True
    assert out.captions.hook.margin_v == 120
    assert out.captions.hook.text == "My hook"


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
    # hook_look now carries position/timing too (templates remember everything) — but NEVER text
    assert "text" not in hook_look
    assert hook_look["margin_v"] == 120


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


def test_default_caption_track_seeds_hook_timing_and_position() -> None:
    """A starred default now also carries hook TIMING + POSITION into NEW jobs (founder ask).
    The hook TEXT still comes from the segment (never fabricated by the look)."""
    words = [Word(text="a", start=1.0, end=1.4)]
    intervals = [SourceInterval(source_start=1.0, source_end=5.0)]
    track = default_caption_track(
        words,
        intervals,
        hook="Hooky",
        pref_hook_look={
            "font": "Anton",
            "full_clip": False,
            "duration_sec": 3.0,
            "margin_v": 77,
            "pos_x": 0.2,
        },
    )
    assert track.hook is not None
    assert track.hook.text == "Hooky"  # from the segment, NOT the look
    assert track.hook.font == "Anton"
    assert track.hook.full_clip is False
    assert track.hook.duration_sec == 3.0
    assert track.hook.margin_v == 77
    assert track.hook.pos_x == 0.2


def test_default_caption_track_falls_back_to_preset_a() -> None:
    from app.editor.preset_seeds import DEFAULT_PRESET_ID, seed_presets

    words = [Word(text="a", start=1.0, end=1.4)]
    intervals = [SourceInterval(source_start=1.0, source_end=5.0)]
    track = default_caption_track(words, intervals, hook=None)
    preset_a = next(p for p in seed_presets() if p.id == DEFAULT_PRESET_ID)
    assert track.style.font == preset_a.style.font
    assert track.style.size == preset_a.style.size


# ── named templates (founder's template system) ──────────────────────────────────────────


def test_build_template_carries_look_only() -> None:
    t = build_template(
        "t1",
        "Bold",
        CaptionStyle(font="Anton", size=80, color="#FF0000"),
        HighlightStyle(color="#00FF00", animation="pop"),
        {"font": "Rubik", "size": 50, "text": "ignored", "margin_v": 999},
    )
    assert t["id"] == "t1" and t["name"] == "Bold"
    assert t["look"]["style"]["font"] == "Anton"
    assert t["look"]["highlight"]["animation"] == "pop"
    # hook_style keeps look + position/timing (templates remember everything) but DROPS text
    assert t["look"]["hook_style"]["font"] == "Rubik"
    assert t["look"]["hook_style"]["margin_v"] == 999
    assert "text" not in t["look"]["hook_style"]


def test_template_crud_newest_first_and_upsert_by_id() -> None:
    t1 = build_template("t1", "Bold", CaptionStyle(font="Anton"), None, None)
    t2 = build_template("t2", "Clean", CaptionStyle(font="Poppins"), None, None)
    blob = upsert_template(upsert_template(None, t1), t2)
    assert [t["id"] for t in list_templates(blob)] == ["t2", "t1"]  # newest first
    # upsert replaces by id (no dup), moves it to front
    t1b = build_template("t1", "Bold v2", CaptionStyle(font="Bebas Neue"), None, None)
    blob = upsert_template(blob, t1b)
    assert [t["id"] for t in list_templates(blob)] == ["t1", "t2"]
    assert next(t for t in list_templates(blob) if t["id"] == "t1")["name"] == "Bold v2"


def test_default_flag_seed_and_delete_clears_default() -> None:
    t1 = build_template("t1", "Bold", CaptionStyle(font="Bebas Neue", size=99), None, None)
    blob = upsert_template(None, t1)
    assert default_template_id(blob) is None and get_default_look(blob) is None
    blob = set_default_template(blob, "t1")
    assert default_template_id(blob) == "t1"
    look = get_default_look(blob)
    assert look is not None and look[0].font == "Bebas Neue" and look[0].size == 99
    # deleting the default template clears the default pointer
    blob = delete_template(blob, "t1")
    assert list_templates(blob) == []
    assert default_template_id(blob) is None and get_default_look(blob) is None


def test_get_default_look_malformed_raises() -> None:
    blob = {
        "templates": [{"id": "x", "name": "bad", "look": {"style": {"size": "nope", "color": 1}}}],
        "default_id": "x",
    }
    with pytest.raises(ValueError):
        get_default_look(blob)


def test_list_templates_handles_garbage() -> None:
    assert list_templates(None) == []
    assert list_templates({"templates": "nope"}) == []
    assert list_templates({"templates": [{"no_id": 1}, {"id": "ok"}]}) == [{"id": "ok"}]
