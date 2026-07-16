"""Tests for adapters/notification_service (STORY-047)."""

from PySide6.QtWidgets import QStatusBar, QWidget
import pytest
from pytestqt.qtbot import QtBot

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
