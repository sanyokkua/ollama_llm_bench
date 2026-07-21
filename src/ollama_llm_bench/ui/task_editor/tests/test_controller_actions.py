"""Colocated unit tests for ``TaskEditorController``'s remaining file/task
lifecycle actions -- not tied to one single named acceptance criterion, but
required by the story's Definition of done branch-coverage gate (>=85% on
controllers) and by ``09_Task_Editor/state_machine.md`` §3's per-file Loaded/
Dirty/ExternalChanged states this shell owns: Open Folder, New File, the
recent-files reopen-vs-select path, drag-drop, file/task selection, Remove/
Move Task, Reload (from toolbar and from the context menu), Close/Close
Others, Reveal in File Manager, and the app-settings/run-renamed event
handlers.
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.native_pickers.testing import FakeNativePickers
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_SETTINGS_CHANGED,
    SIGNAL_RUN_RENAMED,
    AppSettingsChangedEvent,
    RunRenamedEvent,
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

_MOVED_ORDER = ("t2", "t1")
_TWO_BUFFERS_OR_TASKS = 2


def _collaborators(
    *,
    native_pickers: FakeNativePickers,
    validator: FakeTaskFileValidator,
    file_system_actions: FakeFileSystemActions | None = None,
) -> TaskEditorCollaborators:
    return TaskEditorCollaborators(
        gateway=FakeTaskEditorGateway(),
        task_file_loader=FakeTaskFileLoader(),
        task_file_validator=validator,
        yaml_formatter=make_yaml_formatter(),
        file_change_watcher=FakeFileChangeWatcher(),
        native_pickers=native_pickers,
        file_system_actions=file_system_actions or FakeFileSystemActions(),
    )


def test_open_folder_opens_every_top_level_yaml_file_and_ignores_other_extensions(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Open Folder opens every top-level ``.yaml``/``.yml`` file, in sorted
    order, and ignores a non-YAML file in the same folder."""
    # Arrange
    (tmp_path / "a.yaml").write_text(
        "tasks:\n  - task_id: a1\n    question: Qa?\n", encoding="utf-8"
    )
    (tmp_path / "b.yml").write_text(
        "tasks:\n  - task_id: b1\n    question: Qb?\n", encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("not a task file", encoding="utf-8")
    validator = FakeTaskFileValidator()
    validator.set_validation_result(
        str(tmp_path / "a.yaml"), make_clean_validation_result(str(tmp_path / "a.yaml"))
    )
    validator.set_validation_result(
        str(tmp_path / "b.yml"), make_clean_validation_result(str(tmp_path / "b.yml"))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_folder_result(str(tmp_path))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )

    # Act
    controller.on_open_folder_clicked()

    # Assert
    assert {buffer.source_path for buffer in controller._buffers} == {
        str(tmp_path / "a.yaml"),
        str(tmp_path / "b.yml"),
    }


def test_open_folder_is_a_noop_when_the_user_cancels(qtbot: QtBot) -> None:
    """Open Folder with no folder chosen (native picker returns ``None``) opens
    nothing."""
    # Arrange
    native_pickers = FakeNativePickers()
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=native_pickers, validator=FakeTaskFileValidator()
        ),
    )

    # Act
    controller.on_open_folder_clicked()

    # Assert
    assert controller._buffers == []


def test_new_file_writes_seed_yaml_and_opens_it(qtbot: QtBot, tmp_path: Path) -> None:
    """New File writes the seed-scaffold YAML via ``FileSystemActions.write_text_file``
    and then opens the freshly written file as a buffer."""
    # Arrange
    target_path = str(tmp_path / "tasks.yaml")
    validator = FakeTaskFileValidator()
    validator.set_validation_result(target_path, make_clean_validation_result(target_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_save_result(target_path)
    file_system_actions = FakeFileSystemActions()
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=native_pickers,
            validator=validator,
            file_system_actions=file_system_actions,
        ),
    )

    # Act
    controller.on_new_file_clicked()

    # Assert
    assert target_path in file_system_actions.written_text
    assert controller._buffers[0].source_path == target_path


