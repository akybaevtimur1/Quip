"""Cost guard: the LLM model id must never run a Gemini-3 / moving -latest alias.
`gemini-flash-latest` now resolves to gemini-3.5-flash (~×10 the cost of 2.5-flash) —
`pin_llm_model` coerces it down."""

import pytest

from app.config import pin_llm_model


@pytest.mark.parametrize(
    "given,expected",
    [
        ("gemini-flash-latest", "gemini-2.5-flash"),  # the prod secret value (→ gemini-3.5-flash)
        ("gemini-pro-latest", "gemini-2.5-flash"),
        ("gemini-3.5-flash", "gemini-2.5-flash"),
        ("gemini-3-pro", "gemini-2.5-flash"),
        ("models/gemini-3.5-flash", "gemini-2.5-flash"),
        ("GEMINI-FLASH-LATEST", "gemini-2.5-flash"),  # case-insensitive
        # pinned, allowed models pass through untouched
        ("gemini-2.5-flash", "gemini-2.5-flash"),
        ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
        ("gemini-2.5-pro", "gemini-2.5-pro"),
    ],
)
def test_pin_llm_model(given: str, expected: str) -> None:
    assert pin_llm_model(given) == expected
