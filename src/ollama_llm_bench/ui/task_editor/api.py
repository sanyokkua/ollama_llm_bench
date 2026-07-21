"""Public factory for ``ui/task_editor/`` (STORY-068, STORY-069).

Source of truth: ``docs/v3_specification/09_Task_Editor/implementation_structure.md``
§2 (public API). ``compose.py`` wiring is out of scope for this story (Phase 11 owns
it) -- this factory only declares the collaborators a later composition-root story
wires.
"""

from functools import partial

import icontract
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.task_editor._internal.controller import TaskEditorController
from ollama_llm_bench.ui.task_editor._internal.view import TaskEditorView
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators

__all__: list[str] = ["make_task_editor_workspace"]


@icontract.require(lambda bus: bus is not None, "the event bus is a required collaborator")
@icontract.require(
    lambda collaborators: all(
        c is not None
        for c in (
            collaborators.gateway,
            collaborators.task_file_loader,
            collaborators.task_file_validator,
            collaborators.yaml_formatter,
            collaborators.file_change_watcher,
            collaborators.native_pickers,
            collaborators.file_system_actions,
            collaborators.clipboard,
        )
    ),
    "every collaborator is required, wired by a later composition-root story",
)
@icontract.ensure(lambda result: isinstance(result, QWidget))
def make_task_editor_workspace(*, bus: EventBus, collaborators: TaskEditorCollaborators) -> QWidget:
    """Construct the mountable Task Editor workspace shell.

    Args:
        bus: The application Event Bus this workspace subscribes to and emits on.
        collaborators: The gateway and OS-adapter/file-service helpers this
            workspace's controller depends on (D-R-06).

    Returns:
        A QWidget ready to mount into the Main Window central region, opened
        in its Empty state (no file loaded yet).
    """
    controller = TaskEditorController(collaborators=collaborators, event_bus=bus)
    view = TaskEditorView()
    view.open_file_clicked.connect(controller.on_open_file_clicked)
    view.open_folder_clicked.connect(controller.on_open_folder_clicked)
    view.new_file_clicked.connect(controller.on_new_file_clicked)
    view.reload_clicked.connect(controller.on_reload_clicked)
    view.recent_file_clicked.connect(controller.on_recent_file_clicked)
    view.files_dropped.connect(controller.on_files_dropped)
    view.file_row_selected.connect(controller.on_file_row_selected)
    view.close_requested.connect(controller.on_close_file_clicked)
    view.close_others_requested.connect(controller.on_close_others_clicked)
    view.reveal_requested.connect(controller.on_reveal_in_file_manager_clicked)
    view.reload_from_disk_requested.connect(controller.on_reload_from_disk_context_menu)
    view.task_row_selected.connect(controller.on_task_row_selected)
    view.add_task_clicked.connect(controller.on_add_task_clicked)
    view.duplicate_task_clicked.connect(controller.on_duplicate_task_clicked)
    view.remove_tasks_clicked.connect(controller.on_remove_tasks_clicked)
    view.move_up_clicked.connect(partial(controller.on_move_task_clicked, offset=-1))
    view.move_down_clicked.connect(partial(controller.on_move_task_clicked, offset=1))
    view.save_clicked.connect(controller.on_save_clicked)
    view.save_all_clicked.connect(controller.on_save_all_clicked)
    view.view_yaml_toggled.connect(controller.on_view_yaml_toggled)
    view.copy_yaml_clicked.connect(controller.on_copy_yaml_clicked)
    view.field_text_changed.connect(controller.on_field_text_changed)
    view.field_focus_lost.connect(controller.on_field_focus_lost)
    view.field_boolean_changed.connect(controller.on_field_boolean_changed)
    view.field_enum_changed.connect(controller.on_field_enum_changed)
    view.field_chip_values_changed.connect(controller.on_field_chip_values_changed)
    controller.bind(view)
    controller.load_initial_state()
    return view
