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


# ── Named templates (founder's ask: a real template system, not an implicit default) ──────
# Stored in profiles.style_preferences jsonb as:
#   { "templates": [ {"id": str, "name": str, "look": <pref-blob>} ], "default_id": str|None }
# A template's "look" blob is exactly what build_pref_blob/parse_pref produce. The user saves
# named templates and applies one to THIS clip or to ALL clips of a video. One template may be
# flagged default → NEW clips of future jobs seed from it (the "adapt to my style" path),
# but it's EXPLICIT (the user picked it), not a silent every-clip override.


def list_templates(blob: dict[str, Any] | None) -> list[dict[str, Any]]:
    """All saved templates from the prefs blob (newest-first order as stored). PURE."""
    if not isinstance(blob, dict):
        return []
    t = blob.get("templates")
    return [x for x in t if isinstance(x, dict) and x.get("id")] if isinstance(t, list) else []


def default_template_id(blob: dict[str, Any] | None) -> str | None:
    """Id of the template flagged as the new-clip default, or None. PURE."""
    if not isinstance(blob, dict):
        return None
    did = blob.get("default_id")
    return did if isinstance(did, str) and did else None


def build_template(
    template_id: str,
    name: str,
    style: CaptionStyle,
    highlight: HighlightStyle | None,
    hook_style: dict[str, Any] | None,
) -> dict[str, Any]:
    """A clip's current look → a named, storable template. `hook_style` is the look-fields
    dict the client sends (same shape as StylePrefBody.hook_style / apply-style-all). PURE."""
    look: dict[str, Any] = {
        "style": style.model_dump(),
        "highlight": highlight.model_dump() if highlight is not None else None,
        "hook_style": (
            {k: hook_style[k] for k in HOOK_LOOK_FIELDS if k in hook_style}
            if isinstance(hook_style, dict)
            else None
        )
        or None,
    }
    return {"id": template_id, "name": name, "look": look}


def upsert_template(blob: dict[str, Any] | None, template: dict[str, Any]) -> dict[str, Any]:
    """Add (or replace by id) a template; newest goes first. Returns a NEW blob. PURE."""
    out: dict[str, Any] = dict(blob) if isinstance(blob, dict) else {}
    others = [t for t in list_templates(out) if t.get("id") != template["id"]]
    out["templates"] = [template, *others]
    return out


def delete_template(blob: dict[str, Any] | None, template_id: str) -> dict[str, Any]:
    """Remove a template by id; clear default if it pointed there. Returns a NEW blob. PURE."""
    out: dict[str, Any] = dict(blob) if isinstance(blob, dict) else {}
    out["templates"] = [t for t in list_templates(out) if t.get("id") != template_id]
    if out.get("default_id") == template_id:
        out["default_id"] = None
    return out


def set_default_template(blob: dict[str, Any] | None, template_id: str | None) -> dict[str, Any]:
    """Flag a template as the new-clip default (or clear with None). Returns a NEW blob. PURE."""
    out: dict[str, Any] = dict(blob) if isinstance(blob, dict) else {}
    out["default_id"] = template_id
    return out


def get_default_look(
    blob: dict[str, Any] | None,
) -> tuple[CaptionStyle, HighlightStyle | None, dict[str, Any] | None] | None:
    """The default template's look for seeding a NEW clip, or None. Raises ValueError if the
    default template exists but its look is malformed (rule #8: caller logs + preset_a). PURE."""
    did = default_template_id(blob)
    if did is None:
        return None
    for t in list_templates(blob):
        if t.get("id") == did:
            return parse_pref(t.get("look"))
    return None
