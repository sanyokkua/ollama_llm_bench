"""Resolves the ThemeTokens container matching a ThemeManager's current active theme (08-D
§13, §16) — the shared theme-follow helper for ui/shared's custom-painted primitives.
"""

from ollama_llm_bench.ui.theme import (
    ActiveThemeKind,
    PlatformKind,
    ThemeManager,
    ThemeTokens,
    make_dark_theme_tokens,
    make_light_theme_tokens,
)


def resolve_active_tokens(
    *, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> ThemeTokens:
    """Return the token container matching `theme_manager`'s currently active theme kind."""
    if theme_manager.active_theme_kind is ActiveThemeKind.DARK:
        return make_dark_theme_tokens(platform_kind=platform_kind)
    return make_light_theme_tokens(platform_kind=platform_kind)
