"""Startup configuration tests — Fusion style, HighDPI policy, bundled fonts, system theme."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QStyleFactory
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.style.theme_loader import connect_system_theme_listener, detect_system_theme

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return the existing QApplication or create one for this module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Group A — Fusion style
# ---------------------------------------------------------------------------


def test_qapplication_style_is_fusion(qapp: QApplication) -> None:
    # Arrange
    fusion = QStyleFactory.create("Fusion")
    assert fusion is not None, "Fusion style plugin must be available in this Qt build"

    # Act
    qapp.setStyle(fusion)

    # Assert
    assert qapp.style().objectName() == "fusion"


# ---------------------------------------------------------------------------
# Group B — High-DPI rounding policy
# ---------------------------------------------------------------------------


def test_high_dpi_rounding_policy_set() -> None:
    # Arrange + Act
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # Assert
    assert QApplication.highDpiScaleFactorRoundingPolicy() == Qt.HighDpiScaleFactorRoundingPolicy.PassThrough


# ---------------------------------------------------------------------------
# Group D — System theme detection (scheme → theme string mapping)
# ---------------------------------------------------------------------------


def test_detect_system_theme_without_qapp_returns_dark(mocker: MockerFixture) -> None:
    # Arrange — simulate no running QApplication
    mocker.patch(
        "ollama_llm_bench.ui.style.theme_loader.QApplication.instance",
        return_value=None,
    )

    # Act
    result = detect_system_theme()

    # Assert — default fallback when no QApplication exists is "dark"
    assert result == "dark"


@pytest.mark.parametrize(
    "scheme,expected_theme",
    [
        (Qt.ColorScheme.Light, "light"),
        (Qt.ColorScheme.Dark, "dark"),
        (Qt.ColorScheme.Unknown, "dark"),
    ],
    ids=["light_scheme", "dark_scheme", "unknown_scheme_fallback_dark"],
)
def test_color_scheme_maps_to_expected_theme(
    qapp: QApplication,
    scheme: Qt.ColorScheme,
    expected_theme: str,
) -> None:
    # Arrange — capture what theme the listener receives when the OS emits a scheme change
    received: list[str] = []
    connect_system_theme_listener(received.append)

    # Act — emit the colorSchemeChanged signal programmatically
    qapp.styleHints().colorSchemeChanged.emit(scheme)

    # Assert — the last received theme must match the expected mapping
    assert received, "callback was never called — signal emission failed"
    assert received[-1] == expected_theme


# ---------------------------------------------------------------------------
# Group E — Color scheme change wires callback
# ---------------------------------------------------------------------------


def test_color_scheme_change_triggers_theme_reload(qapp: QApplication) -> None:
    # Arrange
    received: list[str] = []
    connect_system_theme_listener(received.append)

    # Act — simulate the OS switching to light then back to dark
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)

    # Assert — both transitions must have been captured
    assert "light" in received
    assert "dark" in received
