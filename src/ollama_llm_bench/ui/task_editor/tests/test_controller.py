"""Colocated unit tests for ``TaskEditorController`` (STORY-068-AC-4, AC-6;
STORY-069-AC-2, AC-3, AC-4).

Follows ``ui/progress/tests/test_controller.py``'s precedent: bind the
controller to a real ``TaskEditorView`` (never a mock -- a widget is never
replaced by a mock, per ``testing-standard-pyqt``) and read the derived state
back off the controller's own open-buffer collection, since neither AC needs
a rendered glyph to be proven.
"""

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.domain import RunMode
from ollama_llm_bench.backend.events import (
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_TASK_FILE_CHANGED,
    SIGNAL_WORKSPACE_CHANGED,
    RunStartedEvent,
    RunStoppedEvent,
    TaskFileChangedEvent,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.backend.task_files import (
    FileValidationResult,
    TaskValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidationSeverity,
    make_task_file_validator,
)
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor._internal.view_model_select import (
    select_task_editor_view_model,
)
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators, ValidationState
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeFileSystemActions,
    ScratchAwareTaskFileValidator,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)

_TWO_TASKS_AFTER_SAVE = 2


def _collaborators(
    *,
    gateway: FakeTaskEditorGateway,
    native_pickers: FakeNativePickers,
    validator: ScratchAwareTaskFileValidator,
) -> TaskEditorCollaborators:
    return TaskEditorCollaborators(
        gateway=gateway,
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
    )


def _file_result_with_field_error(source_path: str, field_name: str) -> FileValidationResult:
    """Build a hard-error ``FileValidationResult`` carrying one FIELD-level issue
    on ``field_name`` of the file's first (only) task -- the UI-mapping layer
    treats every field name identically (STORY-069's own notes), so this fake
    stands in for ``task_id``/``golden_answer`` where the real cascade has no
    rule yet."""
    issue = ValidationIssue(
        level=ValidationLevel.FIELD,
        severity=ValidationSeverity.ERROR,
        rule=f"empty_{field_name}",
        message=f"{field_name} is empty after whitespace trimming.",
        task_index=0,
        field_name=field_name,
    )
    return FileValidationResult(
        source_path=source_path,
        severity=ValidationSeverity.ERROR,
        save_enabled=False,
        task_results=(
            TaskValidationResult(
                task_index=0, task_id="t1", severity=ValidationSeverity.ERROR, issues=(issue,)
            ),
        ),
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
    validator = ScratchAwareTaskFileValidator()
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
    validator = ScratchAwareTaskFileValidator()
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
    validator = ScratchAwareTaskFileValidator()
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
        clipboard=FakeClipboard(),
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


def _view_model_for(controller: object) -> object:
    """Re-derive the current ``TaskEditorViewModel`` straight from the
    controller's own open-buffer state -- the same pure call
    ``_push_view_model`` makes internally, used here so a test can assert on
    the derived view model without needing a rendered glyph."""
    return select_task_editor_view_model(
        buffers=controller._buffers,  # type: ignore[attr-defined]
        active_buffer_index=controller._active_buffer_index,  # type: ignore[attr-defined]
        active_task_index=controller._active_task_index,  # type: ignore[attr-defined]
        preview_shown=False,
        preview_text="",
    )


@pytest.mark.parametrize("field_name", ["task_id", "question", "golden_answer"])
def test_missing_required_field_disables_save(
    qtbot: QtBot, tmp_path: Path, field_name: str
) -> None:
    """Proves: STORY-069-AC-2

    Given a task with an empty ``task_id``, ``question``, or
    ``golden_answer``, when the validation cascade runs, then that field
    carries a hard-error strip, the task and file badges aggregate to error,
    and the file's Save is disabled.
    """
    # Arrange
    source_path = tmp_path / "invalid.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), _file_result_with_field_error(str(source_path), field_name)
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            gateway=FakeTaskEditorGateway(), native_pickers=native_pickers, validator=validator
        ),
    )

    # Act
    controller.on_open_file_clicked()

    # Assert
    view_model = _view_model_for(controller)
    field_row = next(row for row in view_model.field_rows if row.field_name == field_name)  # type: ignore[attr-defined]
    assert field_row.validation_state is ValidationState.ERROR
    assert view_model.tasks[0].validation_state is ValidationState.ERROR  # type: ignore[attr-defined]
    assert view_model.files[0].validation_state is ValidationState.ERROR  # type: ignore[attr-defined]
    assert view_model.toolbar_state.save_enabled is False  # type: ignore[attr-defined]


