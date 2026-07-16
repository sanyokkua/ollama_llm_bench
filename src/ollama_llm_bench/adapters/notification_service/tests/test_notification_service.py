"""Tests for adapters/notification_service (STORY-047)."""

from PySide6.QtWidgets import QApplication, QStatusBar, QWidget
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
import shiboken6

from ollama_llm_bench.adapters.notification_service import make_notification_service


@pytest.fixture
def status_bar(qtbot: QtBot) -> QStatusBar:
    bar = QStatusBar()
    qtbot.addWidget(bar)
    return bar


@pytest.fixture
def parent_widget(qtbot: QtBot) -> QWidget:
    widget = QWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.mark.parametrize("method_name", ["show_info", "show_warning"])
def test_info_and_warning_show_transient_toast(
    status_bar: QStatusBar, parent_widget: QWidget, method_name: str
) -> None:
    """Proves: STORY-047-AC-1

    show_info and show_warning each show a transient toast carrying the given
    text on the status bar and return without raising (table-driven over
    info and warning).
    """
    # Arrange
    service = make_notification_service(status_bar=status_bar, parent=parent_widget)
    method = getattr(service, method_name)

    # Act
    result = method("Hello notification", 1234)

    # Assert
    assert result is None
    assert status_bar.currentMessage() == "Hello notification"


def test_show_error_blocking_flag_selects_modal_or_toast(
    mocker: MockerFixture, status_bar: QStatusBar, parent_widget: QWidget
) -> None:
    """Proves: STORY-047-AC-2

    show_error(text, blocking=True) shows a modal error dialog carrying that
    text; show_error(text, blocking=False) shows a transient error toast
    instead -- the blocking flag selects modal vs. toast.
    """
    # Arrange
    service = make_notification_service(status_bar=status_bar, parent=parent_widget)
    critical_mock = mocker.patch(
        "ollama_llm_bench.adapters.notification_service._internal.qt_notification_service"
        ".QMessageBox.critical"
    )

    # Act
    service.show_error("Toast error", blocking=False)
    toast_message = status_bar.currentMessage()
    service.show_error("Modal error", blocking=True)

    # Assert
    assert toast_message == "Toast error"
    critical_mock.assert_called_once_with(parent_widget, "Error", "Modal error")


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("show_info", ("Info text",)),
        ("show_warning", ("Warning text",)),
        ("show_error", ("Error text",)),
    ],
)
def test_all_methods_are_synchronous_and_never_raise(
    qapp: QApplication, method_name: str, args: tuple[str, ...]
) -> None:
    """Proves: STORY-047-AC-3

    When any of show_info, show_warning, or show_error is called, the call is
    synchronous and returns without raising to the caller (the never-raises
    contract holds) -- even when the underlying Qt widget has already been
    destroyed.
    """
    # Arrange
    status_bar = QStatusBar()
    parent_widget = QWidget()
    service = make_notification_service(status_bar=status_bar, parent=parent_widget)
    shiboken6.delete(status_bar)
    shiboken6.delete(parent_widget)

    # Act
    result = getattr(service, method_name)(*args)

    # Assert
    assert result is None
