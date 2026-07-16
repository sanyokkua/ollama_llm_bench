"""Colocated unit tests for ``adapters.clipboard`` (STORY-048)."""

from PySide6.QtGui import QClipboard, QGuiApplication
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.clipboard import make_clipboard
from ollama_llm_bench.backend.errors import OsAdapterError


def test_copy_text_places_exact_text_on_clipboard(qtbot: QtBot) -> None:
    """Proves: STORY-048-AC-3

    Places exactly the given text on the real Qt system clipboard.
    """
    # Arrange
    clipboard = make_clipboard()
    # Act
    clipboard.copy_text("hello ollama_llm_bench")
    # Assert
    assert QGuiApplication.clipboard().text() == "hello ollama_llm_bench"


def test_integration_failure_raises_os_adapter_error(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-048-AC-5

    A clipboard-subsystem failure raises OsAdapterError chaining the original
    cause, with no raw platform exception text on the message.
    """
    # Arrange
    fake_clipboard = mocker.Mock(spec=QClipboard)
    fake_clipboard.setText.side_effect = RuntimeError("X11 selection lost: /secret/detail")
    mocker.patch(
        "ollama_llm_bench.adapters.clipboard._internal.qt_clipboard.QGuiApplication.clipboard",
        return_value=fake_clipboard,
    )
    clipboard = make_clipboard()
    # Act / Assert
    with pytest.raises(OsAdapterError) as exc_info:
        clipboard.copy_text("some text")
    assert "/secret/detail" not in exc_info.value.message
    assert isinstance(exc_info.value.__cause__, RuntimeError)
