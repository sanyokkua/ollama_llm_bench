"""Unit tests for NotificationService — status bar routing and QMessageBox dialogs."""

import pytest
from PySide6.QtWidgets import QMessageBox, QStatusBar, QWidget
from pytest_mock import MockerFixture  # used via mocker fixture parameter type hint

from ollama_llm_bench.ui.qt_classes.notification_service import NotificationService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_status_bar(mocker: MockerFixture) -> QStatusBar:
    """Return a Mock spec'd to QStatusBar — no Qt event loop required."""
    return mocker.Mock(spec=QStatusBar)  # type: ignore[no-any-return]


@pytest.fixture
def service(mock_status_bar: QStatusBar) -> NotificationService:
    """Construct a NotificationService with a mocked status bar."""
    return NotificationService(status_bar=mock_status_bar)


@pytest.fixture
def mock_parent(mocker: MockerFixture) -> QWidget:
    """Return a Mock spec'd to QWidget for use as dialog parent."""
    return mocker.Mock(spec=QWidget)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# TestShowInfo
# ---------------------------------------------------------------------------


class TestShowInfo:
    """Tests for NotificationService.show_info()."""

    def test_show_info_calls_status_bar_show_message(
        self,
        service: NotificationService,
        mock_status_bar: QStatusBar,
    ) -> None:
        # Arrange
        text = "hello"

        # Act
        service.show_info(text)

        # Assert
        mock_status_bar.showMessage.assert_called_once_with("hello", 5000)  # type: ignore[attr-defined]

    def test_show_info_custom_msecs(
        self,
        service: NotificationService,
        mock_status_bar: QStatusBar,
    ) -> None:
        # Arrange
        text = "msg"

        # Act
        service.show_info(text, msecs=3000)

        # Assert
        mock_status_bar.showMessage.assert_called_once_with("msg", 3000)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# TestConfirm
# ---------------------------------------------------------------------------


class TestConfirm:
    """Tests for NotificationService.confirm()."""

    def test_confirm_returns_true_when_yes_clicked(
        self,
        service: NotificationService,
        mock_parent: QWidget,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mocker.patch(
            "ollama_llm_bench.ui.qt_classes.notification_service.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        )

        # Act
        result = service.confirm(mock_parent, "Confirm", "Are you sure?")

        # Assert
        assert result is True

    def test_confirm_returns_false_when_cancel_clicked(
        self,
        service: NotificationService,
        mock_parent: QWidget,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mocker.patch(
            "ollama_llm_bench.ui.qt_classes.notification_service.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Cancel,
        )

        # Act
        result = service.confirm(mock_parent, "Confirm", "Are you sure?")

        # Assert
        assert result is False

    def test_confirm_default_button_is_cancel(
        self,
        service: NotificationService,
        mock_parent: QWidget,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mock_question = mocker.patch(
            "ollama_llm_bench.ui.qt_classes.notification_service.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Cancel,
        )

        # Act
        service.confirm(mock_parent, "Confirm", "Are you sure?")

        # Assert — 5th positional arg (index 4) is the default_button
        call_args = mock_question.call_args
        assert call_args.args[4] == QMessageBox.StandardButton.Cancel


# ---------------------------------------------------------------------------
# TestShowWarningBlocking
# ---------------------------------------------------------------------------


class TestShowWarningBlocking:
    """Tests for NotificationService.show_warning_blocking()."""

    def test_show_warning_blocking_calls_qmessagebox_warning(
        self,
        service: NotificationService,
        mock_parent: QWidget,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mock_warning = mocker.patch(
            "ollama_llm_bench.ui.qt_classes.notification_service.QMessageBox.warning",
        )

        # Act
        service.show_warning_blocking(mock_parent, "Warning", "Something went wrong.")

        # Assert
        mock_warning.assert_called_once_with(mock_parent, "Warning", "Something went wrong.")


# ---------------------------------------------------------------------------
# TestShowErrorBlocking
# ---------------------------------------------------------------------------


class TestShowErrorBlocking:
    """Tests for NotificationService.show_error_blocking()."""

    def test_show_error_blocking_calls_qmessagebox_critical(
        self,
        service: NotificationService,
        mock_parent: QWidget,
        mocker: MockerFixture,
    ) -> None:
        # Arrange
        mock_critical = mocker.patch(
            "ollama_llm_bench.ui.qt_classes.notification_service.QMessageBox.critical",
        )

        # Act
        service.show_error_blocking(mock_parent, "Error", "Fatal failure.")

        # Assert
        mock_critical.assert_called_once_with(mock_parent, "Error", "Fatal failure.")
