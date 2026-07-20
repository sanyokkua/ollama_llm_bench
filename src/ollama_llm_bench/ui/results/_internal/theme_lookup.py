"""Resolve theme-invariant spacing tokens for ``ui/results/``'s layout construction
(STORY-061).

Follows ``ui/progress/_internal/theme_lookup.py``'s established pattern verbatim:
spacing/radius/border tokens carry identical values in both the Dark and Light
containers (``ui/theme/_internal/factory.py``), so layout code can size margins/gaps
from real tokens with no live ``ThemeManager`` at all.
"""

from ollama_llm_bench.ui.theme import PlatformKind, ThemeTokens, make_dark_theme_tokens

__all__: list[str] = ["resolve_spacing_tokens"]


def resolve_spacing_tokens(*, platform_kind: PlatformKind) -> ThemeTokens:
    """Return the theme-invariant spacing/radius/border scale for layout construction."""
    return make_dark_theme_tokens(platform_kind=platform_kind)
