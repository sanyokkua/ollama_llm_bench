"""``TaskEditorController`` -- EventBus subscriptions, the open-buffer collection, and
the file/task lifecycle (STORY-068). Depends only on ``TaskEditorGateway`` plus
``EventBus``, ``TaskFileLoader``, ``TaskFileValidator``, ``YamlFormatter``,
``FileChangeWatcher``, ``NativePickers``, and ``FileSystemActions`` -- never a raw
backend Store/Service Protocol (D-R-06).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from ollama_llm_bench.adapters.native_pickers import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_SETTINGS_CHANGED,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_WORKSPACE_CHANGED,
    EventBus,
    RunStartedEvent,
)
from ollama_llm_bench.ui.task_editor._internal.buffer import (
    TaskBuffer,
    add_task,
    commit_field_edit,
    duplicate_task,
    load_buffer,
    move_task,
    remove_tasks,
    task_count,
)
from ollama_llm_bench.ui.task_editor._internal.view_model_select import (
    select_task_editor_view_model,
)
from ollama_llm_bench.ui.task_editor.models import TaskEditorCollaborators

if TYPE_CHECKING:
    # The view import is only for the apply_view_model()/set_recent_files() calls
    # below -- view.py imports this module for TaskEditorController's constructor
    # parameter, so a real module-level import here would be a runtime import
    # cycle (mirrors ui.resume_benchmark._internal.controller's identical
    # TYPE_CHECKING import).
    from ollama_llm_bench.ui.task_editor._internal.view import TaskEditorView
    from ollama_llm_bench.ui.task_editor.protocols import FileWatchSubscription

__all__: list[str] = ["TaskEditorController"]

logger = structlog.get_logger(__name__)

_YAML_SUFFIXES = frozenset({".yaml", ".yml"})
_RECENT_FILES_MAX = 10
_SEED_YAML_TEXT = (
    "schema_version: 1\n"
    "tasks:\n"
    '  - task_id: ""\n'
    "    difficulty: medium\n"
    '    question: ""\n'
    '    golden_answer: ""\n'
    '    pass_criteria: ""\n'
    '    fail_criteria: ""\n'
    "    required_terms:\n"
    "      exact: []\n"
    "      semantic: []\n"
    "      forbidden: []\n"
)


@dataclass
class _PendingFieldEdit:
    """One uncommitted field draft, staged for commit on the next workspace switch
    (STORY-068-AC-6, EC-WS-4)."""

    buffer_index: int
    task_index: int
    field_name: str
    draft_text: str


class TaskEditorController:
    """Owns the Task Editor workspace's open buffers, subscribes, derives, applies."""

    def __init__(self, *, collaborators: TaskEditorCollaborators, event_bus: EventBus) -> None:
        self._gateway = collaborators.gateway
        self._event_bus = event_bus
        self._task_file_loader = collaborators.task_file_loader
        self._task_file_validator = collaborators.task_file_validator
        self._yaml_formatter = collaborators.yaml_formatter
        self._file_change_watcher = collaborators.file_change_watcher
        self._native_pickers = collaborators.native_pickers
        self._file_system_actions = collaborators.file_system_actions
        self._buffers: list[TaskBuffer] = []
        self._watch_subscriptions: dict[str, FileWatchSubscription] = {}
        self._active_buffer_index: int | None = None
        self._active_task_index: int | None = None
        self._recent_files: list[str] = []
        self._preview_shown = False
        self._pending_field_edit: _PendingFieldEdit | None = None
        self._view: TaskEditorView | None = None
        logger.debug("task_editor_controller_constructed")

    def bind(self, view: "TaskEditorView") -> None:
        """Subscribe to the Event Bus, owner-bound to ``view``'s lifetime."""
        self._view = view
        bus = self._event_bus
        bus.subscribe(SIGNAL_APP_SETTINGS_CHANGED, self._on_app_settings_changed, owner=view)
        bus.subscribe(SIGNAL_RUN_STARTED, self._on_run_started, owner=view)
        bus.subscribe(SIGNAL_RUN_FINISHED, self._on_run_terminal, owner=view)
        bus.subscribe(SIGNAL_RUN_STOPPED, self._on_run_terminal, owner=view)
        bus.subscribe(SIGNAL_RUN_FAILED, self._on_run_terminal, owner=view)
        bus.subscribe(SIGNAL_RUN_RENAMED, self._on_run_renamed, owner=view)
        bus.subscribe(SIGNAL_WORKSPACE_CHANGED, self._on_workspace_changed, owner=view)

    def load_initial_state(self) -> None:
        """Push the workspace's initial (Empty) render state."""
        self._push_view_model()
        self._push_recent_files()

    # ---- open / create -----------------------------------------------------

    def on_open_file_clicked(self) -> None:
        logger.debug("task_editor_open_file_clicked")
        paths = self._native_pickers.open_file(
            FilePickerOptions(
                title="Open Task File", filters=("*.yaml", "*.yml"), allow_multiple=True
            )
        )
        for path in paths:
            self._open_path(path)

    def on_open_folder_clicked(self) -> None:
        logger.debug("task_editor_open_folder_clicked")
        folder = self._native_pickers.open_folder(FolderPickerOptions(title="Open Task Folder"))
        if folder is None:
            return
        for path in _top_level_yaml_files(folder):
            self._open_path(path)

    def on_new_file_clicked(self) -> None:
        logger.debug("task_editor_new_file_clicked")
        path = self._native_pickers.save_file(
            SavePickerOptions(
                title="New Task File", suggested_name="tasks.yaml", filters=("*.yaml",)
            )
        )
        if path is None:
            return
        self._file_system_actions.write_text_file(path=path, content=_SEED_YAML_TEXT)
        self._open_path(path)

    def on_recent_file_clicked(self, path: str) -> None:
        logger.debug("task_editor_recent_file_clicked", path=path)
        self._open_path(path)

    def on_files_dropped(self, paths: tuple[str, ...]) -> None:
        logger.debug("task_editor_files_dropped", path_count=len(paths))
        for path in paths:
            candidate = Path(path)
            if candidate.is_dir():
                for nested_path in _top_level_yaml_files(str(candidate)):
                    self._open_path(nested_path)
            elif candidate.suffix.lower() in _YAML_SUFFIXES:
                self._open_path(str(candidate))

    def _open_path(self, path: str) -> None:
        existing_index = self._find_buffer_index(path)
        if existing_index is not None:
            self._select_file(existing_index)
            return
        buffer = load_buffer(source_path=path, yaml_formatter=self._yaml_formatter)
        buffer.validation = self._task_file_validator.validate(path)
        buffer.is_in_use_by_run = path in self._gateway.active_run_task_paths()
        self._add_buffer(buffer)
        self._watch_file(path)

    def _add_buffer(self, buffer: TaskBuffer) -> None:
        self._buffers.append(buffer)
        self._active_buffer_index = len(self._buffers) - 1
        self._active_task_index = 0 if task_count(buffer) > 0 else None
        self._touch_recent_file(buffer.source_path)
        logger.debug("task_editor_buffer_opened", path=buffer.source_path)
        self._push_view_model()

    def _find_buffer_index(self, path: str) -> int | None:
        for index, buffer in enumerate(self._buffers):
            if buffer.source_path == path:
                return index
        return None

    def _touch_recent_file(self, path: str) -> None:
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        del self._recent_files[_RECENT_FILES_MAX:]
        self._push_recent_files()

    def _watch_file(self, path: str) -> None:
        subscription = self._file_change_watcher.watch(path, self._on_file_changed_on_disk)
        self._watch_subscriptions[path] = subscription

    def _on_file_changed_on_disk(self, path: str) -> None:
        index = self._find_buffer_index(path)
        if index is None:
            return
        logger.debug("task_editor_file_changed_on_disk", path=path)
        self._buffers[index].is_external_changed = True
        self._push_view_model()

    # ---- selection -----------------------------------------------------

    def on_file_row_selected(self, index: int) -> None:
        self._select_file(index)

    def _select_file(self, index: int) -> None:
        if not (0 <= index < len(self._buffers)):
            return
        self._active_buffer_index = index
        buffer = self._buffers[index]
        self._active_task_index = 0 if task_count(buffer) > 0 else None
        logger.debug("task_editor_file_selected", path=buffer.source_path)
        self._push_view_model()

    def on_task_row_selected(self, index: int) -> None:
        buffer = self._active_buffer()
        if buffer is None or not (0 <= index < task_count(buffer)):
            return
        self._active_task_index = index
        self._push_view_model()

    # ---- tasks -----------------------------------------------------

    def on_add_task_clicked(self) -> None:
        buffer = self._active_buffer()
        if buffer is None:
            return
        new_index = add_task(buffer)
        self._active_task_index = new_index
        logger.debug("task_editor_task_added", path=buffer.source_path, task_index=new_index)
        self._push_view_model()

    def on_duplicate_task_clicked(self, index: int) -> None:
        buffer = self._active_buffer()
        if buffer is None or not (0 <= index < task_count(buffer)):
            return
        new_index = duplicate_task(buffer, index)
        self._active_task_index = new_index
        logger.debug(
            "task_editor_task_duplicated",
            path=buffer.source_path,
            source_index=index,
            new_index=new_index,
        )
        self._push_view_model()

    def on_remove_tasks_clicked(self, indices: tuple[int, ...]) -> None:
        buffer = self._active_buffer()
        if buffer is None or not indices:
            return
        remove_tasks(buffer, indices)
        remaining = task_count(buffer)
        self._active_task_index = 0 if remaining > 0 else None
        logger.debug("task_editor_tasks_removed", path=buffer.source_path, count=len(indices))
        self._push_view_model()

    def on_move_task_clicked(self, index: int, *, offset: int) -> None:
        buffer = self._active_buffer()
        if buffer is None:
            return
        new_index = move_task(buffer, index, offset=offset)
        self._active_task_index = new_index
        logger.debug(
            "task_editor_task_moved", path=buffer.source_path, from_index=index, to_index=new_index
        )
        self._push_view_model()

    # ---- files-pane actions -----------------------------------------------------

    def on_reload_clicked(self) -> None:
        buffer = self._active_buffer()
        if buffer is None or buffer.is_dirty:
            return
        self._reload_buffer(buffer)

    def on_reload_from_disk_context_menu(self, index: int) -> None:
        if not (0 <= index < len(self._buffers)):
            return
        buffer = self._buffers[index]
        if buffer.is_dirty:
            return
        self._reload_buffer(buffer)

    def _reload_buffer(self, buffer: TaskBuffer) -> None:
        logger.debug("task_editor_reload_from_disk", path=buffer.source_path)
        buffer.document = self._yaml_formatter.load_document(buffer.source_path)
        buffer.validation = self._task_file_validator.validate(buffer.source_path)
        buffer.is_external_changed = False
        buffer.is_dirty = False
        index = self._find_buffer_index(buffer.source_path)
        if index is not None and index == self._active_buffer_index:
            self._active_task_index = 0 if task_count(buffer) > 0 else None
        self._push_view_model()

    def on_close_file_clicked(self, index: int) -> None:
        if not (0 <= index < len(self._buffers)) or self._buffers[index].is_dirty:
            return
        self._close_buffer(index)

    def on_close_others_clicked(self, index: int) -> None:
        for other_index in reversed(range(len(self._buffers))):
            if other_index == index or self._buffers[other_index].is_dirty:
                continue
            self._close_buffer(other_index)

    def _close_buffer(self, index: int) -> None:
        buffer = self._buffers.pop(index)
        subscription = self._watch_subscriptions.pop(buffer.source_path, None)
        if subscription is not None:
            subscription.cancel()
        logger.debug("task_editor_buffer_closed", path=buffer.source_path)
        self._reindex_active_selection_after_close(closed_index=index)
        self._push_view_model()

    def _reindex_active_selection_after_close(self, *, closed_index: int) -> None:
        if not self._buffers:
            self._active_buffer_index = None
            self._active_task_index = None
            return
        if self._active_buffer_index is None:
            return
        if self._active_buffer_index == closed_index:
            self._active_buffer_index = min(closed_index, len(self._buffers) - 1)
            self._active_task_index = (
                0 if task_count(self._buffers[self._active_buffer_index]) > 0 else None
            )
        elif self._active_buffer_index > closed_index:
            self._active_buffer_index -= 1

    def on_reveal_in_file_manager_clicked(self, index: int) -> None:
        if not (0 <= index < len(self._buffers)):
            return
        self._file_system_actions.open_in_file_manager(self._buffers[index].source_path)

    # ---- field-edit commit hook (STORY-068-AC-6, EC-WS-4) -----------------------------

    def stage_field_edit(
        self, *, buffer_index: int, task_index: int, field_name: str, draft_text: str
    ) -> None:
        """Record an in-progress field edit so a later workspace switch commits it.

        There is no real Field-editor pane yet (STORY-069's scope); this hook lets a
        future field widget report its uncommitted draft text so
        ``_on_workspace_changed`` commits it before the switch (STORY-068-AC-6).

        Args:
            buffer_index: The buffer holding the field being edited.
            task_index: The task within that buffer holding the field.
            field_name: The task field's YAML key.
            draft_text: The uncommitted text currently held by the field control.
        """
        self._pending_field_edit = _PendingFieldEdit(
            buffer_index=buffer_index,
            task_index=task_index,
            field_name=field_name,
            draft_text=draft_text,
        )

    def _commit_pending_field_edit(self) -> None:
        pending = self._pending_field_edit
        self._pending_field_edit = None
        if pending is None or not (0 <= pending.buffer_index < len(self._buffers)):
            return
        buffer = self._buffers[pending.buffer_index]
        if not (0 <= pending.task_index < task_count(buffer)):
            return
        commit_field_edit(
            buffer,
            task_index=pending.task_index,
            field_name=pending.field_name,
            draft_text=pending.draft_text,
        )
        logger.debug(
            "task_editor_field_edit_committed",
            path=buffer.source_path,
            task_index=pending.task_index,
            field_name=pending.field_name,
        )

    # ---- Event Bus handlers -----------------------------------------------------

    def _on_app_settings_changed(self, _payload: object) -> None:
        logger.debug("task_editor_event_received", signal_name="app_settings_changed")

    def _on_run_started(self, payload: object) -> None:
        if not isinstance(payload, RunStartedEvent):
            return
        logger.debug("task_editor_event_received", signal_name="run_started", run_id=payload.run_id)
        task_paths = set(self._gateway.active_run_task_paths())
        for buffer in self._buffers:
            buffer.is_in_use_by_run = buffer.source_path in task_paths
        self._push_view_model()

    def _on_run_terminal(self, _payload: object) -> None:
        logger.debug("task_editor_event_received", signal_name="run_terminal")
        for buffer in self._buffers:
            buffer.is_in_use_by_run = False
        self._push_view_model()

    def _on_run_renamed(self, _payload: object) -> None:
        logger.debug("task_editor_event_received", signal_name="run_renamed")

    def _on_workspace_changed(self, _payload: object) -> None:
        logger.debug("task_editor_event_received", signal_name="workspace_changed")
        self._commit_pending_field_edit()
        self._push_view_model()

    # ---- view-model push -----------------------------------------------------

    def _active_buffer(self) -> TaskBuffer | None:
        if self._active_buffer_index is None or not (
            0 <= self._active_buffer_index < len(self._buffers)
        ):
            return None
        return self._buffers[self._active_buffer_index]

    def _push_view_model(self) -> None:
        view_model = select_task_editor_view_model(
            buffers=self._buffers,
            active_buffer_index=self._active_buffer_index,
            active_task_index=self._active_task_index,
            preview_shown=self._preview_shown,
        )
        if self._view is not None:
            self._view.apply_view_model(view_model)

    def _push_recent_files(self) -> None:
        if self._view is not None:
            self._view.set_recent_files(tuple(self._recent_files))


def _top_level_yaml_files(folder: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(path)
            for path in Path(folder).iterdir()
            if path.is_file() and path.suffix.lower() in _YAML_SUFFIXES
        )
    )
