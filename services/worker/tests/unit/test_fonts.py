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

FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"

# Mirror StyleTab.CAPTION_FONTS → the TTF filename under services/worker/fonts.
EXPECTED_FAMILY_TO_FILE = {
    "Montserrat": "Montserrat.ttf",
    "Unbounded": "Unbounded.ttf",
    "Rubik": "Rubik.ttf",
    "Anton": "Anton.ttf",
    "Poppins": "PoppinsBlack.ttf",
    "Bebas Neue": "BebasNeue.ttf",
    "Archivo Black": "ArchivoBlack.ttf",
    "Russo One": "RussoOne.ttf",
    "Luckiest Guy": "LuckiestGuy.ttf",
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
