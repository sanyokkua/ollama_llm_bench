"""Tests for ui/style/style_utils.py — repolish helper."""

from unittest.mock import call

from PySide6.QtWidgets import QWidget
from pytest_mock import MockerFixture

from ollama_llm_bench.ui.style.style_utils import repolish


def test_repolish_calls_unpolish_on_widget_style(mocker: MockerFixture) -> None:
    # Arrange
    mock_style = mocker.Mock()
    mock_widget = mocker.Mock(spec=QWidget)
    mock_widget.style.return_value = mock_style

    # Act
    repolish(mock_widget)

    # Assert
    mock_style.unpolish.assert_called_once_with(mock_widget)


def test_repolish_calls_polish_on_widget_style(mocker: MockerFixture) -> None:
    # Arrange
    mock_style = mocker.Mock()
    mock_widget = mocker.Mock(spec=QWidget)
    mock_widget.style.return_value = mock_style

    # Act
    repolish(mock_widget)

    # Assert
    mock_style.polish.assert_called_once_with(mock_widget)


def test_repolish_calls_update_on_widget(mocker: MockerFixture) -> None:
    # Arrange
    mock_style = mocker.Mock()
    mock_widget = mocker.Mock(spec=QWidget)
    mock_widget.style.return_value = mock_style

    # Act
    repolish(mock_widget)

    # Assert
    mock_widget.update.assert_called_once()


def test_repolish_calls_in_correct_order(mocker: MockerFixture) -> None:
    # Arrange
    manager = mocker.Mock()
    mock_style = mocker.Mock()
    mock_widget = mocker.Mock(spec=QWidget)
    mock_widget.style.return_value = mock_style
    # Attach style methods to manager so call order is recorded on one object
    manager.attach_mock(mock_style.unpolish, "unpolish")
    manager.attach_mock(mock_style.polish, "polish")
    manager.attach_mock(mock_widget.update, "update")

    # Act
    repolish(mock_widget)

    # Assert — unpolish must precede polish, polish must precede update
    assert manager.mock_calls == [
        call.unpolish(mock_widget),
        call.polish(mock_widget),
        call.update(),
    ]
