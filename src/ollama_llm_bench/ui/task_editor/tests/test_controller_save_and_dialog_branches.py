"""Colocated unit tests closing the remaining branch-coverage gaps in
``TaskEditorController`` (STORY-069) not already proven by
``test_controller.py``/``test_controller_actions.py``/``test_controller_field_editing.py``:
settings parsing, the in-use-on-save and save-failure dialogs, the
leave/quit dirty-buffer resolution branches (no-dirty / discard-all / save-all
with a remaining hard error), Save & Close, the stale-recent-file failure
path, and the buffer-close reindexing edge cases.
"""

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.events import (
    SIGNAL_GLOBAL_MESSAGE,
    SIGNAL_RUN_STARTED,
    SIGNAL_TASK_FILE_CHANGED,
    GlobalMessageEvent,
    WorkspaceChangedEvent,
)
from ollama_llm_bench.backend.task_files import (
    FileValidationResult,
    TaskValidationResult,
    ValidationIssue,
    ValidationLevel,
    ValidationSeverity,
)
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import (
    SaveFailureReason,
    SaveResult,
    make_yaml_formatter,
)
from ollama_llm_bench.backend.yaml_formatter.testing import FakeYamlFormatter
from ollama_llm_bench.ui.task_editor._internal import dialogs
from ollama_llm_bench.ui.task_editor._internal.controller import (
    TaskEditorController,
    _parse_bool_setting,
    _parse_debounce_ms,
)
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators
from ollama_llm_bench.ui.task_editor.testing import FakeFileChangeWatcher, FakeTaskEditorGateway
from ollama_llm_bench.ui.task_editor.tests.conftest import (
    FakeClipboard,
    FakeEventBus,
    FakeFileSystemActions,
    ScratchAwareTaskFileValidator,
    make_bound_task_editor_controller,
    make_clean_validation_result,
)

_THREE_BUFFERS = 3


def _collaborators(
    *,
    native_pickers: FakeNativePickers,
    validator: ScratchAwareTaskFileValidator,
    yaml_formatter: object | None = None,
    gateway: FakeTaskEditorGateway | None = None,
) -> TaskEditorCollaborators:
    return TaskEditorCollaborators(
        gateway=gateway or FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=yaml_formatter or make_yaml_formatter(),  # type: ignore[arg-type]
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
    )


# ---- settings parsing --------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [(None, True, True), ("true", False, True), ("FALSE", True, False), ("nonsense", True, False)],
)
def test_parse_bool_setting_falls_back_on_missing_or_malformed_value(
    value: str | None,
    default: bool,  # noqa: FBT001  # parametrize tuple element
    expected: bool,  # noqa: FBT001  # parametrize tuple element
) -> None:
    """``_parse_bool_setting`` falls back to its default only when the
    setting is entirely absent (``None``); any present non-``"true"``
    spelling (case-insensitive) parses as ``False``, matching the default
    only when the default itself is ``False``."""
    assert _parse_bool_setting(value, default=default) is expected


@pytest.mark.parametrize(
    ("value", "expected"), [(None, 250), ("500", 500), ("not_a_number", 250), ("-10", 0)]
)
def test_parse_debounce_ms_falls_back_on_missing_or_malformed_value(
    value: str | None, expected: int
) -> None:
    """``_parse_debounce_ms`` falls back to the spec default on a missing or
    non-numeric setting, and clamps a negative value to zero."""
    assert _parse_debounce_ms(value) == expected


# ---- stale recent-file open failure ------------------------------------------


