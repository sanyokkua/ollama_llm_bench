"""Resolve theme tokens for ``ui/progress/``'s custom-painted stage badge and for
layout spacing/radius sizing (STORY-058).

``resolve_theme_tokens`` follows ``ui/resume_benchmark/_internal/theme_lookup.py``'s
established optional-``ThemeManager`` pattern verbatim. ``resolve_spacing_tokens``
exploits that spacing/radius/border tokens carry identical values in both the Dark
and Light containers (``ui/theme/_internal/factory.py``), so layout code can size
margins/gaps from real tokens with no live ``ThemeManager`` at all.
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


def resolve_theme_tokens(
    *, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> ThemeTokens:
    """Return the token container matching `theme_manager`'s active theme kind."""
    if theme_manager.active_theme_kind is ActiveThemeKind.DARK:
        return make_dark_theme_tokens(platform_kind=platform_kind)
    return make_light_theme_tokens(platform_kind=platform_kind)


def resolve_spacing_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Return the theme-invariant spacing/radius/border scale for layout construction.

    Spacing, radius, and border tokens are identical in both the Dark and Light
    containers, so this needs no live ``ThemeManager`` -- layout code can size
    margins/gaps from real tokens even before a theme is wired.
    """
    return make_dark_theme_tokens(platform_kind=platform_kind)
