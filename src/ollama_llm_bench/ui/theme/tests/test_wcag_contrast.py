"""Proves STORY-050-AC-4 (08-D §14)."""

from collections.abc import Callable

import pytest

from ollama_llm_bench.ui.theme import (
    PlatformKind,
    ThemeTokens,
    make_dark_theme_tokens,
    make_light_theme_tokens,
)
from ollama_llm_bench.ui.theme._internal.contrast import contrast_ratio
from ollama_llm_bench.ui.theme.api import resolve_color

_CONTRAST_PAIRS = [
    ("text.primary", "bg.window", 4.5),
    ("text.primary", "bg.surface", 4.5),
    ("text.primary", "bg.raised", 4.5),
    ("text.secondary", "bg.surface", 4.5),
    ("text.secondary", "bg.raised", 4.5),
    ("text.on-primary", "primary.base", 4.5),
    ("text.on-error", "error.base", 4.5),
    ("success.base", "bg.surface", 3.0),
    ("warning.base", "bg.surface", 3.0),
    ("error.base", "bg.surface", 3.0),
    ("info.base", "bg.surface", 3.0),
    ("muted.base", "bg.surface", 3.0),
    ("border.focus", "bg.window", 3.0),
    ("border.default", "bg.surface", 3.0),
]


@pytest.mark.parametrize("theme_maker", [make_dark_theme_tokens, make_light_theme_tokens])
@pytest.mark.parametrize(("foreground_role", "background_role", "minimum_ratio"), _CONTRAST_PAIRS)
def test_contrast_pair_meets_minimum_in_both_themes(
    theme_maker: Callable[[PlatformKind], "ThemeTokens"],
    foreground_role: str,
    background_role: str,
    minimum_ratio: float,
) -> None:
    """Proves: STORY-050-AC-4

    For each of the 14 foreground/background pairs in 08-D §14, in both the Dark and Light
    theme, the contrast ratio computed from the resolved token values meets or exceeds that
    pair's minimum required ratio.
    """
    tokens = theme_maker(
        platform_kind=PlatformKind.LINUX  # type: ignore[call-arg]  # Callable erases kw-only param name
    )
    foreground_hex = resolve_color(tokens, foreground_role)
    background_hex = resolve_color(tokens, background_role)

    ratio = contrast_ratio(foreground_hex, background_hex)

    assert ratio >= minimum_ratio
