"""Unit tests for ``_internal/geometry.py`` (STORY-053-AC-7, STORY-053-AC-8, EC-PLAT-3)."""

from unittest.mock import MagicMock

from PySide6.QtCore import QRect
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QMainWindow
import pytest

from ollama_llm_bench.ui.main_window._internal.geometry import (
    DebouncedGeometryWriter,
    restore_geometry,
)
from ollama_llm_bench.ui.main_window._internal.tests.conftest import FakeMainWindowGateway


def _make_screen(available: QRect) -> QScreen:
    screen = MagicMock(spec=QScreen)
    screen.availableGeometry.return_value = available
    return screen


def _persist_offscreen_value(gateway: FakeMainWindowGateway) -> None:
    gateway.set_window_geometry("9000,9000,400,300")
    gateway.set_window_geometry_calls.clear()


def _leave_unset(_gateway: FakeMainWindowGateway) -> None:
    return None


def test_resize_burst_coalesces_into_one_write(
    qtbot: object, gateway: FakeMainWindowGateway
) -> None:
    """Proves: STORY-053-AC-7

    Given a burst of window resize events,
    when the geometry writer runs,
    then it coalesces the burst into a single ``MainWindowGateway.set_window_geometry`` write
    after the debounce interval, carrying the last value observed.
    """
    # Arrange
    writer = DebouncedGeometryWriter(gateway=gateway, debounce_ms=200)

    # Act
    writer.on_window_geometry_changed("0,0,1440,900")
    writer.on_window_geometry_changed("1,0,1440,900")
    writer.on_window_geometry_changed("2,0,1440,900")
    writer.on_window_geometry_changed("3,0,1440,900")
    writer.on_window_geometry_changed("4,0,1440,900")
    qtbot.wait(250)  # type: ignore[attr-defined]  # qtbot fixture is untyped upstream

    # Assert
    assert gateway.set_window_geometry_calls == ["4,0,1440,900"]


@pytest.mark.parametrize(
    ("setup_gateway", "screens", "expected_rect"),
    [
        (
            _persist_offscreen_value,
            [_make_screen(QRect(0, 0, 1920, 1080))],
            QRect(240, 90, 1440, 900),
        ),
        (_leave_unset, [_make_screen(QRect(0, 0, 1920, 1080))], QRect(240, 90, 1440, 900)),
        (_persist_offscreen_value, [], QRect(0, 0, 1440, 900)),
    ],
    ids=["off_screen_clamped_to_centred_default", "no_persisted_value", "no_screens_at_all"],
)
def test_offscreen_geometry_is_clamped(
    setup_gateway: object,
    screens: list[QScreen],
    expected_rect: QRect,
    gateway: FakeMainWindowGateway,
    qtbot: object,
) -> None:
    """Proves: STORY-053-AC-8

    Given a persisted window geometry that lies fully off-screen (or is absent, or no screen
    exists at all),
    when the shell restores geometry on launch,
    then it clamps to the available screen area, falling back to the centred ``1440x900``
    default when no valid placement exists (EC-PLAT-3).
    """
    # Arrange
    setup_gateway(gateway)  # type: ignore[operator]  # a parametrized setup callable
    window = QMainWindow()
    qtbot.addWidget(window)  # type: ignore[attr-defined]  # qtbot fixture is untyped upstream

    # Act
    restore_geometry(window, gateway, screens=screens)

    # Assert
    assert window.geometry() == expected_rect
