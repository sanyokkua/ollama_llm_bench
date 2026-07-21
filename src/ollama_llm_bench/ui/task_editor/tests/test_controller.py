"""Colocated unit tests for ``TaskEditorController`` (STORY-068-AC-4, AC-6).

Follows ``ui/progress/tests/test_controller.py``'s precedent: bind the
controller to a real ``TaskEditorView`` (never a mock -- a widget is never
replaced by a mock, per ``testing-standard-pyqt``) and read the derived state
back off the controller's own open-buffer collection, since neither AC needs
a rendered glyph to be proven.
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_WORKSPACE_CHANGED,
    RunStartedEvent,
    RunStoppedEvent,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader, FakeTaskFileValidator
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeFileSystemActions,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)


def _collaborators(
    *,
    gateway: FakeTaskEditorGateway,
    native_pickers: FakeNativePickers,
    validator: FakeTaskFileValidator,
) -> TaskEditorCollaborators:
    return TaskEditorCollaborators(
        gateway=gateway,
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        file_system_actions=FakeFileSystemActions(),
    )


def test_run_started_marks_in_use_files(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-068-AC-4

    Given a run is active, when a ``_run_started`` event carries the run's
    task paths, then every open file whose path is in that list is marked
    in-use; and when a terminal run event arrives, then the in-use markers
    clear.
    """
    # Arrange
    path_a = tmp_path / "a.yaml"
    path_a.write_text("tasks:\n  - task_id: a1\n    question: Qa?\n", encoding="utf-8")
    path_b = tmp_path / "b.yaml"
    path_b.write_text("tasks:\n  - task_id: b1\n    question: Qb?\n", encoding="utf-8")
    validator = FakeTaskFileValidator()
    validator.set_validation_result(str(path_a), make_clean_validation_result(str(path_a)))
    validator.set_validation_result(str(path_b), make_clean_validation_result(str(path_b)))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(path_a), str(path_b)))
    gateway = FakeTaskEditorGateway()
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            gateway=gateway, native_pickers=native_pickers, validator=validator
        ),
    )
    controller.on_open_file_clicked()
    gateway.set_active_run_task_paths((str(path_a),))

    # Act -- run started
    bus.emit(
        SIGNAL_RUN_STARTED,
        RunStartedEvent(
            run_id=1,
            run_name="Run 1",
            run_mode=RunMode.TASKS,
            started_at="2026-07-21T00:00:00+00:00",
            total_tasks=1,
            test_targets=(),
        ),
    )
    in_use_after_start = {
        buffer.source_path: buffer.is_in_use_by_run for buffer in controller._buffers
    }

    # Act -- run terminal
    bus.emit(
        SIGNAL_RUN_STOPPED,
        RunStoppedEvent(
            run_id=1, stopped_at="2026-07-21T00:01:00+00:00", completed_tasks=0, total_tasks=1
        ),
    )
    in_use_after_terminal = {
        buffer.source_path: buffer.is_in_use_by_run for buffer in controller._buffers
    }

    # Assert
    assert in_use_after_start == {str(path_a): True, str(path_b): False}
    assert in_use_after_terminal == {str(path_a): False, str(path_b): False}


def test_workspace_switch_commits_field_edit(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-068-AC-6

    Covers: EC-WS-4

    Given the workspace is switched away while a Task Editor field holds
    uncommitted text, when the switch is handled, then the in-progress field
    edit is committed to the in-memory buffer and the buffer's dirty state is
    preserved.
    """
    # Arrange
    source_path = tmp_path / "editable.yaml"
    source_path.write_text(
        "tasks:\n  - task_id: t1\n    question: Old question?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            gateway=FakeTaskEditorGateway(), native_pickers=native_pickers, validator=validator
        ),
    )
    controller.on_open_file_clicked()
    controller.stage_field_edit(
        buffer_index=0, task_index=0, field_name="question", draft_text="New question text"
    )

    # Act
    bus.emit(
        SIGNAL_WORKSPACE_CHANGED,
        WorkspaceChangedEvent(workspace="benchmark", previous_workspace="task_editor"),
    )

    # Assert
    committed_buffer = controller._buffers[0]
    assert committed_buffer.document["tasks"][0]["question"] == "New question text"
    assert committed_buffer.is_dirty


def test_file_change_watcher_trigger_marks_external_changed(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-068-AC-2

    Given a file open in the controller through the real open path, when the
    ``FileChangeWatcher`` fires its change callback for that file's path, then
    the controller flips the buffer's ``is_external_changed`` state and the
    rendered Files-pane row shows the reload-pending badge -- exercising the
    controller-owned ExternalChanged transition, not just its rendering.
    """
    # Arrange
    source_path = tmp_path / "watched.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = FakeTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    watcher = FakeFileChangeWatcher()
    collaborators = TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=watcher,
        native_pickers=native_pickers,
        file_system_actions=FakeFileSystemActions(),
    )
    controller, _bus = make_bound_task_editor_controller(qtbot=qtbot, collaborators=collaborators)
    controller.on_open_file_clicked()
    buffer_before_change = controller._buffers[0]
    assert buffer_before_change.is_external_changed is False

    # Act
    watcher.trigger_change(str(source_path))

    # Assert
    buffer_after_change = controller._buffers[0]
    assert buffer_after_change.is_external_changed is True
    assert controller._view is not None
    rendered_row_text = controller._view._files_pane._list.item(0).text()
    assert "[reload pending]" in rendered_row_text
