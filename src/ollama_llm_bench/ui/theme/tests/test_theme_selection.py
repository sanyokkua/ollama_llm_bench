"""Proves STORY-050-AC-1 and STORY-050-AC-3 (08-D §13)."""

import pytest

from ollama_llm_bench.ui.theme import ActiveThemeKind, OsColorScheme, ThemeSetting
from ollama_llm_bench.ui.theme.api import select_active_theme_kind


@pytest.mark.parametrize(
    ("theme_setting", "os_color_scheme", "expected"),
    [
        (ThemeSetting.SYSTEM, OsColorScheme.DARK, ActiveThemeKind.DARK),
        (ThemeSetting.SYSTEM, OsColorScheme.LIGHT, ActiveThemeKind.LIGHT),
        (ThemeSetting.DARK, OsColorScheme.DARK, ActiveThemeKind.DARK),
        (ThemeSetting.DARK, OsColorScheme.LIGHT, ActiveThemeKind.DARK),
        (ThemeSetting.LIGHT, OsColorScheme.DARK, ActiveThemeKind.LIGHT),
        (ThemeSetting.LIGHT, OsColorScheme.LIGHT, ActiveThemeKind.LIGHT),
    ],
)
def test_active_container_matches_setting_and_os_scheme(
    theme_setting: ThemeSetting, os_color_scheme: OsColorScheme, expected: ActiveThemeKind
) -> None:
    """Proves: STORY-050-AC-1

    For each combination of ui.theme setting and reported OS colour scheme, the correct
    container (Dark/Light) is selected per the 08-D §13 table.
    """
    result = select_active_theme_kind(theme_setting=theme_setting, os_color_scheme=os_color_scheme)

    assert result == expected