def test_recent_file_clicked_on_a_missing_file_emits_an_error_and_forgets_it(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Reopening a recent-file entry whose file no longer exists on disk emits
    a global error message and drops the stale path from the recent list."""
    # Arrange
    missing_path = str(tmp_path / "gone.yaml")
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )
    controller._recent_files = [missing_path]

    # Act
    controller.on_recent_file_clicked(missing_path)

    # Assert
    assert controller._buffers == []
    assert missing_path not in controller._recent_files
    error_messages = [
        payload
        for signal_name, payload in bus.emitted
        if signal_name == SIGNAL_GLOBAL_MESSAGE
        and isinstance(payload, GlobalMessageEvent)
        and payload.severity == "error"
    ]
    assert error_messages


# ---- Save: in-use-on-save and save-failure dialogs ---------------------------


def test_save_clicked_is_a_noop_when_no_buffer_is_active(qtbot: QtBot) -> None:
    """Save with no open buffers is a no-op (guard branch)."""
    # Arrange
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )

    # Act
    controller.on_save_clicked()

    # Assert
    assert bus.emitted == []


def test_save_deferred_when_in_use_dialog_declines(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saving a file currently in use by a run shows the in-use dialog first;
    choosing Defer leaves the file dirty and unsaved (EC-TE-07)."""
    # Arrange
    monkeypatch.setattr(dialogs, "confirm_in_use_save", lambda: False)
    source_path = tmp_path / "in_use.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._buffers[0].is_in_use_by_run = True
    controller.on_add_task_clicked()

    # Act
    controller.on_save_clicked()

    # Assert
    assert controller._buffers[0].is_dirty
    assert not any(signal_name == SIGNAL_TASK_FILE_CHANGED for signal_name, _payload in bus.emitted)


def test_save_proceeds_when_in_use_dialog_confirms(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing Save Anyway on the in-use dialog lets the save proceed."""
    # Arrange
    monkeypatch.setattr(dialogs, "confirm_in_use_save", lambda: True)
    source_path = tmp_path / "in_use.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._buffers[0].is_in_use_by_run = True
    controller.on_add_task_clicked()

    # Act
    controller.on_save_clicked()

    # Assert
    assert controller._buffers[0].is_dirty is False


def test_save_failure_shows_the_save_failure_dialog_and_keeps_the_buffer_dirty(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the ``YamlFormatter`` reports a failed save, the save-failure
    dialog is shown with the failure reason/detail and the buffer stays
    dirty (EC-TE-10)."""
    # Arrange
    shown_failures: list[tuple[SaveFailureReason | None, str]] = []
    monkeypatch.setattr(
        dialogs,
        "show_save_failure",
        lambda *, reason, detail: shown_failures.append((reason, detail)),
    )
    source_path = str(tmp_path / "unwritable.yaml")
    fake_formatter = FakeYamlFormatter()
    fake_formatter.set_save_result(
        SaveResult(
            succeeded=False,
            failure_reason=SaveFailureReason.WRITE_FAILED,
            detail="Disk full",
        )
    )
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(source_path, make_clean_validation_result(source_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((source_path,))
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=native_pickers, validator=validator, yaml_formatter=fake_formatter
        ),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()

    # Act
    controller.on_save_clicked()

    # Assert
    assert controller._buffers[0].is_dirty
    assert shown_failures == [(SaveFailureReason.WRITE_FAILED, "Disk full")]
    assert not any(signal_name == SIGNAL_TASK_FILE_CHANGED for signal_name, _payload in bus.emitted)


# ---- leave/quit dirty-buffer resolution --------------------------------------


def test_confirm_and_prepare_leave_returns_true_immediately_with_no_dirty_buffers(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no dirty buffers, the leave guard returns ``True`` without ever
    showing a dialog."""
    # Arrange
    monkeypatch.setattr(
        dialogs,
        "confirm_leave",
        lambda _count: pytest.fail("confirm_leave must not be called with no dirty buffers"),
    )
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )

    # Act
    result = controller.confirm_and_prepare_leave()

    # Assert
    assert result is True


def test_confirm_and_prepare_quit_discard_all_reverts_edits(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing Discard All on the quit-confirmation dialog reloads every
    dirty buffer from disk, discarding its in-memory edits."""
    # Arrange
    monkeypatch.setattr(dialogs, "confirm_quit", lambda _count: "discard_all")
    source_path = tmp_path / "discardable.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Old?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()

    # Act
    result = controller.confirm_and_prepare_quit()

    # Assert
    assert result is True
    assert controller._buffers[0].is_dirty is False
    assert len(controller._buffers[0].document["tasks"]) == 1


def test_confirm_and_prepare_leave_save_all_holds_when_a_hard_error_remains(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing Save All saves every saveable dirty buffer but returns
    ``False`` (holding the leave) while a hard-error buffer stays dirty."""
    # Arrange
    monkeypatch.setattr(dialogs, "confirm_leave", lambda _count: "save_all")
    saveable_path = tmp_path / "saveable.yaml"
    saveable_path.write_text("tasks:\n  - task_id: s1\n    question: Q?\n", encoding="utf-8")
    broken_path = tmp_path / "broken.yaml"
    broken_path.write_text("tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(saveable_path), make_clean_validation_result(str(saveable_path))
    )
    issue = ValidationIssue(
        level=ValidationLevel.FIELD,
        severity=ValidationSeverity.ERROR,
        rule="empty_question",
        message="question is empty.",
        task_index=0,
        field_name="question",
    )
    broken_result = FileValidationResult(
        source_path=str(broken_path),
        severity=ValidationSeverity.ERROR,
        save_enabled=False,
        task_results=(
            TaskValidationResult(
                task_index=0, task_id="b1", severity=ValidationSeverity.ERROR, issues=(issue,)
            ),
        ),
    )
    validator.set_validation_result(str(broken_path), broken_result)
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(saveable_path), str(broken_path)))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()  # dirties the broken buffer
    controller.on_file_row_selected(0)
    controller.on_add_task_clicked()  # dirties the saveable buffer

    # Act
    result = controller.confirm_and_prepare_leave()

    # Assert
    assert result is False
    assert controller._buffers[0].is_dirty is False
    assert controller._buffers[1].is_dirty is True


# ---- close: Save & Close ------------------------------------------------------


def test_close_file_clicked_save_and_close_succeeds(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Choosing Save & Close on the close-confirmation dialog saves the file
    then closes it."""
    # Arrange
    monkeypatch.setattr(dialogs, "confirm_close", lambda _name: "save_and_close")
    source_path = tmp_path / "closeable.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()

    # Act
    controller.on_close_file_clicked(0)

    # Assert
    assert controller._buffers == []
    saved_document = make_yaml_formatter().load_document(str(source_path))
    assert len(saved_document["tasks"]) == _THREE_BUFFERS - 1


def test_close_file_clicked_save_and_close_keeps_the_file_open_on_save_failure(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Save & Close's save fails, the file stays open and dirty rather
    than being closed out from under a failed write."""
    # Arrange
    monkeypatch.setattr(dialogs, "confirm_close", lambda _name: "save_and_close")
    monkeypatch.setattr(dialogs, "show_save_failure", lambda *, reason, detail: None)
    source_path = str(tmp_path / "unwritable.yaml")
    fake_formatter = FakeYamlFormatter()
    fake_formatter.set_save_result(SaveResult(succeeded=False))
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(source_path, make_clean_validation_result(source_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((source_path,))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=native_pickers, validator=validator, yaml_formatter=fake_formatter
        ),
    )
    controller.on_open_file_clicked()
    controller.on_add_task_clicked()

    # Act
    controller.on_close_file_clicked(0)

    # Assert
    assert len(controller._buffers) == 1
    assert controller._buffers[0].is_dirty


# ---- _close_buffer / reindex edge cases --------------------------------------


def test_close_buffer_tolerates_an_already_cancelled_watch_subscription(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Closing a buffer whose watch subscription was already removed (e.g. a
    prior cancellation) does not raise."""
    # Arrange
    source_path = tmp_path / "watched.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._watch_subscriptions.pop(str(source_path))

    # Act
    controller.on_close_file_clicked(0)

    # Assert
    assert controller._buffers == []


def test_closing_the_last_buffer_clears_the_active_selection(qtbot: QtBot, tmp_path: Path) -> None:
    """Closing the only open buffer clears both active-selection indices."""
    # Arrange
    source_path = tmp_path / "only.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()

    # Act
    controller.on_close_file_clicked(0)

    # Assert
    assert controller._active_buffer_index is None
    assert controller._active_task_index is None


def test_closing_a_buffer_after_the_active_one_leaves_the_active_index_unchanged(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Closing a later buffer while an earlier one is active leaves the
    active buffer index untouched (neither the equal nor the decrement
    branch applies)."""
    # Arrange
    paths = [tmp_path / name for name in ("a.yaml", "b.yaml", "c.yaml")]
    for index, path in enumerate(paths):
        path.write_text(f"tasks:\n  - task_id: t{index}\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    for path in paths:
        validator.set_validation_result(str(path), make_clean_validation_result(str(path)))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result(tuple(str(path) for path in paths))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller.on_file_row_selected(0)
    assert controller._active_buffer_index == 0

    # Act
    controller.on_close_file_clicked(2)

    # Assert
    assert controller._active_buffer_index == 0


def test_reindex_after_close_is_a_noop_when_active_index_is_already_none(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """The reindex helper is a no-op when the active-buffer index is already
    ``None`` at close time (defensive branch)."""
    # Arrange
    path_a = tmp_path / "a.yaml"
    path_a.write_text("tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(str(path_a), make_clean_validation_result(str(path_a)))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(path_a),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._active_buffer_index = None

    # Act
    controller.on_close_file_clicked(0)

    # Assert
    assert controller._buffers == []
    assert controller._active_buffer_index is None


# ---- commit-pending-field-edit guards ----------------------------------------


def test_validation_debounce_firing_with_no_pending_edit_only_revalidates(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Firing the validation-debounce timer with no staged edit still
    revalidates the active buffer and does not raise."""
    # Arrange
    source_path = tmp_path / "clean.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()

    # Act
    controller._on_validation_debounce_fired()

    # Assert
    assert controller._pending_field_edit is None
    assert controller._buffers[0].validation is not None


def test_commit_pending_field_edit_ignores_a_stale_out_of_range_reference(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A staged field edit referencing a buffer/task index that no longer
    exists (e.g. the buffer was closed first) is silently dropped rather
    than raising."""
    # Arrange
    source_path = tmp_path / "clean.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller.stage_field_edit(
        buffer_index=0, task_index=99, field_name="question", draft_text="Unreachable"
    )

    # Act
    controller._on_validation_debounce_fired()

    # Assert
    assert controller._buffers[0].document["tasks"][0]["question"] == "Q?"


# ---- _on_run_started type guard; unbound-view push guards --------------------


def test_run_started_ignores_a_mismatched_payload_type(qtbot: QtBot) -> None:
    """The ``_run_started`` handler ignores a payload that is not a
    ``RunStartedEvent`` (defensive type guard)."""
    # Arrange
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )

    # Act
    bus.emit(
        SIGNAL_RUN_STARTED, WorkspaceChangedEvent(workspace="benchmark", previous_workspace=None)
    )

    # Assert
    assert controller._buffers == []


def test_unbound_controller_pushes_are_inert_with_no_view(tmp_path: Path) -> None:
    """A controller that was never ``bind()``-ed to a view (no ``QApplication``
    involvement needed) safely no-ops every view-push call -- covers the
    ``self._view is not None`` guard's ``False`` branch."""
    # Arrange
    source_path = tmp_path / "unbound.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller = TaskEditorController(
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
        event_bus=FakeEventBus(),
    )

    # Act -- no bind() call: self._view stays None throughout
    controller.load_initial_state()
    controller.on_open_file_clicked()

    # Assert
    assert controller._view is None
    assert controller._buffers[0].source_path == str(source_path)
