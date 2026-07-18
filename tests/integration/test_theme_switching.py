"""Integration test for live OS colour-scheme switching under ``ThemeSetting.SYSTEM``
(STORY-050 AC-2).

Wires the real ``ThemeManager`` to the real ``QApplication``/``QStyleHints`` pair with no
fakes — the theme module is the single styling authority and `styleSheet()`/`palette()` are
observed straight off the real ``QApplication`` singleton. This crosses the real
manager/QApplication boundary rather than testing one function in isolation, so it lives in
``tests/integration/`` rather than the module's colocated ``tests/`` (which cover the pure
AC-1 selection table and the AC-3 explicit-override case with no live re-application to
assert).
"""

from collections.abc import Iterator

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QStyleHints
from PySide6.QtWidgets import QApplication
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.theme import (
    ActiveThemeKind,
    PlatformKind,
    ThemeSetting,
    make_dark_theme_tokens,
)
from ollama_llm_bench.ui.theme.api import make_theme_manager


@pytest.fixture
def _style_hints(qapp: QApplication) -> Iterator[QStyleHints]:
    """Yield the app's QStyleHints; always restore auto-detected colour scheme on teardown."""
    style_hints = qapp.styleHints()
    yield style_hints
    style_hints.colorSchemeChanged.disconnect()
    style_hints.unsetColorScheme()


def test_system_theme_reapplies_and_notifies_on_os_change(
    qapp: QApplication, _style_hints: QStyleHints, qtbot: QtBot
) -> None:
    """Proves: STORY-050-AC-2

    Given ui.theme is system, when the OS colour scheme changes at runtime, then the theme
    module rebuilds and re-applies the stylesheet and QPalette to the QApplication for the
    newly matching container and emits the theme-changed notification, without an
    application restart.
    """
    # Arrange
    _style_hints.setColorScheme(Qt.ColorScheme.Light)
    manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.SYSTEM, platform_kind=PlatformKind.LINUX
    )
    active_kind_before: ActiveThemeKind = manager.active_theme_kind
    assert active_kind_before == ActiveThemeKind.LIGHT
    stylesheet_before = qapp.styleSheet()
    assert stylesheet_before != ""

    # Act — flip the live OS colour scheme; no restart, same QApplication instance throughout
    with qtbot.waitSignal(manager.theme_changed, timeout=2000):
        _style_hints.setColorScheme(Qt.ColorScheme.Dark)

    # Assert — the container flips, the stylesheet was rebuilt and re-applied, and the
    # QPalette carries the newly matching (Dark) container's resolved token value
    active_kind_after: ActiveThemeKind = manager.active_theme_kind
    assert active_kind_after == ActiveThemeKind.DARK
    stylesheet_after = qapp.styleSheet()
    assert stylesheet_after != ""
    assert stylesheet_after != stylesheet_before
    expected_dark_window_color = make_dark_theme_tokens(
        platform_kind=PlatformKind.LINUX
    ).colors.bg_window
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == expected_dark_window_color
