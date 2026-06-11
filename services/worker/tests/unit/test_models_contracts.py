"""Контракты editor-v3: Chapter/ChaptersData, split center_b, animation."""

from app.models import Chapter, ChaptersData, CropOverride, HighlightStyle


def test_chapter_fields() -> None:
    ch = Chapter(start=0.0, end=12.5, title="Интро", summary="Знакомство с гостем")
    assert ch.end > ch.start


def test_chapters_data_default_pending() -> None:
    cd = ChaptersData(status="pending")
    assert cd.chapters == []
    assert cd.error is None


def test_crop_override_split_center_b() -> None:
    ov = CropOverride(source_start=0, source_end=5, mode="split", center=0.25, center_b=0.75)
    assert ov.center_b == 0.75


def test_crop_override_center_b_default_none() -> None:
    ov = CropOverride(source_start=0, source_end=5, mode="fill")
    assert ov.center_b is None


def test_highlight_animation_default() -> None:
    assert HighlightStyle().animation == "karaoke_fill"


def test_highlight_animation_values() -> None:
    for anim in ("none", "karaoke_fill", "pop", "bounce"):
        assert HighlightStyle(animation=anim).animation == anim


def test_contract_keeps_field_named_title() -> None:
    """_strip_titles чистит метаданные, но НЕ поле модели с именем "title" (Chapter.title)."""
    from app.export_schema import build_contract

    contract = build_contract()
    chapter_props = contract["$defs"]["Chapter"]["properties"]
    assert "title" in chapter_props
    assert chapter_props["title"]["type"] == "string"
