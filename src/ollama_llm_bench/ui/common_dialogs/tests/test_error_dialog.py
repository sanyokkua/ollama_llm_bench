"""Colocated unit tests for the generic Error dialog (STORY-070).

``make_error_dialog`` requires fake ``Clipboard`` and ``EventBus``
collaborators (STORY-070-AC-6's fake-collaborator table) -- ``error_dialog.md``
§9's Copy Details action and EC-ERR-6 need the clipboard; the AC-7
confirmation/failure toast needs the event bus. Every test below constructs
``make_error_dialog`` with ``mocker.Mock(spec=Clipboard)`` and
``mocker.Mock(spec=EventBus)`` fakes.
"""

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QTextEdit
import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, EventBus, GlobalMessageEvent
from ollama_llm_bench.ui.common_dialogs import make_error_dialog
from ollama_llm_bench.ui.common_dialogs.models import (
    ErrorDialogAction,
    ErrorDialogPattern,
    ErrorDialogPayload,
)

if TYPE_CHECKING:
    from ollama_llm_bench.ui.common_dialogs._internal.error_view import ErrorDialog


def _make_payload(
    *, pattern: ErrorDialogPattern, detail: str | None, mocker: MockerFixture
) -> ErrorDialogPayload:
    action = (
        ErrorDialogAction(label="Fix in Settings", callback=mocker.Mock())
        if pattern is ErrorDialogPattern.ACTION_AVAILABLE
        else None
    )
    quit_callback = mocker.Mock() if pattern is ErrorDialogPattern.FATAL else None
    return ErrorDialogPayload(
        title="Something failed",
        message="A plain-language description of the failure.",
        detail=detail,
        pattern=pattern,
        action=action,
        quit_callback=quit_callback,
    )


@pytest.mark.parametrize(
    ("pattern", "detail", "expected_buttons"),
    [
        (
            ErrorDialogPattern.RECOVERABLE,
            "diagnostic detail",
            (True, True, False, False),
        ),
        (ErrorDialogPattern.RECOVERABLE, None, (False, True, False, False)),
        (
            ErrorDialogPattern.ACTION_AVAILABLE,
            "diagnostic detail",
            (True, True, True, False),
        ),
        (ErrorDialogPattern.ACTION_AVAILABLE, None, (False, True, True, False)),
        (ErrorDialogPattern.FATAL, "diagnostic detail", (True, False, False, True)),
        (ErrorDialogPattern.FATAL, None, (False, False, False, True)),
    ],
    ids=[
        "recoverable_with_detail",
        "recoverable_no_detail",
        "action_available_with_detail",
        "action_available_no_detail",
        "fatal_with_detail",
        "fatal_no_detail",
    ],
)
def test_footer_buttons_per_pattern(
    qtbot: QtBot,
    mocker: MockerFixture,
    pattern: ErrorDialogPattern,
    detail: str | None,
    expected_buttons: tuple[bool, bool, bool, bool],
) -> None:
    """Proves: STORY-070-AC-3

    For each error pattern, the Error dialog renders the specified footer
    button set: Copy Details (if detail) for every pattern; Close (primary)
    for recoverable and action-available only, never fatal; the recovery
    action button only for action-available; Quit (destructive primary)
    only for fatal. ``expected_buttons`` is
    ``(copy_details, close, action, quit)``.
    """
    # Arrange
    payload = _make_payload(pattern=pattern, detail=detail, mocker=mocker)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    # Act
    dialog = make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus)
    qtbot.addWidget(dialog)
    has_copy_details = (
        dialog.findChild(QPushButton, "common_dialogs.error.copy_details_button") is not None
    )
    has_close = dialog.findChild(QPushButton, "common_dialogs.error.close_button") is not None
    has_action = dialog.findChild(QPushButton, "common_dialogs.error.action_button") is not None
    has_quit = dialog.findChild(QPushButton, "common_dialogs.error.quit_button") is not None
    # Assert
    assert (has_copy_details, has_close, has_action, has_quit) == expected_buttons


