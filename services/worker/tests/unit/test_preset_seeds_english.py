from app.editor.preset_seeds import seed_presets


def test_preset_names_are_ascii_english():
    for p in seed_presets():
        assert p.name.isascii(), f"non-English preset name: {p.id}={p.name!r}"
