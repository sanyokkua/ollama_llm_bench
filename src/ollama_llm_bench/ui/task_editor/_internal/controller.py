"""``TaskEditorController`` -- EventBus subscriptions, the open-buffer collection, the
file/task lifecycle, the field-edit/validation/preview pipeline, and Save
orchestration (STORY-068, STORY-069). Depends only on ``TaskEditorGateway`` plus
``EventBus``, ``TaskFileLoader``, ``TaskFileValidator``, ``YamlFormatter``,
``FileChangeWatcher``, ``NativePickers``, ``FileSystemActions``, and ``Clipboard`` --
never a raw backend Store/Service Protocol (D-R-06). The controller never
serializes, parses, or validates YAML itself -- it always delegates to the
``YamlFormatter``/``TaskFileValidator`` through ``_internal/buffer.py``'s scratch
seam (D-R-06).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
import structlog

from ollama_llm_bench.adapters.native_pickers import (
    FilePickerOptions,
    FolderPickerOptions,
    SavePickerOptions,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_APP_SETTINGS_CHANGED,
    SIGNAL_GLOBAL_MESSAGE,
    SIGNAL_RUN_FAILED,
    SIGNAL_RUN_FINISHED,
    SIGNAL_RUN_RENAMED,
    SIGNAL_RUN_STARTED,
    SIGNAL_RUN_STOPPED,
    SIGNAL_TASK_FILE_CHANGED,
    SIGNAL_WORKSPACE_CHANGED,
    EventBus,
    GlobalMessageEvent,
    RunStartedEvent,
    TaskFileChangedEvent,
)
from ollama_llm_bench.backend.task_files import ValidationSeverity
from ollama_llm_bench.ui.task_editor._internal import dialogs
from ollama_llm_bench.ui.task_editor._internal.buffer import (
    TaskBuffer,
    add_task,
    close_scratch,
    commit_boolean_field,
    commit_field_edit,
    duplicate_task,
    is_saveable,
    load_buffer,
    materialize_to_scratch,
    move_task,
    remove_tasks,
    scratch_path_for,
    set_chip_values,
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
_DEFAULT_VALIDATION_DEBOUNCE_MS = 250
_PREVIEW_DEBOUNCE_MS = 200
_SETTING_AUTO_FORMAT_ON_SAVE = "task_editor.auto_format_on_save"
_SETTING_VALIDATION_DEBOUNCE_MS = "task_editor.validation_debounce_ms"
_COULD_NOT_OPEN_MESSAGE = "Could not open the selected file"
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


def _parse_bool_setting(value: str | None, *, default: bool) -> bool:
    """Parse a ``"true"``/``"false"`` settings string; falls back to ``default``."""
    if value is None:
        return default
    return value.strip().lower() == "true"


def _parse_debounce_ms(value: str | None) -> int:
    """Parse ``task_editor.validation_debounce_ms``; falls back to the spec default
    on a missing or malformed setting, never raises."""
    if value is None:
        return _DEFAULT_VALIDATION_DEBOUNCE_MS
    try:
        parsed = int(value)
    except ValueError:
        return _DEFAULT_VALIDATION_DEBOUNCE_MS
    return max(0, parsed)


@dataclass
class _PendingFieldEdit:
    """One uncommitted field draft, staged for commit on the next validation pass,
    focus loss, or workspace switch (STORY-068-AC-6, EC-WS-4; STORY-069)."""

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
        self._clipboard = collaborators.clipboard
        self._buffers: list[TaskBuffer] = []
        self._watch_subscriptions: dict[str, FileWatchSubscription] = {}
        self._active_buffer_index: int | None = None
        self._active_task_index: int | None = None
        self._recent_files: list[str] = []
        self._preview_shown = False
        self._pending_field_edit: _PendingFieldEdit | None = None
        self._auto_format_on_save = True
        self._validation_debounce_ms = _DEFAULT_VALIDATION_DEBOUNCE_MS
        self._validation_timer: QTimer | None = None
        self._preview_timer: QTimer | None = None
        self._view: TaskEditorView | None = None
        self._refresh_settings()
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

    # ---- settings -----------------------------------------------------

    def _refresh_settings(self) -> None:
        self._auto_format_on_save = _parse_bool_setting(
            self._gateway.get_setting(_SETTING_AUTO_FORMAT_ON_SAVE), default=True
        )
        self._validation_debounce_ms = _parse_debounce_ms(
            self._gateway.get_setting(_SETTING_VALIDATION_DEBOUNCE_MS)
        )

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
        try:
            self._open_path(path)
        except OSError:
            logger.debug("task_editor_recent_file_open_failed", path=path)
            self._recent_files = [entry for entry in self._recent_files if entry != path]
            self._push_recent_files()
            self._event_bus.emit(
                SIGNAL_GLOBAL_MESSAGE,
                GlobalMessageEvent(text=_COULD_NOT_OPEN_MESSAGE, severity="error"),
            )

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
        self._validate_buffer(buffer)
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

    def _rebaseline_watch(self, path: str) -> None:
        """Restart ``path``'s watch after the editor itself wrote the file
        (STORY-112-AC-4).

        The watcher reports a path whose on-disk bytes differ from the ones it
        last read, and it cannot tell who wrote them -- so without this, a
        successful Save would immediately flag its own file as changed by
        someone else. Cancelling and re-watching re-reads the bytes the editor
        just wrote as the new baseline, leaving the file in ``Watching`` rather
        than ``Conflict`` (09_Task_Editor/state_machine.md §3, §8).
        """
        subscription = self._watch_subscriptions.pop(path, None)
        if subscription is not None:
            subscription.cancel()
        self._watch_file(path)

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

    def on_validation_summary_clicked(self) -> None:
        """Focus the active file's first task at WARNING or ERROR severity, if any
        (STORY-099-AC-2, `validation_summary_button`)."""
        buffer = self._active_buffer()
        if buffer is None or buffer.validation is None:
            return
        target_index = next(
            (
                result.task_index
                for result in sorted(buffer.validation.task_results, key=lambda r: r.task_index)
                if result.severity in (ValidationSeverity.WARNING, ValidationSeverity.ERROR)
            ),
            None,
        )
        if target_index is None:
            return
        logger.debug("task_editor_validation_summary_clicked", task_index=target_index)
        self.on_task_row_selected(target_index)

    # ---- tasks -----------------------------------------------------

    def on_add_task_clicked(self) -> None:
        buffer = self._active_buffer()
        if buffer is None:
            return
        new_index = add_task(buffer)
        self._active_task_index = new_index
        self._validate_buffer(buffer)
        logger.debug("task_editor_task_added", path=buffer.source_path, task_index=new_index)
        self._push_view_model()

    def on_duplicate_task_clicked(self, index: int) -> None:
        buffer = self._active_buffer()
        if buffer is None or not (0 <= index < task_count(buffer)):
            return
        new_index = duplicate_task(buffer, index)
        self._active_task_index = new_index
        self._validate_buffer(buffer)
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
        self._validate_buffer(buffer)
        logger.debug("task_editor_tasks_removed", path=buffer.source_path, count=len(indices))
        self._push_view_model()

    def on_move_task_clicked(self, index: int, *, offset: int) -> None:
        buffer = self._active_buffer()
        if buffer is None:
            return
        new_index = move_task(buffer, index, offset=offset)
        self._active_task_index = new_index
        self._validate_buffer(buffer)
        logger.debug(
            "task_editor_task_moved", path=buffer.source_path, from_index=index, to_index=new_index
        )
        self._push_view_model()

    # ---- field editing (STORY-069-AC-1, AC-2) -----------------------------------

    def on_field_text_changed(self, field_name: str, text: str) -> None:
        if self._active_buffer_index is None or self._active_task_index is None:
            return
        self._pending_field_edit = _PendingFieldEdit(
            buffer_index=self._active_buffer_index,
            task_index=self._active_task_index,
            field_name=field_name,
            draft_text=text,
        )
        self._schedule_validation_debounce()
        if self._preview_shown:
            self._schedule_preview_refresh()

    def on_field_focus_lost(self, field_name: str, text: str) -> None:
        buffer = self._active_buffer()
        if buffer is None or self._active_task_index is None:
            return
        commit_field_edit(
            buffer, task_index=self._active_task_index, field_name=field_name, draft_text=text
        )
        self._pending_field_edit = None
        self._revalidate_active_buffer_and_push()

    def on_field_boolean_changed(self, field_name: str, value: bool) -> None:  # noqa: FBT001  # Qt signal callback
        buffer = self._active_buffer()
        if buffer is None or self._active_task_index is None:
            return
        commit_boolean_field(
            buffer, task_index=self._active_task_index, field_name=field_name, value=value
        )
        self._revalidate_active_buffer_and_push()

    def on_field_enum_changed(self, field_name: str, value: str) -> None:
        buffer = self._active_buffer()
        if buffer is None or self._active_task_index is None:
            return
        commit_field_edit(
            buffer, task_index=self._active_task_index, field_name=field_name, draft_text=value
        )
        self._revalidate_active_buffer_and_push()

    def on_field_chip_values_changed(self, field_name: str, values: tuple[str, ...]) -> None:
        buffer = self._active_buffer()
        if buffer is None or self._active_task_index is None:
            return
        _group_key, _, leaf_key = field_name.partition(".")
        set_chip_values(
            buffer, task_index=self._active_task_index, field_name=leaf_key, values=values
        )
        self._revalidate_active_buffer_and_push()

    def _revalidate_active_buffer_and_push(self) -> None:
        buffer = self._active_buffer()
        if buffer is not None:
            self._validate_buffer(buffer)
        self._push_view_model()

    def _schedule_validation_debounce(self) -> None:
        if self._view is None:
            return
        if self._validation_timer is None:
            # Parented to `self._view` (never a bare `QTimer()`): the controller is
            # not a QObject, so parenting ties the timer's lifetime to the view's,
            # matching `ProgressController`/`LogController`'s established idiom.
            self._validation_timer = QTimer(self._view)
            self._validation_timer.setSingleShot(True)
            self._validation_timer.timeout.connect(self._on_validation_debounce_fired)
        self._validation_timer.start(self._validation_debounce_ms)

    def _on_validation_debounce_fired(self) -> None:
        self._commit_pending_field_edit()
        self._revalidate_active_buffer_and_push()

    def _schedule_preview_refresh(self) -> None:
        if self._view is None:
            return
        if self._preview_timer is None:
            self._preview_timer = QTimer(self._view)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.timeout.connect(self._on_preview_timer_fired)
        self._preview_timer.start(_PREVIEW_DEBOUNCE_MS)

    def _on_preview_timer_fired(self) -> None:
        self._commit_pending_field_edit()
        buffer = self._active_buffer()
        if buffer is None or self._view is None:
            return
        text = materialize_to_scratch(
            buffer, yaml_formatter=self._yaml_formatter, format_on_save=self._auto_format_on_save
        )
        self._view.set_preview_text(text)

    # ---- validation (delegates to TaskFileValidator; never validates itself) ----

    def _validate_buffer(self, buffer: TaskBuffer) -> None:
        scratch = scratch_path_for(buffer)
        self._yaml_formatter.save(
            document=buffer.document, target_path=scratch, format_on_save=self._auto_format_on_save
        )
        buffer.validation = self._task_file_validator.validate(scratch)

    # ---- YAML preview (STORY-069-AC-5, EC-WS-3) -----------------------------

    def on_view_yaml_toggled(self) -> None:
        self._preview_shown = not self._preview_shown
        logger.debug("task_editor_view_yaml_toggled", shown=self._preview_shown)
        self._push_view_model()

    def on_copy_yaml_clicked(self) -> None:
        logger.debug("task_editor_copy_yaml_clicked")
        self._clipboard.copy_text(self._compute_preview_text())

    def _compute_preview_text(self) -> str:
        if not self._preview_shown:
            return ""
        buffer = self._active_buffer()
        if buffer is None:
            return ""
        return materialize_to_scratch(
            buffer, yaml_formatter=self._yaml_formatter, format_on_save=self._auto_format_on_save
        )

    # ---- Save orchestration (STORY-069-AC-3, AC-4) --------------------------

    def on_save_clicked(self) -> None:
        buffer = self._active_buffer()
        if buffer is None or not buffer.is_dirty or not is_saveable(buffer):
            return
        logger.debug("task_editor_save_clicked", path=buffer.source_path)
        self._save_buffer(buffer)
        self._push_view_model()

    def on_save_all_clicked(self) -> None:
        logger.debug("task_editor_save_all_clicked", dirty_count=self.dirty_buffer_count())
        self.save_all_buffers()

    def _save_buffer(self, buffer: TaskBuffer) -> bool:
        if buffer.is_in_use_by_run and not dialogs.confirm_in_use_save():
            logger.debug("task_editor_save_deferred_in_use", path=buffer.source_path)
            return False
        result = self._yaml_formatter.save(
            document=buffer.document,
            target_path=buffer.source_path,
            format_on_save=self._auto_format_on_save,
        )
        if not result.succeeded:
            logger.debug(
                "task_editor_save_failed", path=buffer.source_path, reason=result.failure_reason
            )
            dialogs.show_save_failure(reason=result.failure_reason, detail=result.detail)
            return False
        buffer.is_dirty = False
        self._rebaseline_watch(buffer.source_path)
        self._validate_buffer(buffer)
        self._event_bus.emit(
            SIGNAL_TASK_FILE_CHANGED,
            TaskFileChangedEvent(
                path=buffer.source_path, task_count=task_count(buffer), change_kind="saved"
            ),
        )
        self._event_bus.emit(
            SIGNAL_GLOBAL_MESSAGE,
            GlobalMessageEvent(text=f"Saved {Path(buffer.source_path).name}", severity="info"),
        )
        logger.debug("task_editor_save_succeeded", path=buffer.source_path)
        return True

    def dirty_buffer_count(self) -> int:
        """Return how many open buffers hold unsaved edits (STORY-114-AC-1).

        Fast and synchronous; called from the GUI thread by the application-level
        quit sequence through the callable ``compose.py`` injects into
        ``make_main_window``.
        """
        return sum(1 for buffer in self._buffers if buffer.is_dirty)

    def save_all_buffers(self) -> tuple[str, ...]:
        """Save every dirty buffer that has no hard error; report the rest as data.

        A dirty file that still holds a hard validation error cannot be written
        (§3.7) -- that is an ordinary, expected outcome, so it comes back as a
        value the quit path inspects, never as a raised error (STORY-114-AC-2,
        AC-3).

        The result is derived from which buffers are *still dirty afterwards*
        rather than from ``_save_buffer``'s return value, deliberately: a buffer
        skipped by ``is_saveable`` never reaches ``_save_buffer`` at all, and the
        same "still dirty" reading also covers an in-use-by-run save the user
        declined and a ``SaveResult`` that failed. Every case where an edit would
        otherwise be lost therefore holds the quit.

        Returns:
            The display names of the buffers still dirty once every saveable
            buffer has been written -- empty when everything saved.
        """
        for buffer in self._buffers:
            if buffer.is_dirty and is_saveable(buffer):
                self._save_buffer(buffer)
        self._push_view_model()
        return tuple(Path(buffer.source_path).name for buffer in self._buffers if buffer.is_dirty)

    # ---- leave/quit guard (STORY-069-AC-6) -----------------------------------

    def confirm_and_prepare_leave(self) -> bool:
        """Run the leave-confirmation flow (§3.7); ``True`` means the workspace
        switch may proceed."""
        return self._resolve_dirty_buffers(dialog=dialogs.confirm_leave)

    def confirm_and_prepare_quit(self) -> bool:
        """Run the quit-confirmation flow (§3.7); ``True`` means the quit may
        proceed.

        **No production caller (STORY-114).** The application-level quit prompt
        is owned by ``ui/main_window/_internal/close_handler.py``, which reaches
        this controller through ``dirty_buffer_count``/``save_all_buffers``
        instead. Retained as the counterpart of ``confirm_and_prepare_leave``,
        which remains the live path for the still-unowned leave half of §3.7.
        """
        return self._resolve_dirty_buffers(dialog=dialogs.confirm_quit)

    def _resolve_dirty_buffers(self, *, dialog: Callable[[int], str]) -> bool:
        dirty_buffers = [buffer for buffer in self._buffers if buffer.is_dirty]
        if not dirty_buffers:
            return True
        choice = dialog(len(dirty_buffers))
        logger.debug("task_editor_dirty_buffers_resolution", choice=choice)
        if choice == "cancel":
            return False
        if choice == "discard_all":
            for buffer in dirty_buffers:
                self._reload_buffer(buffer)
            return True
        for buffer in dirty_buffers:
            if is_saveable(buffer):
                self._save_buffer(buffer)
        self._push_view_model()
        return not any(buffer.is_dirty for buffer in self._buffers)

    # ---- files-pane actions -----------------------------------------------------

    def on_reload_clicked(self) -> None:
        buffer = self._active_buffer()
        if buffer is None:
            return
        if buffer.is_dirty and not dialogs.confirm_reload():
            logger.debug("task_editor_reload_cancelled", path=buffer.source_path)
            return
        self._reload_buffer(buffer)

    def on_reload_from_disk_context_menu(self, index: int) -> None:
        if not (0 <= index < len(self._buffers)):
            return
        buffer = self._buffers[index]
        if buffer.is_dirty and not dialogs.confirm_reload():
            logger.debug("task_editor_reload_cancelled", path=buffer.source_path)
            return
        self._reload_buffer(buffer)

    def _reload_buffer(self, buffer: TaskBuffer) -> None:
        logger.debug("task_editor_reload_from_disk", path=buffer.source_path)
        buffer.document = self._yaml_formatter.load_document(buffer.source_path)
        buffer.is_external_changed = False
        buffer.is_dirty = False
        self._validate_buffer(buffer)
        index = self._find_buffer_index(buffer.source_path)
        if index is not None and index == self._active_buffer_index:
            self._active_task_index = 0 if task_count(buffer) > 0 else None
        self._push_view_model()

    def on_close_file_clicked(self, index: int) -> None:
        if not (0 <= index < len(self._buffers)):
            return
        buffer = self._buffers[index]
        if buffer.is_dirty:
            choice = dialogs.confirm_close(Path(buffer.source_path).name)
            logger.debug("task_editor_close_confirmation_resolved", choice=choice)
            if choice == "cancel":
                return
            if choice == "save_and_close" and not self._save_buffer(buffer):
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
        close_scratch(buffer)
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
        self._refresh_settings()

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
            preview_text=self._compute_preview_text(),
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
