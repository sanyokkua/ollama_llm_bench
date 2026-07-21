"""Colocated unit tests for ``TaskEditorController``'s remaining no-active-buffer
guard clauses and a few reload/reopen branches not yet exercised by
``test_controller.py``/``test_controller_actions.py``/``test_controller_field_editing.py``/
``test_controller_save_and_dialog_branches.py`` -- required by the story's
Definition of done branch-coverage gate (>=85% on controllers), not tied to a
single named acceptance criterion.
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.task_files.testing import FakeTaskFileLoader
from ollama_llm_bench.backend.yaml_formatter import make_yaml_formatter
from ollama_llm_bench.ui.task_editor._internal.controller import TaskEditorController
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

_TWO_BUFFERS = 2


def _collaborators(
    *, native_pickers: FakeNativePickers, validator: ScratchAwareTaskFileValidator
) -> TaskEditorCollaborators:
    return TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        clipboard=FakeClipboard(),
        file_system_actions=FakeFileSystemActions(),
    )


def test_task_and_field_actions_are_noops_with_no_buffer_open(qtbot: QtBot) -> None:
    """Every task/field-edit action that requires an active buffer is a no-op
    when no file is open (the ``buffer is None`` guard clause each one
    shares)."""
    # Arrange
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )

    # Act
    controller.on_file_row_selected(99)
    controller.on_add_task_clicked()
    controller.on_duplicate_task_clicked(0)
    controller.on_move_task_clicked(0, offset=1)
    controller.on_field_text_changed("question", "unreachable")
    controller.on_field_focus_lost("question", "unreachable")
    controller.on_field_boolean_changed("cosine_enabled", value=True)
    controller.on_field_enum_changed("difficulty", "hard")
    controller.on_field_chip_values_changed("required_terms.exact", ("x",))
    controller.on_reload_clicked()

    # Assert
    assert controller._buffers == []
    assert controller._pending_field_edit is None


def test_file_change_watcher_trigger_after_the_buffer_is_gone_is_ignored(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A change notification arriving for a path whose buffer has since
    disappeared from the open-buffer list is silently ignored (a stale
    watch callback racing a close)."""
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
    controller._buffers.clear()  # simulate the buffer having disappeared already

    # Act -- the watch callback is still registered and fires anyway
    watcher.trigger_change(str(source_path))

    # Assert
    assert controller._buffers == []


def test_reopening_a_previously_recent_path_moves_it_back_to_the_front(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Closing then reopening a path re-touches its recent-files entry,
    exercising the "already present, move to front" dedup branch rather than
    a fresh insert."""
    # Arrange
    path_a = str(tmp_path / "a.yaml")
    path_b = str(tmp_path / "b.yaml")
    (tmp_path / "a.yaml").write_text(
        "tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8"
    )
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(path_a, make_clean_validation_result(path_a))
    validator.set_validation_result(path_b, make_clean_validation_result(path_b))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((path_a, path_b))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    assert controller._recent_files[0] == path_b
    controller.on_close_file_clicked(0)  # close a.yaml (clean, no confirmation)

    # Act -- reopen a.yaml, already present in the recent list
    native_pickers.set_open_file_result((path_a,))
    controller.on_open_file_clicked()

    # Assert
    assert controller._recent_files[0] == path_a
    assert controller._recent_files.count(path_a) == 1


def test_reload_from_disk_context_menu_reloads_a_clean_non_active_buffer(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """The context-menu Reload from Disk action, on a clean buffer that is
    not the active file, reloads it from disk with no confirmation and
    leaves the active-file selection untouched."""
    # Arrange
    active_path = tmp_path / "active.yaml"
    active_path.write_text("tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8")
    reloadable_path = tmp_path / "reloadable.yaml"
    reloadable_path.write_text("tasks:\n  - task_id: r1\n    question: Old?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(
        str(active_path), make_clean_validation_result(str(active_path))
    )
    validator.set_validation_result(
        str(reloadable_path), make_clean_validation_result(str(reloadable_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(reloadable_path), str(active_path)))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    assert controller._active_buffer_index == 1  # active.yaml, opened last
    reloadable_path.write_text(
        "tasks:\n  - task_id: r1\n    question: Changed on disk?\n", encoding="utf-8"
    )

    # Act
    controller.on_reload_from_disk_context_menu(0)

    # Assert
    assert controller._buffers[0].document["tasks"][0]["question"] == "Changed on disk?"
    assert controller._active_buffer_index == 1


def test_closing_one_of_two_buffers_when_active_index_was_already_none(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Closing a buffer while ``_active_buffer_index`` is already ``None``
    (and at least one buffer remains afterward) is a no-op for the active
    selection (the reindex helper's defensive early-return branch)."""
    # Arrange
    path_a = tmp_path / "a.yaml"
    path_a.write_text("tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8")
    path_b = tmp_path / "b.yaml"
    path_b.write_text("tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8")
    validator = ScratchAwareTaskFileValidator()
    validator.set_validation_result(str(path_a), make_clean_validation_result(str(path_a)))
    validator.set_validation_result(str(path_b), make_clean_validation_result(str(path_b)))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(path_a), str(path_b)))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._active_buffer_index = None

    # Act
    controller.on_close_file_clicked(0)

    # Assert
    assert len(controller._buffers) == 1
    assert controller._active_buffer_index is None


def test_preview_related_calls_are_inert_with_no_buffer_open(qtbot: QtBot) -> None:
    """Toggling and refreshing the YAML preview with no active buffer is
    inert (the ``buffer is None`` guards in ``_compute_preview_text``/
    ``_on_preview_timer_fired``)."""
    # Arrange
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )
    controller.on_view_yaml_toggled()
    assert controller._preview_shown is True

    # Act
    controller._on_preview_timer_fired()

    # Assert
    assert controller._view is not None
    assert controller._view._yaml_preview.preview_text() == ""


def test_revalidate_active_buffer_and_push_is_a_noop_with_no_buffer_open(qtbot: QtBot) -> None:
    """Calling the shared revalidate-and-push helper with no active buffer
    skips validation and still pushes the (empty) view model, rather than
    raising."""
    # Arrange
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=ScratchAwareTaskFileValidator()
        ),
    )

    # Act
    controller._revalidate_active_buffer_and_push()

    # Assert
    assert controller._buffers == []


def test_debounce_and_preview_scheduling_are_inert_on_an_unbound_controller(
    tmp_path: Path,
) -> None:
    """A controller never ``bind()``-ed to a view (``self._view`` stays
    ``None``) safely no-ops both the validation-debounce and the
    preview-refresh scheduling calls, even with an active buffer and the
    preview flag set."""
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
    controller.load_initial_state()
    controller.on_open_file_clicked()
    controller.on_view_yaml_toggled()

    # Act -- no bind() call: self._view is None throughout
    controller.on_field_text_changed("question", "unreachable")

    # Assert
    assert controller._view is None
    assert controller._validation_timer is None
    assert controller._preview_timer is None


def test_field_text_changed_twice_reuses_the_existing_validation_and_preview_timers(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """A second keystroke while the debounce/preview timers are already
    running restarts them rather than constructing new ``QTimer``
    instances."""
    # Arrange
    source_path = tmp_path / "editable.yaml"
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
    controller.on_view_yaml_toggled()
    controller.on_field_text_changed("question", "First keystroke")
    first_validation_timer = controller._validation_timer
    first_preview_timer = controller._preview_timer

    # Act
    controller.on_field_text_changed("question", "Second keystroke")

    # Assert
    assert controller._validation_timer is first_validation_timer
    assert controller._preview_timer is first_preview_timer