def test_no_detail_hides_detail_block(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-070-AC-4

    Given the caller supplies no detail, when the Error dialog renders, then
    the detail block and the Copy Details button are both absent.
    """
    # Arrange
    payload = _make_payload(pattern=ErrorDialogPattern.RECOVERABLE, detail=None, mocker=mocker)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    # Act
    dialog = make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus)
    qtbot.addWidget(dialog)
    # Assert
    assert dialog.findChild(QTextEdit, "common_dialogs.error.detail") is None
    assert dialog.findChild(QPushButton, "common_dialogs.error.copy_details_button") is None


def test_fatal_pattern_quit_only_no_escape(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-070-AC-5

    Given the fatal pattern, when the dialog is shown, then Escape does not
    dismiss it and there is no close (X) glyph; the only exit is the Quit
    button, which runs the clean-shutdown sequence.
    """
    # Arrange
    quit_callback = mocker.Mock()
    payload = ErrorDialogPayload(
        title="Fatal failure",
        message="The application encountered an unrecoverable error.",
        detail=None,
        pattern=ErrorDialogPattern.FATAL,
        action=None,
        quit_callback=quit_callback,
    )
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    dialog = cast(
        "ErrorDialog",
        make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    has_close_button_hint = bool(dialog.windowFlags() & Qt.WindowType.WindowCloseButtonHint)

    # Act
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)  # type: ignore[no-untyped-call]
    still_visible_after_escape = dialog.isVisible()
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.quit_button, Qt.MouseButton.LeftButton
    )

    # Assert
    assert dialog.findChild(QPushButton, "common_dialogs.error.close_button") is None
    assert dialog.quit_button.property("role") == "destructive-button"
    assert has_close_button_hint is False
    assert still_visible_after_escape is True
    quit_callback.assert_called_once()


@pytest.mark.parametrize(
    ("pattern", "detail"),
    [
        (ErrorDialogPattern.RECOVERABLE, "diagnostic detail"),
        (ErrorDialogPattern.ACTION_AVAILABLE, None),
        (ErrorDialogPattern.FATAL, "diagnostic detail"),
    ],
    ids=["recoverable_with_detail", "action_available_no_detail", "fatal_with_detail"],
)
def test_error_dialog_constructs_and_shows_with_no_error_logs(
    qtbot: QtBot,
    mocker: MockerFixture,
    pattern: ErrorDialogPattern,
    detail: str | None,
) -> None:
    """Proves: STORY-070-AC-6

    For make_error_dialog constructed with a fake Clipboard collaborator (see
    the module docstring's discrepancy note), mounting under qtbot and
    showing it raises no exception, reports isVisible(), and captures no
    error/critical structlog record -- across a detail-present and a
    detail-absent case.
    """
    # Arrange
    payload = _make_payload(pattern=pattern, detail=detail, mocker=mocker)
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    # Act
    with structlog.testing.capture_logs() as captured:
        dialog = make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in captured)


def test_copy_details_success_emits_confirmation_toast(qtbot: QtBot, mocker: MockerFixture) -> None:
    """Proves: STORY-070-AC-7

    Given the Error dialog, when Copy Details succeeds, then it emits the
    confirmation toast ``Details copied.`` on the event bus and the dialog
    stays open.
    """
    # Arrange
    payload = _make_payload(
        pattern=ErrorDialogPattern.RECOVERABLE, detail="diagnostic detail", mocker=mocker
    )
    clipboard = mocker.Mock(spec=Clipboard)
    event_bus = mocker.Mock(spec=EventBus)
    dialog = cast(
        "ErrorDialog",
        make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.copy_details_button, Qt.MouseButton.LeftButton
    )

    # Assert
    event_bus.emit.assert_called_once_with(
        SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="Details copied.", severity="info")
    )
    assert dialog.isVisible() is True


def test_copy_details_failure_emits_toast_and_keeps_dialog_open(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    """Proves: STORY-070-AC-7

    Given the Error dialog, when Copy Details raises OsAdapterError
    (EC-ERR-6), then the dialog emits the failure toast
    ``Could not copy to the clipboard.``, stays open, and no exception
    propagates out of the slot.
    """
    # Arrange
    payload = _make_payload(
        pattern=ErrorDialogPattern.RECOVERABLE, detail="diagnostic detail", mocker=mocker
    )
    clipboard = mocker.Mock(spec=Clipboard)
    clipboard.copy_text.side_effect = OsAdapterError(message="clipboard unavailable")
    event_bus = mocker.Mock(spec=EventBus)
    dialog = cast(
        "ErrorDialog",
        make_error_dialog(payload=payload, clipboard=clipboard, event_bus=event_bus),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.copy_details_button, Qt.MouseButton.LeftButton
    )

    # Assert
    event_bus.emit.assert_called_once_with(
        SIGNAL_GLOBAL_MESSAGE,
        GlobalMessageEvent(text="Could not copy to the clipboard.", severity="error"),
    )
    assert dialog.isVisible() is True
