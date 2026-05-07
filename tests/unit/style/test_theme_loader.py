"""Unit tests for ui/style/theme_loader.py — _SafeTokenMap, apply_theme, get_color."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.style.theme_loader import _SafeTokenMap, apply_theme, get_color

# ---------------------------------------------------------------------------
# Group A — _SafeTokenMap
# ---------------------------------------------------------------------------


def test_safe_token_map_returns_value_for_known_key() -> None:
    # Arrange
    m = _SafeTokenMap({"primary": "#FF0000"})

    # Act
    result = m["primary"]

    # Assert
    assert result == "#FF0000"


def test_safe_token_map_returns_placeholder_for_unknown_key() -> None:
    # Arrange
    m = _SafeTokenMap({"primary": "#FF0000"})

    # Act
    result = m["unknown_key"]

    # Assert — preserves the original {key} pattern instead of raising KeyError
    assert result == "{unknown_key}"


# ---------------------------------------------------------------------------
# Group B — apply_theme
# ---------------------------------------------------------------------------


def test_apply_theme_dark_calls_set_stylesheet_with_resolved_tokens(
    mocker: MockerFixture,
) -> None:
    # Arrange — stub out the file read so the test never hits the real QSS file
    mocker.patch.object(Path, "read_text", return_value="bg: {bg_primary};")
    mock_app = mocker.Mock(spec=QApplication)

    # Act
    apply_theme(mock_app, "dark")

    # Assert — dark bg_primary token is #111827; it must appear in the resolved QSS
    mock_app.setStyleSheet.assert_called_once()
    stylesheet_arg: str = mock_app.setStyleSheet.call_args[0][0]
    assert "#111827" in stylesheet_arg


def test_apply_theme_dark_stylesheet_contains_no_unresolved_token_placeholders(
    mocker: MockerFixture,
) -> None:
    # Arrange — template with a known token; after resolution no {…} should remain
    mocker.patch.object(Path, "read_text", return_value="color: {text_primary};")
    mock_app = mocker.Mock(spec=QApplication)

    # Act
    apply_theme(mock_app, "dark")

    # Assert — resolved value must not still be a raw placeholder
    stylesheet_arg: str = mock_app.setStyleSheet.call_args[0][0]
    assert "{text_primary}" not in stylesheet_arg


def test_apply_theme_unknown_qss_file_does_not_call_set_stylesheet(
    mocker: MockerFixture,
) -> None:
    # Arrange — simulate missing QSS file for an unknown theme name
    mocker.patch.object(Path, "read_text", side_effect=FileNotFoundError("no file"))
    mock_app = mocker.Mock(spec=QApplication)

    # Act
    apply_theme(mock_app, "nonexistent_theme")

    # Assert — early return on FileNotFoundError; setStyleSheet must not be called
    mock_app.setStyleSheet.assert_not_called()


# ---------------------------------------------------------------------------
# Group C — get_color
# ---------------------------------------------------------------------------


def test_get_color_returns_hex_for_known_dark_token() -> None:
    # Act
    result = get_color("dark", "primary")

    # Assert — dark primary token value from DARK_TOKENS
    assert result == "#14B8A6"


def test_get_color_raises_key_error_for_unknown_token() -> None:
    # Act / Assert — KeyError is the documented contract for missing tokens
    with pytest.raises(KeyError):
        get_color("dark", "token_that_does_not_exist")
