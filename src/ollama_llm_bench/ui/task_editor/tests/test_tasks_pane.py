"""Colocated unit test for the Tasks pane's Add/Duplicate task_id generation
through real user interaction (STORY-068-AC-3)."""

from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QPushButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader, FakeTaskFileValidator
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor import TaskEditorCollaborators, make_task_editor_workspace
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeEventBus,
    FakeFileSystemActions,
    make_clean_validation_result,
)

_ADDED_TASK_COUNT = 2
_DUPLICATED_TASK_COUNT = 3


def test_add_and_duplicate_task_id_generation(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-068-AC-3

    Given the active file, clicking Add Task appends a blank task with the
    generated ``<filename_stem>_new_<N>`` id, selected, and marks the file
    dirty; clicking Duplicate on the now-selected task inserts a clone below
    it with a unique ``_copy<N>`` id.
    """
    # Arrange
    source_path = tmp_path / "sample_tasks.yaml"
    source_path.write_text(
        "tasks:\n  - task_id: existing_one\n    question: Q?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
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
        file_system_actions=FakeFileSystemActions(),
    )
    widget = make_task_editor_workspace(bus=FakeEventBus(), collaborators=collaborators)
    qtbot.addWidget(widget)
    open_file_button = cast(
        "QPushButton", widget.findChild(QPushButton, "task_editor.toolbar.open_file")
    )
    qtbot.mouseClick(open_file_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
    tasks_list = cast("QListWidget", widget.findChild(QListWidget, "task_editor.tasks_pane.list"))
    add_button = cast("QPushButton", widget.findChild(QPushButton, "task_editor.tasks_pane.add"))

    # Act -- add
    qtbot.mouseClick(add_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs

    # Assert -- add
    assert tasks_list.count() == _ADDED_TASK_COUNT
    assert "sample_tasks_new_1" in tasks_list.item(1).text()
    assert tasks_list.item(1).isSelected()

    # Act -- duplicate the newly added (selected) task
    duplicate_button = cast(
        "QPushButton", widget.findChild(QPushButton, "task_editor.tasks_pane.duplicate")
    )
    qtbot.mouseClick(duplicate_button, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs

    # Assert -- duplicate
    assert tasks_list.count() == _DUPLICATED_TASK_COUNT
    assert "sample_tasks_new_1_copy1" in tasks_list.item(2).text()
