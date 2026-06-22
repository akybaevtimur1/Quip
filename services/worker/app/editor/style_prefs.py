"""Style memory (domain 5): apply a saved LOOK to clips + per-user default seed. PURE.

Three levels of style reuse:
  • per-clip      — editing one clip (already exists).
  • per-video     — apply_style_to_edit on every clip of a job ("Apply to all clips").
  • cross-video   — a user saves their look (profiles.style_preferences) → NEW clips of
                    FUTURE jobs seed from it instead of the hardcoded preset_a.

A "look" = caption style + karaoke highlight + hook STYLE fields. Content & position stay
per-clip: replies, caption margin/alignment/free-position, and hook text/enabled/timing are
NEVER overwritten — mirrors apply_preset's position-preserving convention (founder rule).
"""

from __future__ import annotations

from typing import Any

from app.models import CaptionStyle, ClipEdit, HighlightStyle, HookOverlay

# Hook fields that are LOOK (copied by a style). Everything else on HookOverlay is content
# (text/enabled), timing (full_clip/duration_sec) or position (margin_v/pos_*) → preserved.
HOOK_LOOK_FIELDS: tuple[str, ...] = (
    "font",
    "size",
    "color",
    "outline_color",
    "outline_w",
    "shadow",
    "box_color",
    "box_opacity",
    "uppercase",
    "animation",
)


def apply_style_to_edit(
    edit: ClipEdit,
    style: CaptionStyle,
    highlight: HighlightStyle | None,
    hook_look: dict[str, Any] | None,
) -> ClipEdit:
    """Copy a look onto one clip, preserving its content & position. PURE.

    Keeps caption margin_v/alignment/pos_x/pos_y/wrap_width (manual position) and the hook's
    text/enabled/full_clip/duration_sec/margin_v/pos_* — only the look fields change.
    """
    cur = edit.captions.style
    new_style = style.model_copy(
        update={
            "margin_v": cur.margin_v,
            "alignment": cur.alignment,
            "pos_x": cur.pos_x,
            "pos_y": cur.pos_y,
            "wrap_width": cur.wrap_width,
        }
    )
    new_hook = edit.captions.hook
    if new_hook is not None and hook_look:
        look = {k: hook_look[k] for k in HOOK_LOOK_FIELDS if k in hook_look}
        new_hook = new_hook.model_copy(update=look)
    captions = edit.captions.model_copy(
        update={
            "style": new_style,
            "highlight": highlight.model_copy() if highlight is not None else None,
            "hook": new_hook,
        }
    )
    return edit.model_copy(update={"captions": captions})


def build_pref_blob(
    style: CaptionStyle, highlight: HighlightStyle | None, hook: HookOverlay | None
) -> dict[str, Any]:
    """Current clip look → storable preference blob (jsonb in profiles.style_preferences). PURE."""
    return {
        "style": style.model_dump(),
        "highlight": highlight.model_dump() if highlight is not None else None,
        "hook_style": (
            {k: getattr(hook, k) for k in HOOK_LOOK_FIELDS} if hook is not None else None
        ),
    }


def parse_pref(
    blob: dict[str, Any] | None,
) -> tuple[CaptionStyle, HighlightStyle | None, dict[str, Any] | None] | None:
    """Stored preference blob → (style, highlight, hook_look), or None if there is no
    preference. Raises ValueError if a preference EXISTS but is malformed (rule #8: the
    caller logs + falls back to preset_a; we never silently swallow a broken saved style). PURE.
    """
    if not blob or not isinstance(blob, dict) or not blob.get("style"):
        return None
    try:
        style = CaptionStyle.model_validate(blob["style"])
        hl_raw = blob.get("highlight")
        highlight = HighlightStyle.model_validate(hl_raw) if hl_raw else None
    except Exception as e:  # noqa: BLE001 — re-raised as a clear ValueError for the caller
        raise ValueError(f"malformed style preference: {e}") from e
    hook_raw = blob.get("hook_style")
    hook_look = (
        {k: hook_raw[k] for k in HOOK_LOOK_FIELDS if k in hook_raw}
        if isinstance(hook_raw, dict)
        else None
    ) or None
    return style, highlight, hook_look
