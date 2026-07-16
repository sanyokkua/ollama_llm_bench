"""Proves STORY-050-AC-1 and STORY-050-AC-3 (08-D §13)."""

from collections.abc import Iterator

from PySide6.QtCore import Qt
from PySide6.QtGui import QStyleHints
from PySide6.QtWidgets import QApplication
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.theme import ActiveThemeKind, OsColorScheme, PlatformKind, ThemeSetting
from ollama_llm_bench.ui.theme.api import make_theme_manager, select_active_theme_kind


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


@pytest.fixture
def theme_manager_env(qapp: QApplication) -> Iterator[tuple[QApplication, QStyleHints]]:
    """Yield (qapp, style_hints); always restore auto-detected colour scheme on teardown."""
    style_hints = qapp.styleHints()
    yield qapp, style_hints
    style_hints.colorSchemeChanged.disconnect()
    style_hints.unsetColorScheme()


def test_explicit_override_ignores_live_os_change(
    theme_manager_env: tuple[QApplication, QStyleHints], mocker: MockerFixture
) -> None:
    """Proves: STORY-050-AC-3

    Given ui.theme is an explicit dark (or light), when the OS colour scheme changes at
    runtime, then the applied theme does not change and no theme_changed notification fires.
    """
    app, style_hints = theme_manager_env
    style_hints.setColorScheme(Qt.ColorScheme.Dark)
    manager = make_theme_manager(
        app=app, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    apply_spy = mocker.spy(app, "setStyleSheet")
    notified = []
    manager.theme_changed.connect(lambda: notified.append(True))

    style_hints.setColorScheme(Qt.ColorScheme.Light)

    assert manager.active_theme_kind == ActiveThemeKind.DARK
    assert apply_spy.call_count == 0
    assert notified == []
