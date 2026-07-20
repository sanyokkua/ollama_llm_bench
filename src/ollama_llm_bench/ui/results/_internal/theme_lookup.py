"""Resolve theme tokens for ``ui/results/``'s layout construction and custom-painted
surfaces (STORY-061, STORY-063 task 9).

``resolve_spacing_tokens`` follows ``ui/progress/_internal/theme_lookup.py``'s
established pattern verbatim: spacing/radius/border tokens carry identical values in
both the Dark and Light containers (``ui/theme/_internal/factory.py``), so layout code
can size margins/gaps from real tokens with no live ``ThemeManager`` at all.
``resolve_theme_tokens`` follows the same module's optional-``ThemeManager``-caller
pattern for a custom-painted surface (the Details tab's badge delegate) that needs the
*active* Dark/Light container, not just the theme-invariant scale.
"""

from ollama_llm_bench.ui.theme import (
    ActiveThemeKind,
    PlatformKind,
    ThemeManager,
    ThemeTokens,
    make_dark_theme_tokens,
    make_light_theme_tokens,
)

__all__: list[str] = ["resolve_spacing_tokens", "resolve_theme_tokens"]


def resolve_spacing_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Return the theme-invariant spacing/radius/border scale for layout construction."""
    return make_dark_theme_tokens(platform_kind=platform_kind)


def resolve_theme_tokens(
    *, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> ThemeTokens:
    """Return the token container matching `theme_manager`'s active theme kind."""
    if theme_manager.active_theme_kind is ActiveThemeKind.DARK:
        return make_dark_theme_tokens(platform_kind=platform_kind)
    return make_light_theme_tokens(platform_kind=platform_kind)