def test_new_file_is_a_noop_when_the_user_cancels(qtbot: QtBot) -> None:
    """New File with no destination chosen writes nothing and opens nothing."""
    # Arrange
    file_system_actions = FakeFileSystemActions()
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(),
            validator=FakeTaskFileValidator(),
            file_system_actions=file_system_actions,
        ),
    )

    # Act
    controller.on_new_file_clicked()

    # Assert
    assert file_system_actions.written_text == {}
    assert controller._buffers == []


def test_recent_file_clicked_selects_an_already_open_buffer_without_reopening(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Reopening an already-open path (e.g. from the recent-files list) selects
    the existing buffer instead of appending a duplicate."""
    # Arrange
    first_path = str(tmp_path / "first.yaml")
    second_path = str(tmp_path / "second.yaml")
    (tmp_path / "first.yaml").write_text(
        "tasks:\n  - task_id: f1\n    question: Q?\n", encoding="utf-8"
    )
    (tmp_path / "second.yaml").write_text(
        "tasks:\n  - task_id: s1\n    question: Q?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(first_path, make_clean_validation_result(first_path))
    validator.set_validation_result(second_path, make_clean_validation_result(second_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((first_path, second_path))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()

    # Act
    controller.on_recent_file_clicked(first_path)

    # Assert
    assert len(controller._buffers) == _TWO_BUFFERS_OR_TASKS
    assert controller._active_buffer_index == 0


def test_files_dropped_recurses_folders_opens_yaml_and_ignores_other_extensions(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Dropping a folder opens every top-level YAML file inside it; dropping a
    lone YAML file opens it directly; dropping a non-YAML file is ignored."""
    # Arrange
    nested_folder = tmp_path / "nested"
    nested_folder.mkdir()
    nested_yaml = nested_folder / "inside.yaml"
    nested_yaml.write_text("tasks:\n  - task_id: n1\n    question: Q?\n", encoding="utf-8")
    standalone_yaml = tmp_path / "standalone.yaml"
    standalone_yaml.write_text("tasks:\n  - task_id: s1\n    question: Q?\n", encoding="utf-8")
    ignored_file = tmp_path / "ignored.txt"
    ignored_file.write_text("not yaml", encoding="utf-8")
    validator = FakeTaskFileValidator()
    validator.set_validation_result(
        str(nested_yaml), make_clean_validation_result(str(nested_yaml))
    )
    validator.set_validation_result(
        str(standalone_yaml), make_clean_validation_result(str(standalone_yaml))
    )
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=FakeNativePickers(), validator=validator),
    )

    # Act
    controller.on_files_dropped((str(nested_folder), str(standalone_yaml), str(ignored_file)))

    # Assert
    assert {buffer.source_path for buffer in controller._buffers} == {
        str(nested_yaml),
        str(standalone_yaml),
    }


