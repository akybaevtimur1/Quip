"""Сид-пресеты стилей субтитров (галерея, дефолт A). PURE-данные.

Один источник правды значений для бэка (экспорт ASS) и фронта (CSS-превью): фронт зеркалит
эти же значения в apps/web/lib/presets.ts. Главный путь — отдавать их через GET /presets.

Дефолт = A (караоке-бокс). См. docs/superpowers/specs/2026-06-11-editor-v2-design.md §A2.
"""

from __future__ import annotations

from app.models import CaptionPreset, CaptionStyle, HighlightStyle

DEFAULT_PRESET_ID = "preset_a"


def seed_presets() -> list[CaptionPreset]:
    """4 встроенных пресета. id стабильны (preset_a..preset_d), A — дефолт."""
    return [
        CaptionPreset(
            id="preset_a",
            name="Караоке-бокс",
            style=CaptionStyle(size=84, color="#FFFFFF", outline_color="#000000", outline_w=7),
            highlight=HighlightStyle(color="#FF5A3D", scale=1.0, box=True),
        ),
        CaptionPreset(
            id="preset_b",
            name="Цветное слово",
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
            name="Чистая строка",
            style=CaptionStyle(
                size=76, color="#FFFFFF", outline_color="#000000", outline_w=4, shadow=4
            ),
            highlight=None,
        ),
    ]
