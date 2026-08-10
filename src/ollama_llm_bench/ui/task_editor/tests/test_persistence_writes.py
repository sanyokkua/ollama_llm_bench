"""Colocated unit tests for the Task Editor's persisted-setting writers (STORY-114).

``09_Task_Editor/description.md`` §6's persistence table names exactly three write
triggers for ``ui.task_editor_last_folder`` -- a file is opened, a folder is opened,
a new file is created -- and this file is a table over those three rows. It is the
first consumer of ``testing.FakeTaskEditorGateway.recorded_set_setting_calls``,
which had no reader anywhere in the tree before this story.

The companion rows for ``ui.active_workspace`` live in
``ui/main_window/_internal/tests/test_controller.py``, because that setting is
written by the Main Window's controller, not this module's.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Final, NamedTuple, override

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers import FilePickerOptions
from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor._internal.controller import TaskEditorController
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeFileSystemActions,
    ScratchAwareTaskFileValidator,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)

_LAST_FOLDER_KEY: Final[str] = "ui.task_editor_last_folder"
_TASK_YAML: Final[str] = "tasks:\n  - task_id: t1\n    question: Q?\n"


class _TriggerRow(NamedTuple):
    """One §6 write trigger: how to arm the pickers for it, and how to fire it."""

    trigger: str
    arrange: Callable[[FakeNativePickers, ScratchAwareTaskFileValidator, Path], str]
    invoke: Callable[[TaskEditorController], None]


def _seed_task_file(path: Path, validator: ScratchAwareTaskFileValidator) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TASK_YAML, encoding="utf-8")
    validator.set_validation_result(str(path), make_clean_validation_result(str(path)))


def _arrange_open_file(
    pickers: FakeNativePickers, validator: ScratchAwareTaskFileValidator, tmp_path: Path
) -> str:
    """Arm the open-file picker with a file inside its own folder; expect that folder."""
    source_path = tmp_path / "opened_file_parent" / "tasks.yaml"
    _seed_task_file(source_path, validator)
    pickers.set_open_file_result((str(source_path),))
    return str(source_path.parent)


def _arrange_open_folder(
    pickers: FakeNativePickers, validator: ScratchAwareTaskFileValidator, tmp_path: Path
) -> str:
    """Arm the open-folder picker with a folder holding one task file; expect the folder."""
    folder = tmp_path / "opened_folder"
    _seed_task_file(folder / "tasks.yaml", validator)
    pickers.set_open_folder_result(str(folder))
    return str(folder)


def _arrange_new_file(
    pickers: FakeNativePickers, validator: ScratchAwareTaskFileValidator, tmp_path: Path
) -> str:
    """Arm the save picker with a not-yet-existing path; expect its parent folder."""
    target_path = tmp_path / "new_file_parent" / "tasks.yaml"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    validator.set_validation_result(
        str(target_path), make_clean_validation_result(str(target_path))
    )
    pickers.set_save_result(str(target_path))
    return str(target_path.parent)


_TRIGGER_ROWS: Final[tuple[_TriggerRow, ...]] = (
    _TriggerRow("open_file", _arrange_open_file, TaskEditorController.on_open_file_clicked),
    _TriggerRow("open_folder", _arrange_open_folder, TaskEditorController.on_open_folder_clicked),
    _TriggerRow("new_file", _arrange_new_file, TaskEditorController.on_new_file_clicked),
)


class _RecordingNativePickers(FakeNativePickers):
    """``FakeNativePickers`` widened to record the ``start_dir`` it was asked for.

    The shared fake ignores its options by design, so the pre-fill (read) half of
    §6 needs a local subclass to observe them.
    """

    def __init__(self) -> None:
        super().__init__()
        self.requested_start_dirs: list[str | None] = []

    @override
    def open_file(self, options: FilePickerOptions) -> tuple[str, ...]:
        self.requested_start_dirs.append(options.start_dir)
        return super().open_file(options)


@pytest.mark.parametrize("row", _TRIGGER_ROWS, ids=[row.trigger for row in _TRIGGER_ROWS])
def test_setting_written_per_trigger(row: _TriggerRow, qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-114-AC-5

    Given the user opens a file, opens a folder, or creates a new file, when
    that action completes, then ui.task_editor_last_folder holds the folder
    named by the persistence table in 09_Task_Editor/description.md §6.
    """
    # Arrange
    gateway = FakeTaskEditorGateway()
    pickers = FakeNativePickers()
    validator = ScratchAwareTaskFileValidator()
    expected_folder = row.arrange(pickers, validator, tmp_path)
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=TaskEditorCollaborators(
            gateway=gateway,
            task_file_loader=FakeTaskFileLoader(),
            task_file_validator=validator,
            yaml_formatter=make_yaml_formatter(),
            file_change_watcher=FakeFileChangeWatcher(),
            native_pickers=pickers,
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
        ),
    )

    # Act
    row.invoke(controller)

    # Assert
    assert gateway.recorded_set_setting_calls[-1] == (_LAST_FOLDER_KEY, expected_folder)


def test_pickers_prefill_from_the_persisted_last_folder(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-114-AC-5

    Given ui.task_editor_last_folder holds a folder from a previous session,
    when the Open File picker is raised, then it is asked to start there rather
    than wherever the OS would otherwise default to (§6's read side).
    """
    # Arrange
    gateway = FakeTaskEditorGateway()
    gateway.set_setting(_LAST_FOLDER_KEY, str(tmp_path))
    pickers = _RecordingNativePickers()
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=TaskEditorCollaborators(
            gateway=gateway,
            task_file_loader=FakeTaskFileLoader(),
            task_file_validator=ScratchAwareTaskFileValidator(),
            yaml_formatter=make_yaml_formatter(),
            file_change_watcher=FakeFileChangeWatcher(),
            native_pickers=pickers,
            clipboard=FakeClipboard(),
            file_system_actions=FakeFileSystemActions(),
        ),
    )

    # Act
    controller.on_open_file_clicked()

    # Assert
    assert pickers.requested_start_dirs == [str(tmp_path)]
