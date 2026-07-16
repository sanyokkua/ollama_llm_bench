"""Pure Dark/Light container selection from ui.theme + OS colour scheme (08-D §13 AC-1)."""

from ollama_llm_bench.ui.theme.models import ActiveThemeKind, OsColorScheme, ThemeSetting


def resolve_active_theme_kind(
    *, theme_setting: ThemeSetting, os_color_scheme: OsColorScheme
) -> ActiveThemeKind:
    """Select the container per the 08-D §13 table: explicit setting wins; system tracks OS."""
    if theme_setting is ThemeSetting.DARK:
        return ActiveThemeKind.DARK
    if theme_setting is ThemeSetting.LIGHT:
        return ActiveThemeKind.LIGHT
    return ActiveThemeKind.DARK if os_color_scheme is OsColorScheme.DARK else ActiveThemeKind.LIGHT
