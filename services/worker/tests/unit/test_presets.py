from app.editor.defaults import default_clip_edit
from app.editor.preset_seeds import seed_presets
from app.editor.presets import apply_preset
from app.models import CaptionPreset, CaptionStyle, HighlightStyle, Segment, Word


def test_seed_presets_twelve_unique():
    seeds = seed_presets()
    assert len(seeds) >= 12
    assert len({p.id for p in seeds}) == len(seeds)
    assert all(p.style.size > 0 for p in seeds)
    assert all(p.name for p in seeds)


def test_seed_presets_cover_animations():
    # Галерея демонстрирует РАЗНЫЕ анимации: pop, bounce и статичный (без караоке)
    seeds = seed_presets()
    anims = {p.highlight.animation for p in seeds if p.highlight is not None}
    assert "pop" in anims and "bounce" in anims
    assert any(p.highlight is None for p in seeds)


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


def test_apply_preset_preserves_caption_position():
    # B-#2: пресет НЕ должен сбрасывать ручную позицию субтитра (margin_v/alignment).
    # Юзер выставил margin_v=400 + alignment=8; пресет "Подкаст" несёт margin_v=1100/alignment=2.
    words = [Word(text="a", start=0.0, end=0.4)]
    edit = default_clip_edit(
        "clip_01",
        Segment(start=0.0, end=1.0, reason="r", score=0.5, type="hook"),
        words,
    )
    moved = edit.captions.style.model_copy(update={"margin_v": 400, "alignment": 8})
    edit = edit.model_copy(update={"captions": edit.captions.model_copy(update={"style": moved})})

    podcast = next(p for p in seed_presets() if p.id == "preset_h")
    assert podcast.style.margin_v == 1100  # sanity: пресет реально двигал бы позицию

    out = apply_preset(edit, podcast)
    # позиция СОХРАНЕНА (не из пресета)
    assert out.captions.style.margin_v == 400
    assert out.captions.style.alignment == 8
    # остальной стиль — из пресета
    assert out.captions.style.size == podcast.style.size
    assert out.captions.style.color == podcast.style.color
    assert out.captions.style.box_color == podcast.style.box_color
    assert out.captions.highlight is not None and podcast.highlight is not None
    assert out.captions.highlight.color == podcast.highlight.color