def test_file_row_selected_switches_the_active_file(qtbot: QtBot, tmp_path: Path) -> None:
    """Selecting a Files-pane row switches the active file and resets the
    active task to the newly active file's first task."""
    # Arrange
    path_a = str(tmp_path / "a.yaml")
    path_b = str(tmp_path / "b.yaml")
    (tmp_path / "a.yaml").write_text(
        "tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(path_a, make_clean_validation_result(path_a))
    validator.set_validation_result(path_b, make_clean_validation_result(path_b))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((path_a, path_b))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    assert controller._active_buffer_index == 1

    # Act
    controller.on_file_row_selected(0)

    # Assert
    assert controller._active_buffer_index == 0
    assert controller._active_task_index == 0


def test_task_row_selected_updates_active_task_and_ignores_out_of_range(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Selecting a Tasks-pane row updates the active task index; an
    out-of-range index is a no-op."""
    # Arrange
    source_path = str(tmp_path / "two_tasks.yaml")
    (tmp_path / "two_tasks.yaml").write_text(
        "tasks:\n  - task_id: t1\n    question: Q1?\n  - task_id: t2\n    question: Q2?\n",
        encoding="utf-8",
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(source_path, make_clean_validation_result(source_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((source_path,))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()

    # Act
    controller.on_task_row_selected(1)
    out_of_range_index = controller._active_task_index
    controller.on_task_row_selected(99)

    # Assert
    assert out_of_range_index == 1
    assert controller._active_task_index == 1


def test_remove_tasks_clicked_removes_selected_tasks_and_resets_active_index(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Removing the selected task(s) deletes them and resets the active task
    index; an empty selection is a no-op."""
    # Arrange
    source_path = str(tmp_path / "two_tasks.yaml")
    (tmp_path / "two_tasks.yaml").write_text(
        "tasks:\n  - task_id: t1\n    question: Q1?\n  - task_id: t2\n    question: Q2?\n",
        encoding="utf-8",
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(source_path, make_clean_validation_result(source_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((source_path,))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()

    # Act
    controller.on_remove_tasks_clicked(())
    count_after_empty_selection = len(controller._buffers[0].document["tasks"])
    controller.on_remove_tasks_clicked((0,))

    # Assert
    assert count_after_empty_selection == _TWO_BUFFERS_OR_TASKS
    assert len(controller._buffers[0].document["tasks"]) == 1
    assert controller._active_task_index == 0


def test_move_task_clicked_reorders_the_active_buffers_tasks(qtbot: QtBot, tmp_path: Path) -> None:
    """Moving the first task down swaps it with its neighbour."""
    # Arrange
    source_path = str(tmp_path / "two_tasks.yaml")
    (tmp_path / "two_tasks.yaml").write_text(
        "tasks:\n  - task_id: t1\n    question: Q1?\n  - task_id: t2\n    question: Q2?\n",
        encoding="utf-8",
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(source_path, make_clean_validation_result(source_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((source_path,))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()

    # Act
    controller.on_move_task_clicked(0, offset=1)

    # Assert
    reordered = tuple(task["task_id"] for task in controller._buffers[0].document["tasks"])
    assert reordered == _MOVED_ORDER
    assert controller._active_task_index == 1


def test_reload_clicked_noop_when_dirty_and_reloads_from_disk_when_clean(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Reload is a no-op while the active buffer is dirty; once clean, it
    reloads the buffer's content from disk."""
    # Arrange
    source_path = tmp_path / "reloadable.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Old?\n", encoding="utf-8")
    validator = FakeTaskFileValidator()
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
    assert controller._buffers[0].is_dirty

    # Act -- dirty: no-op
    controller.on_reload_clicked()
    task_count_while_dirty = len(controller._buffers[0].document["tasks"])

    # Arrange -- mark clean and change the on-disk content
    controller._buffers[0].is_dirty = False
    source_path.write_text(
        "tasks:\n  - task_id: t1\n    question: Changed on disk?\n", encoding="utf-8"
    )

    # Act -- clean: reloads
    controller.on_reload_clicked()

    # Assert
    assert task_count_while_dirty == _TWO_BUFFERS_OR_TASKS
    assert len(controller._buffers[0].document["tasks"]) == 1
    assert controller._buffers[0].document["tasks"][0]["question"] == "Changed on disk?"
    assert controller._buffers[0].is_dirty is False


def test_reload_from_disk_context_menu_noop_when_dirty_or_out_of_range(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """The context-menu Reload from Disk action is a no-op for an out-of-range
    index and for a dirty buffer."""
    # Arrange
    source_path = tmp_path / "reloadable.yaml"
    source_path.write_text("tasks:\n  - task_id: t1\n    question: Old?\n", encoding="utf-8")
    validator = FakeTaskFileValidator()
    validator.set_validation_result(
        str(source_path), make_clean_validation_result(str(source_path))
    )
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((str(source_path),))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )

    # Act -- no buffers open yet
    controller.on_reload_from_disk_context_menu(0)
    controller.on_open_file_clicked()
    controller._buffers[0].is_dirty = True

    # Act -- dirty buffer
    controller.on_reload_from_disk_context_menu(0)

    # Assert
    assert controller._buffers[0].is_dirty


def test_close_file_clicked_noop_when_dirty_closes_and_reindexes_when_clean(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Close is a no-op for a dirty buffer; for a clean buffer it closes and
    reindexes the active selection."""
    # Arrange
    path_a = str(tmp_path / "a.yaml")
    path_b = str(tmp_path / "b.yaml")
    (tmp_path / "a.yaml").write_text(
        "tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(path_a, make_clean_validation_result(path_a))
    validator.set_validation_result(path_b, make_clean_validation_result(path_b))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((path_a, path_b))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._buffers[0].is_dirty = True

    # Act -- dirty: no-op
    controller.on_close_file_clicked(0)
    count_while_dirty = len(controller._buffers)

    # Act -- out-of-range index: no-op
    controller.on_close_file_clicked(99)

    # Act -- clean: closes
    controller._buffers[0].is_dirty = False
    controller.on_close_file_clicked(0)

    # Assert
    assert count_while_dirty == _TWO_BUFFERS_OR_TASKS
    assert len(controller._buffers) == 1
    assert controller._buffers[0].source_path == path_b
    assert controller._active_buffer_index == 0


def test_close_others_clicked_skips_dirty_buffers(qtbot: QtBot, tmp_path: Path) -> None:
    """Close Others closes every other clean buffer but skips a dirty one."""
    # Arrange
    path_a = str(tmp_path / "a.yaml")
    path_b = str(tmp_path / "b.yaml")
    path_c = str(tmp_path / "c.yaml")
    (tmp_path / "a.yaml").write_text(
        "tasks:\n  - task_id: a1\n    question: Q?\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "tasks:\n  - task_id: b1\n    question: Q?\n", encoding="utf-8"
    )
    (tmp_path / "c.yaml").write_text(
        "tasks:\n  - task_id: c1\n    question: Q?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(path_a, make_clean_validation_result(path_a))
    validator.set_validation_result(path_b, make_clean_validation_result(path_b))
    validator.set_validation_result(path_c, make_clean_validation_result(path_c))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((path_a, path_b, path_c))
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(native_pickers=native_pickers, validator=validator),
    )
    controller.on_open_file_clicked()
    controller._buffers[1].is_dirty = True

    # Act -- keep index 0, close everything else except the dirty middle one
    controller.on_close_others_clicked(0)

    # Assert
    assert [buffer.source_path for buffer in controller._buffers] == [path_a, path_b]


def test_reveal_in_file_manager_clicked_calls_file_system_actions(
    qtbot: QtBot, tmp_path: Path
) -> None:
    """Reveal in File Manager forwards the buffer's path to
    ``FileSystemActions.open_in_file_manager``; an out-of-range index is a
    no-op."""
    # Arrange
    source_path = str(tmp_path / "revealed.yaml")
    (tmp_path / "revealed.yaml").write_text(
        "tasks:\n  - task_id: t1\n    question: Q?\n", encoding="utf-8"
    )
    validator = FakeTaskFileValidator()
    validator.set_validation_result(source_path, make_clean_validation_result(source_path))
    native_pickers = FakeNativePickers()
    native_pickers.set_open_file_result((source_path,))
    file_system_actions = FakeFileSystemActions()
    controller, _bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=native_pickers,
            validator=validator,
            file_system_actions=file_system_actions,
        ),
    )
    controller.on_open_file_clicked()

    # Act
    controller.on_reveal_in_file_manager_clicked(99)
    controller.on_reveal_in_file_manager_clicked(0)

    # Assert
    assert file_system_actions.revealed_paths == [source_path]


def test_app_settings_changed_and_run_renamed_events_are_logged_no_ops(qtbot: QtBot) -> None:
    """The ``_app_settings_changed``/``_run_renamed`` subscriptions are wired
    (per §7 event-bus integration) but change no workspace state -- both are
    logged-only handlers this story."""
    # Arrange
    controller, bus = make_bound_task_editor_controller(
        qtbot=qtbot,
        collaborators=_collaborators(
            native_pickers=FakeNativePickers(), validator=FakeTaskFileValidator()
        ),
    )

    # Act
    bus.emit(SIGNAL_APP_SETTINGS_CHANGED, AppSettingsChangedEvent(changed_keys=("some.key",)))
    bus.emit(SIGNAL_RUN_RENAMED, RunRenamedEvent(run_id=1, new_name="Renamed"))

    # Assert
    assert controller._buffers == []
