"""Guard: every caption/hook font's TTF primary family name (name ID 1) MUST equal the family
the ASS Style line asks for (the UI value). If they diverge, libass/ffmpeg can't match the font
on EXPORT and silently falls back — the 'I picked Poppins but the render used another font' bug
(PoppinsBlack.ttf shipped as family 'Poppins Black', not 'Poppins'). Preview (libass-wasm) matches
the typographic name and hides it, so only the render breaks → caught here."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fontTools")
from fontTools.ttLib import TTFont  # noqa: E402

from app.editor.captions_v2 import (  # noqa: E402
    KAZAKH_CODEPOINTS,
    KAZAKH_INCOMPLETE_FONTS,
    LATIN_ONLY_FONTS,
)

FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"

# Family (the name the ASS Style line asks for) → the TTF filename under services/worker/fonts.
# Two groups: (1) UI fonts users can pick (StyleControls.CAPTION_FONTS); (2) Cyrillic look-match
# fonts (LOOK_MATCH_FOR_CYRILLIC) emitted at render-time to keep the bold display look on
# Cyrillic/Kazakh. Both must have name ID 1 == the family the ASS asks for, or export font
# matching silently falls back.
EXPECTED_FAMILY_TO_FILE = {
    # (1) UI-pickable fonts
    "Montserrat": "Montserrat.ttf",
    "Unbounded": "Unbounded.ttf",
    "Rubik": "Rubik.ttf",
    "Anton": "Anton.ttf",
    "Poppins": "PoppinsBlack.ttf",
    "Bebas Neue": "BebasNeue.ttf",
    "Archivo Black": "ArchivoBlack.ttf",
    "Russo One": "RussoOne.ttf",
    "Luckiest Guy": "LuckiestGuy.ttf",
    # (2) Cyrillic look-match fonts (single static heavy instances, OFL, google/fonts)
    "Rubik Black": "RubikBlack.ttf",  # Unbounded look-match (hook default)
    "Play": "Play.ttf",  # Russo One look-match
    "Oswald Heavy": "OswaldHeavy.ttf",  # Anton look-match
    "Oswald": "Oswald.ttf",  # Bebas Neue look-match
    "Golos Text Black": "GolosTextBlack.ttf",  # Archivo Black look-match (heavy Cyrillic grotesque)
    "Nunito Black": "NunitoBlack.ttf",  # Luckiest Guy look-match
}


@pytest.mark.parametrize("family,filename", sorted(EXPECTED_FAMILY_TO_FILE.items()))
def test_ttf_family_matches_ass_family(family: str, filename: str) -> None:
    path = FONTS_DIR / filename
    assert path.exists(), f"missing render font {path}"
    family_id1 = TTFont(path)["name"].getDebugName(1)
    assert family_id1 == family, (
        f"{filename}: TTF family (name ID 1) is {family_id1!r} but the ASS asks for {family!r} — "
        f"export font matching will fall back. Normalise the TTF name table."
    )


# Шрифты-ФОЛБЭКИ казахского: всё, что НЕ Latin-only (нет кириллицы вовсе) и НЕ Kazakh-incomplete
# (Unbounded/Russo One — нет казахских глифов). resolve_font_for_text переключает текст с
# казахскими буквами ИМЕННО на них, поэтому tofu в их cmap недопустим — иначе будущая правка
# свапа тихо вернёт квадратики на казахском (founder closing Almaty B2B deal).
KAZAKH_FALLBACK_FAMILIES = sorted(
    fam
    for fam in EXPECTED_FAMILY_TO_FILE
    if fam not in LATIN_ONLY_FONTS and fam not in KAZAKH_INCOMPLETE_FONTS
)


@pytest.mark.parametrize("family", KAZAKH_FALLBACK_FAMILIES)
def test_kazakh_glyph_coverage(family: str) -> None:
    """Каждый шрифт-фолбэк ОБЯЗАН содержать все 18 казахо-уникальных глифов (anti-tofu гард)."""
    path = FONTS_DIR / EXPECTED_FAMILY_TO_FILE[family]
    assert path.exists(), f"missing render font {path}"
    cmap: set[int] = set()
    for table in TTFont(path)["cmap"].tables:
        cmap |= set(table.cmap.keys())
    missing = sorted(cp for cp in KAZAKH_CODEPOINTS if cp not in cmap)
    assert not missing, (
        f"{family} ({path.name}) is a Kazakh fallback target but its cmap is missing "
        f"{len(missing)} Kazakh codepoint(s): {[f'U+{cp:04X}' for cp in missing]} — "
        f"Kazakh text routed here would render as tofu."
    )
