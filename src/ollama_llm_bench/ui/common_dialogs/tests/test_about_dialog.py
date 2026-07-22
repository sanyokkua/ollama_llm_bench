"""Colocated unit tests for the About dialog (STORY-070)."""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget
import pytest
from pytest_mock import MockerFixture, MockType
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, EventBus, GlobalMessageEvent
from ollama_llm_bench.ui.common_dialogs import make_about_dialog
from ollama_llm_bench.ui.common_dialogs.models import AboutDialogCollaborators

if TYPE_CHECKING:
    from ollama_llm_bench.ui.common_dialogs._internal.about_view import AboutDialog


def _make_collaborators(mocker: MockerFixture) -> AboutDialogCollaborators:
    return AboutDialogCollaborators(
        clipboard=mocker.Mock(spec=Clipboard),
        file_system_actions=mocker.Mock(spec=FileSystemActions),
        event_bus=mocker.Mock(spec=EventBus),
    )


def test_version_line_omitted_when_absent(
    qtbot: QtBot, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Proves: STORY-070-AC-1

    Given the About dialog is built without an injected build-version string,
    when it renders, then the version line is omitted entirely and the name,
    description, repository link, and path row are unaffected.
    """
    # Arrange
    collaborators = _make_collaborators(mocker)
    data_folder_path = str(tmp_path / "app-data")
    # Act
    dialog = make_about_dialog(
        collaborators=collaborators, version=None, data_folder_path=data_folder_path
    )
    qtbot.addWidget(dialog)
    # Assert
    assert dialog.findChild(QLabel, "common_dialogs.about.version") is None
    assert dialog.findChild(QLabel, "common_dialogs.about.app_name") is not None
    assert dialog.findChild(QLabel, "common_dialogs.about.description") is not None
    assert dialog.findChild(QLabel, "common_dialogs.about.repository_link") is not None
    assert dialog.findChild(QWidget, "common_dialogs.about.path_row") is not None


def test_copy_path_and_open_folder_keep_dialog_open(
    qtbot: QtBot, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Proves: STORY-070-AC-2

    Given the About dialog, when the user clicks Copy path, then the full
    untruncated application-data-folder path is written to the clipboard and
    the dialog stays open; and when the user clicks Open folder, then the
    folder is revealed via the OS adapter and the dialog stays open.
    """
    # Arrange
    clipboard = mocker.Mock(spec=Clipboard)
    file_system_actions = mocker.Mock(spec=FileSystemActions)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = AboutDialogCollaborators(
        clipboard=clipboard, file_system_actions=file_system_actions, event_bus=event_bus
    )
    long_data_folder_path = str(tmp_path / ("very-long-segment/" * 15) / "app-data")
    dialog = cast(
        "AboutDialog",
        make_about_dialog(
            collaborators=collaborators,
            version="1.2.3",
            data_folder_path=long_data_folder_path,
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    path_display = cast("QLabel", dialog.findChild(QLabel, "common_dialogs.about.path_display"))
    displayed_path_text = path_display.text()

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.copy_path_button, Qt.MouseButton.LeftButton
    )
    is_visible_after_copy = dialog.isVisible()
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.open_folder_button, Qt.MouseButton.LeftButton
    )
    is_visible_after_open = dialog.isVisible()

    # Assert
    clipboard.copy_text.assert_called_once_with(long_data_folder_path)
    file_system_actions.open_in_file_manager.assert_called_once_with(long_data_folder_path)
    assert displayed_path_text != long_data_folder_path
    assert is_visible_after_copy is True
    assert is_visible_after_open is True


def test_about_dialog_constructs_and_shows_with_no_error_logs(
    qtbot: QtBot, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Proves: STORY-070-AC-6

    For make_about_dialog constructed with fakes for its declared Clipboard
    and FileSystemActions collaborators, mounting under qtbot and showing it
    raises no exception, reports isVisible(), and captures no error/critical
    structlog record.
    """
    # Arrange
    collaborators = _make_collaborators(mocker)
    data_folder_path = str(tmp_path / "app-data")
    # Act
    with structlog.testing.capture_logs() as captured:
        dialog = make_about_dialog(
            collaborators=collaborators, version="1.0.0", data_folder_path=data_folder_path
        )
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in captured)


def test_copy_path_success_emits_confirmation_toast(
    qtbot: QtBot, mocker: MockerFixture, tmp_path: Path
) -> None:
    """Proves: STORY-070-AC-7

    Given the About dialog, when Copy path succeeds, then it emits the
    confirmation toast ``Path copied.`` on the event bus and the dialog stays
    open.
    """
    # Arrange
    clipboard = mocker.Mock(spec=Clipboard)
    file_system_actions = mocker.Mock(spec=FileSystemActions)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = AboutDialogCollaborators(
        clipboard=clipboard, file_system_actions=file_system_actions, event_bus=event_bus
    )
    dialog = cast(
        "AboutDialog",
        make_about_dialog(
            collaborators=collaborators, version="1.0.0", data_folder_path=str(tmp_path)
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.copy_path_button, Qt.MouseButton.LeftButton
    )

    # Assert
    event_bus.emit.assert_called_once_with(
        SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="Path copied.", severity="info")
    )
    assert dialog.isVisible() is True


def _click_copy_path(dialog: "AboutDialog", qtbot: QtBot) -> None:
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.copy_path_button, Qt.MouseButton.LeftButton
    )


def _click_open_folder(dialog: "AboutDialog", qtbot: QtBot) -> None:
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.open_folder_button, Qt.MouseButton.LeftButton
    )


def _activate_repository_link(dialog: "AboutDialog", qtbot: QtBot) -> None:
    del qtbot  # unused; kept for a uniform trigger signature across parametrize cases
    link = cast("QLabel", dialog.findChild(QLabel, "common_dialogs.about.repository_link"))
    link.linkActivated.emit("repository")


@pytest.mark.parametrize(
    "trigger",
    [_click_open_folder, _activate_repository_link],
    ids=["open_folder", "repository_link"],
)
def test_open_folder_and_repository_link_success_emit_no_toast(
    qtbot: QtBot,
    mocker: MockerFixture,
    tmp_path: Path,
    trigger: Callable[["AboutDialog", QtBot], None],
) -> None:
    """Proves: STORY-070-AC-7

    Given the About dialog, when Open folder or the ``Project on GitHub``
    link succeeds, then no confirmation toast is emitted on the event bus --
    only Copy path and Copy Details define a success toast (about_dialog.md
    §6, §8) -- and the dialog stays open.
    """
    # Arrange
    clipboard = mocker.Mock(spec=Clipboard)
    file_system_actions = mocker.Mock(spec=FileSystemActions)
    event_bus = mocker.Mock(spec=EventBus)
    collaborators = AboutDialogCollaborators(
        clipboard=clipboard, file_system_actions=file_system_actions, event_bus=event_bus
    )
    dialog = cast(
        "AboutDialog",
        make_about_dialog(
            collaborators=collaborators, version="1.0.0", data_folder_path=str(tmp_path)
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Act
    trigger(dialog, qtbot)

    # Assert
    event_bus.emit.assert_not_called()
    assert dialog.isVisible() is True


def _fail_copy_path(clipboard: MockType, file_system_actions: MockType) -> None:
    clipboard.copy_text.side_effect = OsAdapterError(message="clipboard unavailable")


def _fail_open_folder(clipboard: MockType, file_system_actions: MockType) -> None:
    del clipboard  # unused; kept for a uniform configure-failure signature
    file_system_actions.open_in_file_manager.side_effect = OsAdapterError(message="no file manager")


def _fail_repository_link(clipboard: MockType, file_system_actions: MockType) -> None:
    del clipboard  # unused; kept for a uniform configure-failure signature
    file_system_actions.open_url.side_effect = OsAdapterError(message="no default browser")


class _FailureCase(NamedTuple):
    """One (configure_failure, trigger, expected_message) row for the failure-toast table."""

    configure_failure: Callable[[MockType, MockType], None]
    trigger: Callable[["AboutDialog", QtBot], None]
    expected_message: str


@pytest.mark.parametrize(
    "case",
    [
        _FailureCase(_fail_copy_path, _click_copy_path, "Could not copy the path."),
        _FailureCase(_fail_open_folder, _click_open_folder, "Could not open the folder."),
        _FailureCase(
            _fail_repository_link,
            _activate_repository_link,
            "Could not open the repository link.",
        ),
    ],
    ids=["copy_path_failure", "open_folder_failure", "repository_link_failure"],
)
def test_action_failure_emits_failure_toast_and_keeps_dialog_open(
    qtbot: QtBot,
    mocker: MockerFixture,
    tmp_path: Path,
    case: _FailureCase,
) -> None:
    """Proves: STORY-070-AC-7

    Given any of Copy path (EC-AB-3), Open folder (EC-AB-2), or the
    ``Project on GitHub`` link (EC-AB-7) raises ``OsAdapterError``, then the
    dialog emits the matching failure toast, stays open, and no exception
    propagates out of the slot.
    """
    # Arrange
    clipboard = mocker.Mock(spec=Clipboard)
    file_system_actions = mocker.Mock(spec=FileSystemActions)
    event_bus = mocker.Mock(spec=EventBus)
    case.configure_failure(clipboard, file_system_actions)
    collaborators = AboutDialogCollaborators(
        clipboard=clipboard, file_system_actions=file_system_actions, event_bus=event_bus
    )
    dialog = cast(
        "AboutDialog",
        make_about_dialog(
            collaborators=collaborators, version="1.0.0", data_folder_path=str(tmp_path)
        ),
    )
    qtbot.addWidget(dialog)
    dialog.show()

    # Act
    case.trigger(dialog, qtbot)

    # Assert
    event_bus.emit.assert_called_once_with(
        SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text=case.expected_message, severity="error")
    )
    assert dialog.isVisible() is True
