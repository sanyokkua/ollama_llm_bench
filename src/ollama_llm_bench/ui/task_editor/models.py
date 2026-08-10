"""Dependency bundle and view-model struct family for ``ui/task_editor/`` (STORY-068,
STORY-069).

Source of truth: ``docs/v3_specification/09_Task_Editor/implementation_structure.md``
§4 (view-model structs, declared verbatim below). STORY-069 populates ``field_rows``,
``preview_shown``, and ``preview_text`` for real (the Field-editor pane, the Save/
validation-cascade integration, and the YAML preview panel), and widens
``TaskEditorCollaborators`` by exactly one field (``clipboard``) for the preview
panel's Copy YAML action -- Save already had ``yaml_formatter``, validation already
had ``task_file_validator``; no ``ValidationCascade`` Protocol exists anywhere in the
spec tree (verified by repository grep), so none is added here.
"""

from collections.abc import Callable
from enum import StrEnum

import msgspec
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers
from ollama_llm_bench.backend.task_files import TaskFileLoader, TaskFileValidator
from ollama_llm_bench.backend.yaml_formatter import YamlFormatter
from ollama_llm_bench.ui.task_editor.protocols import FileChangeWatcher, TaskEditorGateway

__all__: list[str] = [
    "FieldControlKind",
    "FieldRowViewModel",
    "FileRowViewModel",
    "TaskEditorCollaborators",
    "TaskEditorViewModel",
    "TaskEditorWorkspace",
    "TaskRowViewModel",
    "ToolbarViewModel",
    "ValidationState",
]


class ValidationState(StrEnum):
    """Per-row/task/toolbar aggregate validation severity (§4): ``clean < info <
    warning < error``."""

    CLEAN = "clean"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FieldControlKind(StrEnum):
    """The Field Row input-control kind (§4; §3.5.1). ``BOOLEAN`` is a STORY-069
    addition -- ``cosine_enabled`` is the only field mapped to it (a UI-layer
    view-model enum only, never persisted to SQLite or serialized to YAML by name,
    so adding a member is a safe additive change). ``OPEN_COMBO`` stays
    declared-but-unused -- no field maps to it."""

    IDENTIFIER = "identifier"
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    ENUM = "enum"
    OPEN_COMBO = "open_combo"
    CHIP_LIST = "chip_list"
    BOOLEAN = "boolean"


class TaskEditorCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_task_editor_workspace`` (coding-style.md's
    4-parameter hard maximum). ``EventBus`` is passed to the factory separately
    (``implementation_structure.md`` §2). ``clipboard`` is STORY-069's one addition,
    for the YAML preview panel's Copy YAML action; ``yaml_formatter.save()`` is now
    used for real (scratch materialization and the real Save)."""

    gateway: TaskEditorGateway
    task_file_loader: TaskFileLoader
    task_file_validator: TaskFileValidator
    yaml_formatter: YamlFormatter
    file_change_watcher: FileChangeWatcher
    native_pickers: NativePickers
    file_system_actions: FileSystemActions
    clipboard: Clipboard


class TaskEditorWorkspace(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The mountable Task Editor workspace plus the two quit-sequence hooks the
    composition root injects into ``make_main_window`` (STORY-114).

    The hooks cross the boundary as plain callables so ``ui/main_window/`` never
    imports ``ui/task_editor/``; ``compose.py`` reads them off this handle exactly
    as it already does for the Settings-open and About-open callbacks.
    """

    widget: QWidget
    dirty_buffer_count: Callable[[], int]
    save_all_buffers: Callable[[], tuple[str, ...]]


class FileRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One Files-pane row (§4). The displayed badge is derived from this row's
    fields at render time with precedence ``reload-pending > error/warning >
    dirty > clean`` (STORY-068-AC-2) -- there is no single "badge" field."""

    path: str
    display_name: str
    is_dirty: bool
    is_active: bool
    validation_state: ValidationState
    is_external_changed: bool
    is_in_use_by_run: bool


class TaskRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One Tasks-pane row for the active file (§4)."""

    task_id: str
    is_selected: bool
    validation_state: ValidationState


class FieldRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One Field-editor row (§4, §3.5.1). ``value`` carries the field's current
    scalar text (or ``"true"``/``"false"`` for a ``BOOLEAN`` field); ``chip_values``
    is populated only for a ``CHIP_LIST`` field."""

    field_name: str
    label: str
    is_required: bool
    format_hint: str
    help_text: str
    control_kind: FieldControlKind
    value: str
    chip_values: tuple[str, ...]
    is_visible: bool
    validation_state: ValidationState
    validation_message: str


class ToolbarViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Editor Toolbar's render state (§4, §3.2). ``save_enabled``/
    ``save_all_enabled``/``save_all_count`` now drive real Save/Save All actions
    (STORY-069)."""

    save_enabled: bool
    save_all_enabled: bool
    save_all_count: int
    reload_enabled: bool
    aggregate_state: ValidationState
    aggregate_task_count: int
    aggregate_warning_count: int
    aggregate_error_count: int


class TaskEditorViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The full Task Editor workspace render state (§4). The panes hold no derived
    state of their own -- they render exactly this struct."""

    files: tuple[FileRowViewModel, ...]
    active_file_index: int | None
    tasks: tuple[TaskRowViewModel, ...]
    active_task_index: int | None
    field_rows: tuple[FieldRowViewModel, ...]
    toolbar_state: ToolbarViewModel
    preview_shown: bool
    preview_text: str
    is_empty: bool
