"""WCAG AA contrast ratio tests for DARK and LIGHT design token pairs."""

import pytest

from ollama_llm_bench.ui.style.tokens import DARK_TOKENS, LIGHT_TOKENS

type TokenDict = dict[str, str]

_WCAG_AA_NORMAL_TEXT = 4.5


def _relative_luminance(hex_color: str) -> float:
    """Return the relative luminance of a hex color per WCAG 2.1.

    Args:
        hex_color: CSS hex color string, with or without leading ``#``.

    Returns:
        Relative luminance in the range [0.0, 1.0].
    """
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _linearise(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _linearise(r) + 0.7152 * _linearise(g) + 0.0722 * _linearise(b)


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    """Return the WCAG contrast ratio between two hex colors.

    Args:
        hex_a: First hex color string.
        hex_b: Second hex color string.

    Returns:
        Contrast ratio in the range [1.0, 21.0].
    """
    la = _relative_luminance(hex_a)
    lb = _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize(
    "tokens,theme",
    [(DARK_TOKENS, "dark"), (LIGHT_TOKENS, "light")],
    ids=["dark", "light"],
)
@pytest.mark.parametrize(
    "fg_key,bg_key,min_ratio",
    [
        ("text_primary", "bg_primary", _WCAG_AA_NORMAL_TEXT),
        ("text_secondary", "bg_secondary", _WCAG_AA_NORMAL_TEXT),
        ("failure", "failure_bg", _WCAG_AA_NORMAL_TEXT),
        ("success", "success_bg", _WCAG_AA_NORMAL_TEXT),
        ("warning", "warning_bg", _WCAG_AA_NORMAL_TEXT),
        ("text_on_primary", "primary", _WCAG_AA_NORMAL_TEXT),
    ],
    ids=[
        "text_primary-bg_primary",
        "text_secondary-bg_secondary",
        "failure-failure_bg",
        "success-success_bg",
        "warning-warning_bg",
        "text_on_primary-primary",
    ],
)
def test_wcag_aa_contrast(
    tokens: TokenDict,
    theme: str,
    fg_key: str,
    bg_key: str,
    min_ratio: float,
) -> None:
    """Assert that each foreground/background token pair meets WCAG AA contrast.

    Args:
        tokens: Token dict for the theme under test.
        theme: Human-readable theme name used in the failure message.
        fg_key: Token key for the foreground color.
        bg_key: Token key for the background color.
        min_ratio: Minimum acceptable contrast ratio (4.5 for WCAG AA normal text).
    """
    fg = tokens[fg_key]
    bg = tokens[bg_key]
    ratio = _contrast_ratio(fg, bg)
    assert ratio >= min_ratio, f"[{theme}] {fg_key} ({fg}) on {bg_key} ({bg}): ratio {ratio:.2f} < required {min_ratio}"
