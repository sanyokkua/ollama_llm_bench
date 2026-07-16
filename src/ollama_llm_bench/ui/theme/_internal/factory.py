"""Assembles the Dark and Light ThemeTokens containers (08-D §3-§12, §16)."""

from ollama_llm_bench.ui.theme._internal.colors import DARK_COLORS, LIGHT_COLORS
from ollama_llm_bench.ui.theme._internal.fonts import select_font_chain
from ollama_llm_bench.ui.theme._internal.scalars import (
    BORDER_TOKENS,
    FOCUS_RING_TOKENS,
    FONT_SIZE_TOKENS,
    FONT_WEIGHT_TOKENS,
    MOTION_TOKENS,
    RADIUS_TOKENS,
    SHADOW_TOKENS,
    SPACING_TOKENS,
)
from ollama_llm_bench.ui.theme.models import PlatformKind, ThemeTokens


def assemble_dark_theme_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Build the Dark ThemeTokens container for the given platform."""
    return ThemeTokens(
        colors=DARK_COLORS,
        fonts=select_font_chain(platform_kind),
        font_size=FONT_SIZE_TOKENS,
        font_weight=FONT_WEIGHT_TOKENS,
        spacing=SPACING_TOKENS,
        radius=RADIUS_TOKENS,
        border=BORDER_TOKENS,
        focus_ring=FOCUS_RING_TOKENS,
        shadow=SHADOW_TOKENS,
        motion=MOTION_TOKENS,
    )


def assemble_light_theme_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Build the Light ThemeTokens container for the given platform."""
    return ThemeTokens(
        colors=LIGHT_COLORS,
        fonts=select_font_chain(platform_kind),
        font_size=FONT_SIZE_TOKENS,
        font_weight=FONT_WEIGHT_TOKENS,
        spacing=SPACING_TOKENS,
        radius=RADIUS_TOKENS,
        border=BORDER_TOKENS,
        focus_ring=FOCUS_RING_TOKENS,
        shadow=SHADOW_TOKENS,
        motion=MOTION_TOKENS,
    )
