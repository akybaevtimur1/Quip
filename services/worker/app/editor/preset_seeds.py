"""Seed caption style presets (UI gallery, default A). Pure data.

Single source of truth for backend (ASS export) and frontend (CSS preview).
Served via GET /presets endpoint. See docs/superpowers/specs/2026-06-11-editor-v2-design.md.
"""

from __future__ import annotations

from app.models import CaptionPreset, CaptionStyle, HighlightStyle

DEFAULT_PRESET_ID = "preset_a"


def seed_presets() -> list[CaptionPreset]:
    """21 built-in presets. IDs are stable (preset_a..preset_u), A is default."""
    return [
        CaptionPreset(
            id="preset_a",
            name="Active Word",
            # Дефолт = вирусный стандарт (OpusClip/Submagic): активное слово вспыхивает
            # кораллом + подскок (pop) РОВНО в момент произнесения. box=False — per-word
            # плашка в libass не рисуется (нет примитива фона под спан), не обещаем её.
            style=CaptionStyle(size=84, color="#FFFFFF", outline_color="#000000", outline_w=7),
            highlight=HighlightStyle(color="#FF5A3D", scale=1.0, box=False, animation="pop"),
        ),
        CaptionPreset(
            id="preset_b",
            name="Color Word",
            style=CaptionStyle(size=84, color="#FFFFFF", outline_color="#000000", outline_w=8),
            highlight=HighlightStyle(color="#FFD23D", scale=1.0, box=False),
        ),
        CaptionPreset(
            id="preset_c",
            name="Hormozi",
            style=CaptionStyle(size=120, color="#FFFFFF", outline_color="#000000", outline_w=12),
            highlight=HighlightStyle(color="#34E36B", scale=1.15, box=False),
        ),
        CaptionPreset(
            id="preset_d",
            name="Clean Line",
            style=CaptionStyle(
                size=76, color="#FFFFFF", outline_color="#000000", outline_w=4, shadow=4
            ),
            highlight=None,
        ),
        CaptionPreset(
            id="preset_e",
            name="MrBeast",
            style=CaptionStyle(size=110, color="#FFE000", outline_color="#000000", outline_w=8),
            highlight=HighlightStyle(color="#FF3B30", scale=1.1, box=False, animation="pop"),
        ),
        CaptionPreset(
            id="preset_f",
            name="Neon",
            style=CaptionStyle(
                size=92, color="#E9FBFF", outline_color="#0FD9FF", outline_w=4, shadow=4
            ),
            highlight=HighlightStyle(color="#0FD9FF", scale=1.0, box=False),
        ),
        CaptionPreset(
            id="preset_g",
            name="Minimal",
            style=CaptionStyle(
                size=64,
                color="#FFFFFF",
                outline_color="#000000",
                outline_w=2,
                shadow=1,
                uppercase=False,
            ),
            highlight=None,
        ),
        CaptionPreset(
            id="preset_h",
            name="Podcast",
            style=CaptionStyle(
                size=78,
                color="#FFFFFF",
                outline_color="#000000",
                outline_w=0,
                shadow=0,
                box_color="#000000",
                box_opacity=0.55,
                margin_v=1100,
            ),
            highlight=HighlightStyle(color="#FFD23D", scale=1.0, box=False),
        ),
        CaptionPreset(
            id="preset_i",
            name="Karaoke Green",
            style=CaptionStyle(size=90, color="#FFFFFF", outline_color="#000000", outline_w=6),
            highlight=HighlightStyle(color="#34E36B", scale=1.0, box=True),
        ),
        CaptionPreset(
            id="preset_j",
            name="Bold White",
            style=CaptionStyle(size=118, color="#FFFFFF", outline_color="#000000", outline_w=9),
            highlight=HighlightStyle(color="#FFFFFF", scale=1.15, box=False, animation="bounce"),
        ),
        CaptionPreset(
            id="preset_k",
            name="Outline Pop",
            style=CaptionStyle(size=96, color="#FFFFFF", outline_color="#FF5A3D", outline_w=5),
            highlight=HighlightStyle(color="#FF5A3D", scale=1.0, box=False, animation="pop"),
        ),
        CaptionPreset(
            id="preset_l",
            name="Lower Third",
            style=CaptionStyle(
                size=58,
                color="#FFFFFF",
                outline_color="#000000",
                outline_w=0,
                shadow=0,
                box_color="#1C1813",
                box_opacity=0.7,
                margin_v=120,
                uppercase=False,
            ),
            highlight=None,
        ),
        CaptionPreset(
            id="preset_m",
            name="Pop Words",
            # T3: авто-подсветка ключевых слов (числа + длинные контентные) коралл-акцентом,
            # без караоке → чистый белый с «выстреливающими» словами (стиль OpusClip/Hormozi).
            style=CaptionStyle(
                size=96,
                color="#FFFFFF",
                outline_color="#000000",
                outline_w=7,
                emphasis_color="#FF5A3D",
            ),
            highlight=None,
        ),
        CaptionPreset(
            id="preset_n",
            name="Anton Bold",
            style=CaptionStyle(
                font="Anton", size=120, color="#FFFFFF", outline_color="#000000", outline_w=12
            ),
            highlight=HighlightStyle(color="#34E36B", scale=1.15, box=False, animation="drop_in"),
        ),
        CaptionPreset(
            id="preset_o",
            name="Beasty Yellow",
            style=CaptionStyle(
                font="Archivo Black",
                size=110,
                color="#FFE000",
                outline_color="#000000",
                outline_w=9,
            ),
            highlight=HighlightStyle(color="#FF3B30", scale=1.1, box=False, animation="punch"),
        ),
        CaptionPreset(
            id="preset_p",
            name="Bold Pop White",
            style=CaptionStyle(
                font="Poppins", size=116, color="#FFFFFF", outline_color="#000000", outline_w=9
            ),
            highlight=HighlightStyle(color="#FFFFFF", scale=1.18, box=False, animation="bounce"),
        ),
        CaptionPreset(
            id="preset_q",
            name="Bebas Condensed",
            style=CaptionStyle(
                font="Bebas Neue", size=130, color="#FFFFFF", outline_color="#000000", outline_w=8
            ),
            highlight=HighlightStyle(color="#FFD23D", scale=1.0, box=False, animation="pop"),
        ),
        CaptionPreset(
            id="preset_r",
            name="Karaoke Fill",
            style=CaptionStyle(
                font="Montserrat", size=88, color="#FFFFFF", outline_color="#000000", outline_w=7
            ),
            highlight=HighlightStyle(
                color="#FFE000", scale=1.0, box=False, animation="karaoke_fill"
            ),
        ),
        CaptionPreset(
            id="preset_s",
            name="Highlight Box",
            style=CaptionStyle(
                font="Montserrat",
                size=84,
                color="#FFFFFF",
                outline_color="#000000",
                outline_w=0,
                box_color="#34E36B",
                box_opacity=1.0,
            ),
            highlight=HighlightStyle(
                color="#000000", scale=1.0, box=False, animation="karaoke_fill"
            ),
        ),
        CaptionPreset(
            id="preset_t",
            name="Sticker Round",
            style=CaptionStyle(
                font="Luckiest Guy", size=108, color="#FFFFFF", outline_color="#000000", outline_w=9
            ),
            highlight=HighlightStyle(color="#FFD23D", scale=1.1, box=False, animation="spring"),
        ),
        CaptionPreset(
            id="preset_u",
            name="Gamer Tech",
            style=CaptionStyle(
                font="Russo One", size=92, color="#FFFFFF", outline_color="#00E5FF", outline_w=5
            ),
            highlight=HighlightStyle(color="#00E5FF", scale=1.0, box=False, animation="glow_pulse"),
        ),
    ]
