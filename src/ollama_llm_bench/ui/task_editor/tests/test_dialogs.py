"""Colocated unit test for the dirty-leave/quit Save-choice confirmation
dialog (STORY-069-AC-6).
"""

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeFileSystemActions,
    ScratchAwareTaskFileValidator,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)


def test_dirty_leave_shows_save_choice_dialog(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-069-AC-6

    Given one or more dirty buffers, when the user switches to the Benchmark
    workspace or quits, then the "Save changes to N file(s)?" dialog is shown
    with Save All / Discard All / Cancel, and Cancel keeps the editor
    unchanged.
    """
    # Arrange
    source_path = tmp_path / "dirty.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    collaborators = TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
    )
    controller, _bus = make_bound_task_editor_controller(qtbot=qtbot, collaborators=collaborators)
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()
    dirty_document_before = copy.deepcopy(controller._buffers[0].document)

    captured_button_texts: list[str] = []

    def _click_cancel() -> None:
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        captured_button_texts.extend(button.text() for button in dialog.buttons())
        cancel_button = next(
            button
            for button in dialog.buttons()
            if dialog.buttonRole(button) == QMessageBox.ButtonRole.RejectRole
        )
        qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
            cancel_button, Qt.MouseButton.LeftButton
        )

    QTimer.singleShot(0, _click_cancel)

    # Act
    may_proceed = controller.confirm_and_prepare_leave()

    # Assert
    assert may_proceed is False
    assert set(captured_button_texts) == {"Discard All", "Cancel", "Save All"}
    assert controller._buffers[0].is_dirty
    assert controller._buffers[0].document == dirty_document_before
