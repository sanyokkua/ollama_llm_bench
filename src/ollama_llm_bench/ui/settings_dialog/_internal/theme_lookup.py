"""Resolve theme tokens for this module's custom-painted table decorations (the
Health Dot / Auth badge delegate, the row-action icons) -- STORY-066.

Optional collaborator, following ``ui/new_benchmark/_internal/task_files.py``'s and
``ui/resume_benchmark/_internal/theme_lookup.py``'s established optional-
``ThemeManager`` pattern: every caller accepts ``theme_manager: ThemeManager | None``
and falls back to an untinted/plain rendering when no live ``ThemeManager`` is
wired (unit tests with no ``QApplication``-bound theme collaborator).
"""

from ollama_llm_bench.ui.theme import (
    ActiveThemeKind,
    PlatformKind,
    ThemeManager,
    ThemeTokens,
    make_dark_theme_tokens,
    make_light_theme_tokens,
)

__all__: list[str] = ["resolve_theme_tokens"]


def resolve_theme_tokens(
    *, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> ThemeTokens:
    """Return the token container matching `theme_manager`'s active theme kind."""
    if theme_manager.active_theme_kind is ActiveThemeKind.DARK:
        return make_dark_theme_tokens(platform_kind=platform_kind)
    return make_light_theme_tokens(platform_kind=platform_kind)