def test_empty_question_via_real_validator_disables_save(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-069-AC-2

    Given a task with an empty ``question``, when the real
    ``TaskFileValidator`` cascade runs end-to-end, then the ``question``
    field carries a hard-error strip and the file's Save is disabled --
    proving the UI-mapping layer against the one field-level rule the real
    cascade already implements (``empty_question``).
    """
    # Arrange
    source_path = tmp_path / "invalid_question.yaml"
    source_path.write_text('tasks:\n  - task_id: t1\n    question: ""\n', encoding="utf-8")
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    collaborators = TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=make_task_file_validator(),
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
    )
    controller, _bus = make_bound_task_editor_controller(qtbot=qtbot, collaborators=collaborators)

    # Act
    controller.on_open_file_clicked()

    # Assert
    view_model = _view_model_for(controller)
    question_row = next(row for row in view_model.field_rows if row.field_name == "question")  # type: ignore[attr-defined]
    assert question_row.validation_state is ValidationState.ERROR
    assert view_model.toolbar_state.save_enabled is False  # type: ignore[attr-defined]


def test_save_all_skips_hard_error_files(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-069-AC-3

    Given a file with no hard error and at least one dirty file, when Save
    All runs, then it saves every dirty hard-error-free file through the
    YAML Formatter and skips (leaving dirty) every file that still has a
    hard error.
    """
    # Arrange
    saveable_path = tmp_path / "saveable.yaml"
    saveable_path.write_text("tasks:\n  - task_id: s1\n    question: Q?\n", encoding="utf-8")
    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text("tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(saveable_path), make_clean_validation_result(str(saveable_path))
    )
    validator.set_validation_result(
        str(broken_path), _file_result_with_field_error(str(broken_path), "question")
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(saveable_path), str(broken_path)))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            gateway=FakeTaskEditorGateway(), native_pickers=native_pickers, validator=validator
        ),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()  # dirties the active (broken) buffer, index 1
    controller.on_file_row_selected(0)
    controller.on_add_task_clicked()  # dirties the saveable buffer, index 0

    # Act
    controller.on_save_all_clicked()

    # Assert -- the mypy-strict-visible narrowing quirk of asserting the same
    # dirty flag both before and after a mutating call is avoided by not
    # re-checking pre-Act dirtiness here; the on-disk assertions below already
    # prove Arrange succeeded (a never-dirtied file could not gain a 2nd task).
    assert controller._buffers[0].is_dirty is False
    assert controller._buffers[1].is_dirty is True
    saved_document = make_yaml_formatter().load_document(str(saveable_path))
    assert len(saved_document["tasks"]) == _TWO_TASKS_AFTER_SAVE
    unsaved_document = make_yaml_formatter().load_document(str(broken_path))
    assert len(unsaved_document["tasks"]) == 1


def test_successful_save_emits_task_file_changed(qtbot: QtBot, tmp_path: Path) -> None:
    """Proves: STORY-069-AC-4

    Given the active file is saved successfully, when the Save completes,
    then the file returns to the clean/Loaded state and a
    ``_task_file_changed`` event carrying the saved path is emitted.
    """
    # Arrange
    source_path = tmp_path / "clean.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
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
    controller.on_add_task_clicked()  # dirties buffer 0 (the only open file)

    # Act
    controller.on_save_clicked()

    # Assert -- no pre-Act dirty re-check here (see the sibling Save All test's
    # note on the mypy narrowing quirk this avoids); the emitted event and the
    # clean state below already prove the save actually ran.
    assert controller._buffers[0].is_dirty is False
    task_file_changed_events = [
        payload for signal_name, payload in bus.emitted if signal_name == SIGNAL_TASK_FILE_CHANGED
    ]
    assert task_file_changed_events
    changed_event = task_file_changed_events[-1]
    assert isinstance(changed_event, TaskFileChangedEvent)
    assert changed_event.path == str(source_path)
