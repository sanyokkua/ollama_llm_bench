"""Dependency bundle and view-model struct family for ``ui/task_editor/`` (STORY-068).

Source of truth: ``docs/v3_specification/09_Task_Editor/implementation_structure.md``
§4 (view-model structs, declared verbatim below). Only this story's shell fields are
populated -- ``field_rows`` stays ``()``, ``preview_shown`` stays ``False``, and
``preview_text`` stays ``""`` until STORY-069 builds the Field-editor pane and the
YAML preview, mirroring how ``ui/results/models.py`` declares its full parent-shell
struct family while individual tabs populate their own slices.
"""

from enum import StrEnum

import msgspec

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
    """The Field Row input-control kind (§4; populated by STORY-069's Field-editor
    pane)."""

    IDENTIFIER = "identifier"
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    ENUM = "enum"
    OPEN_COMBO = "open_combo"
    CHIP_LIST = "chip_list"


class TaskEditorCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_task_editor_workspace`` (coding-style.md's
    4-parameter hard maximum). ``EventBus`` is passed to the factory separately
    (``implementation_structure.md`` §2); ``validation_cascade`` is withheld until
    STORY-069 widens this bundle, and ``yaml_formatter`` is used only for
    ``.load_document()`` this story -- ``.save()`` stays unused until STORY-069."""

    gateway: TaskEditorGateway
    task_file_loader: TaskFileLoader
    task_file_validator: TaskFileValidator
    yaml_formatter: YamlFormatter
    file_change_watcher: FileChangeWatcher
    native_pickers: NativePickers
    file_system_actions: FileSystemActions


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
    """One Field-editor row (§4). Not populated until STORY-069 -- this story's
    ``TaskEditorViewModel.field_rows`` is always ``()``."""

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
    ``save_all_enabled`` are computed honestly from the buffers, but the toolbar
    view renders Save/Save All disabled regardless this story (STORY-068 design
    decision: they are fixed, permanent toolbar members with no working action
    until STORY-069)."""

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
