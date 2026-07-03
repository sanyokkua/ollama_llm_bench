# Task Editor — Implementation Structure

**Status:** Draft
**Owner:** architect
**Audience:** arch, coder
**Last Updated:** 2026-06-06
**Cross-references:** `09_Task_Editor/description.md`, `09_Task_Editor/state_machine.md`, `09_Task_Editor/flow_diagram.md`, `08_Cross_Cutting/08-A_architecture_principles.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `11_Services_and_Algorithms/12_YAML_FORMATTER.md`, `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `14_Process_and_Traceability/01_MODULE_INVENTORY.md`

This document specifies how the Task Editor workspace is structured as a PySide6 module: its module path, public API, sub-modules, the view-model struct that drives the panes, the controller and its subscriptions, the factory wiring, the dependency Protocols it consumes, the store fanout, and the test boundary. It defines structure, not implementation code; it is the binding contract for the module's public surface and its dependency edges.

---

## Table of Contents

1. Module path
2. Public API
3. Sub-modules
4. View-model struct
5. Controller
6. Factory wiring
7. Dependency Protocols
8. Store fanout
9. Test boundary

---

## 1. Module path

```
src/ollama_llm_bench/ui/task_editor/
```

The Task Editor is a UI module under `src/ollama_llm_bench/ui/`. It is constructed lazily — the Workspace Controller calls its factory the first time the user enters the Task Editor workspace and keeps the instance alive for the rest of the session. It follows the layering rules of `08_Cross_Cutting/08-A_architecture_principles.md`: it depends only on Protocols and DTOs, never on concrete service implementations, and never on another widget module.

The module's internal files live under `src/ollama_llm_bench/ui/task_editor/_internal/`; only the names re-exported from the package `__init__` are public. The module's public surface is a single factory function plus the view-model struct it exposes for testing.

## 2. Public API

```python
def make_task_editor_workspace(
    *,
    bus: EventBus,
    gateway: TaskEditorGateway,
    task_file_loader: TaskFileLoader,
    task_file_validator: TaskFileValidator,
    yaml_formatter: YamlFormatter,
    validation_cascade: ValidationCascade,
    file_change_watcher: FileChangeWatcher,
    native_pickers: NativePickers,
    file_system_actions: FileSystemActions,
) -> QWidget: ...
```

The factory returns a single `QWidget` — the workspace root — that the Workspace Controller mounts into the Main Window central region. Every dependency is passed in as a Protocol; the factory constructs no service of its own. The factory wires the controller, the three (or four) panes, and the toolbar, and returns before any file is loaded; the workspace opens in its `Empty` state.

## 3. Sub-modules

Per `08_Cross_Cutting/08-A_architecture_principles.md`, a widget is split into sub-modules when its public surface would exceed five files or its `_internal/` would exceed roughly 1500 lines. The Task Editor is large — three panes, a toolbar, a preview panel, the validation cascade integration, the file lifecycle — so it is split. The single public factory composes these sub-modules; none of them is public on its own.

| Sub-module | Responsibility |
|---|---|
| `_internal/toolbar.py` | The Editor Toolbar: Open File, Open Folder, New File, Save, Save All, Reload, View YAML, the validation pill. |
| `_internal/files_pane.py` | The Files pane: the flat list of open buffers, per-file badges, the dirty marker, the context menu, drag-drop acceptance. |
| `_internal/tasks_pane.py` | The Tasks pane: the per-file task list, per-task badges, add / duplicate / remove / reorder controls and multi-select. |
| `_internal/field_editor.py` | The Field-editor pane: the scrollable Form, the Field Rows, the conditional groups, the help popovers. |
| `_internal/field_rows.py` | The Field Row controls — identifier input, short-text input, long-text auto-grow input, enum dropdown, editable combo box, Chip Input — and their per-field validation strips. |
| `_internal/yaml_preview.py` | The read-only YAML preview side panel and its Copy YAML control. |
| `_internal/buffer.py` | The in-memory buffer model: the round-trip YAML document handle, the draft task list, the dirty flag, and the per-buffer validation state. |
| `_internal/controller.py` | The workspace controller (§5): event-bus subscriptions, derived-state computation, the file lifecycle, and Save orchestration. |
| `_internal/view_model.py` | The `TaskEditorViewModel` struct (§4) and the per-pane view-model slices. |
| `_internal/dialogs.py` | The leave-confirmation, quit-confirmation, close-confirmation, reload-confirmation, in-use-on-save, and save-failure dialogs. |

## 4. View-model struct

The displayed state of the workspace is a frozen `msgspec.Struct`. The controller computes a new view-model on every relevant change and the panes render from it; the panes hold no derived state of their own.

```python
class TaskEditorViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    files: tuple[FileRowViewModel, ...]
    active_file_index: int | None
    tasks: tuple[TaskRowViewModel, ...]
    active_task_index: int | None
    field_rows: tuple[FieldRowViewModel, ...]
    toolbar_state: ToolbarViewModel
    preview_shown: bool
    preview_text: str
    is_empty: bool


class FileRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    path: str
    display_name: str
    is_dirty: bool
    is_active: bool
    validation_state: ValidationState     # clean | info | warning | error
    is_external_changed: bool
    is_in_use_by_run: bool


class TaskRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    task_id: str
    is_selected: bool
    validation_state: ValidationState


class FieldRowViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    field_name: str
    label: str
    is_required: bool
    format_hint: str
    help_text: str
    control_kind: FieldControlKind        # identifier | short_text | long_text
                                          # | enum | open_combo | chip_list
    value: str
    chip_values: tuple[str, ...]
    is_visible: bool                      # false when a conditional group is hidden
    validation_state: ValidationState
    validation_message: str


class ToolbarViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    save_enabled: bool
    save_all_enabled: bool
    save_all_count: int
    reload_enabled: bool
    aggregate_state: ValidationState
    aggregate_task_count: int
    aggregate_warning_count: int
    aggregate_error_count: int
```

`ValidationState` and `FieldControlKind` are `StrEnum` values declared with the other UI enums; the field-domain enum (`Difficulty`) is imported from `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` and are never redefined here. The view-model carries display state only; the editable round-trip YAML document and the draft task list live in `_internal/buffer.py` and are not part of the view-model.

## 5. Controller

`_internal/controller.py` holds the `TaskEditorController`. It owns the open buffers, computes the view-model, runs the file lifecycle, and orchestrates Save. It subscribes to the Event Bus with ownership-binding (`08_Cross_Cutting/08-J_event_bus_catalog.md` §2), the owner being the controller itself.

**Subscriptions:**

| Event | Handler responsibility |
|---|---|
| `_app_settings_changed` | Re-read `task_editor.auto_format_on_save`, `task_editor.warn_on_empty_grading_criteria`, `task_editor.validation_debounce_ms`, and `ui.task_editor_last_folder` through `TaskEditorGateway.get_setting`. |
| `_run_started` | Mark file rows whose path is in the run's task list (`TaskEditorGateway.active_run_task_paths()`) as in-use; show the Running pill. |
| `_run_finished` / `_run_stopped` / `_run_failed` | Clear in-use markers; hide the Running pill. |
| `_run_renamed` | Refresh the Running pill label. |
| `_workspace_changed` | Restore the in-memory view-model when the Task Editor becomes the active workspace. |

**Emissions:**

| Event | When |
|---|---|
| `_task_file_changed` | After every successful Save of a file. |
| `_workspace_changed` | On every workspace switch involving the Task Editor (raised through the Workspace Controller). |
| `_global_message` | On a save success and on a save failure, surfaced as a Status Bar toast. |

**Derived-state computations:**

- The view-model is recomputed on a file open, file close, file switch, task select, task add / remove / reorder, field edit, validation pass, external-change detection, and preview toggle.
- The file lifecycle of `state_machine.md` §3 is driven here: a buffer transitions `Loaded → Dirty` on any edit, returns to `Loaded` on a successful Save, and routes through confirmations for reload and close.
- The validation cascade is invoked on every edit; the controller maps the returned `ValidationReport` onto the per-row `validation_state` fields and onto `ToolbarViewModel.save_enabled`.
- Save delegates serialization and the atomic write to the YAML Formatter, which runs off the UI thread (`11_Services_and_Algorithms/12_YAML_FORMATTER.md` §9); the controller awaits its completion signal on the UI thread before updating the view-model.

The controller never serializes YAML, never parses YAML, and never validates fields itself — it delegates to the YAML Formatter, the Task File Loader, and the validation cascade respectively.

## 6. Factory wiring

The composition root wires the Task Editor once, passing the shared service Protocols and reactive stores. The Workspace Controller calls the factory lazily on first entry to the workspace.

```python
# in src/ollama_llm_bench/compose.py
def build_task_editor(ctx: AppContext) -> QWidget:
    return make_task_editor_workspace(
        bus=ctx.event_bus,
        gateway=ctx.task_editor_gateway,
        task_file_loader=ctx.task_file_loader,
        task_file_validator=ctx.task_file_validator,
        yaml_formatter=ctx.yaml_formatter,
        validation_cascade=ctx.validation_cascade,
        file_change_watcher=ctx.file_change_watcher,
        native_pickers=ctx.native_pickers,
        file_system_actions=ctx.file_system_actions,
    )
```

`AppContext` holds the single instance of each service and store; the factory receives them but constructs none of them. The Workspace Controller registers `build_task_editor` as the lazy builder for the Task Editor workspace slot.

## 7. Dependency Protocols

The Task Editor consumes these Protocols; their full contracts are in `08_Cross_Cutting/08-E_interfaces_contracts.md` and the matching `11_Services_and_Algorithms/` files.

| Protocol | Role | Contract |
|---|---|---|
| `EventBus` | Subscribe to the events of §5; emit `_task_file_changed`, `_global_message`. | `08_Cross_Cutting/08-J_event_bus_catalog.md` |
| `TaskEditorGateway` | The adapter gateway (08-E §7b.7) exposing the workspace's settings / workspace-state / in-use-marker surface: `get_setting`/`set_setting` for the workspace settings keys, `active_workspace()`, and `active_run_task_paths()` for the in-use marker; wraps `SettingsStore`, `WorkspaceStore`, and `RunRegistryStore` (D-R-06). | `08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.7 |
| `TaskFileLoader` | Loader-tolerant parse of a file into `BenchmarkTask` records. | `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` |
| `TaskFileValidator` | Editor-strict per-row diagnostics. | `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md` |
| `YamlFormatter` | The single writer of task files — canonical order, comment preservation, atomic save. | `11_Services_and_Algorithms/12_YAML_FORMATTER.md` |
| `ValidationCascade` | The three-level field / task / file cascade and Save gating. | `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md` |
| `FileChangeWatcher` | Detect an open file changing on disk. | `08_Cross_Cutting/08-E_interfaces_contracts.md` |
| `NativePickers` | File and folder pickers (`open_file`, `open_folder`, `save_file`). | `08_Cross_Cutting/08-E_interfaces_contracts.md` |
| `FileSystemActions` | "Reveal in File Manager" via `open_in_file_manager`. | `08_Cross_Cutting/08-E_interfaces_contracts.md` |

The Task Editor has **no** persistence-store dependency — task files are YAML on disk, not in the SQLite database. Task-file reads and writes go through `TaskFileLoader`, `TaskFileValidator`, and `YamlFormatter`; the native pickers and file-system actions cover the OS surface area; the workspace's settings, workspace-state, and in-use-marker reads cross the `TaskEditorGateway`.

**Adapter boundary (D-R-06).** The controller depends only on `TaskEditorGateway` for the `SettingsStore`, `WorkspaceStore`, and `RunRegistryStore` surface (plus the Event Bus and the retained `TaskFileLoader`, `TaskFileValidator`, `YamlFormatter`, `ValidationCascade`, `FileChangeWatcher`, `NativePickers`, and `FileSystemActions` helpers), never on a backend Protocol — no `SettingsStore`, `WorkspaceStore`, or `RunRegistryStore` reaches the controller (08-A §5/§6); the adapter holds those behind the gateway.

## 8. Store fanout

The Task Editor depends on a single `TaskEditorGateway` (its settings / workspace-state / in-use-marker surface) plus the Event Bus. That fan-out is within the soft limit (`08_Cross_Cutting/08-A_architecture_principles.md` allows a controller up to four store subscriptions before a split is required), so the workspace keeps a single controller rather than splitting into per-pane controllers. The per-pane sub-modules are view-only: they render the slices of `TaskEditorViewModel` the controller hands them and forward user intent back to the controller; they hold no store subscriptions of their own.

If a future change widens the gateway's surface enough to push the controller past the soft limit, it is to be split along the seam already present in the view-model — a files-and-toolbar controller and a field-editor controller — before the limit is exceeded.

## 9. Test boundary

| Test target | Location | What is covered |
|---|---|---|
| Buffer model | `tests/` colocated with `_internal/buffer.py` | Dirty-flag transitions, the draft task list, Form B / Form C to Form A conversion, unknown-key preservation. |
| Validation mapping | colocated with `_internal/controller.py` | The `ValidationReport` to view-model mapping; Save-enable gating; the toolbar aggregate counts. |
| Field Row controls | colocated with `_internal/field_rows.py` | Each control kind round-trips a value; the Chip Input add / remove / paste-split behaviour; the enum dropdown and editable combo box. |
| View-model computation | colocated with `_internal/view_model.py` | The view-model is a pure function of the buffers and the validation state. |
| Workspace integration | `tests/integration/` at the top level, with `pytest-qt` | Open a file, edit a field, see the badge change, Save, observe `_task_file_changed`; the leave-confirmation flow; drag-drop; the external-change banner. |

The YAML Formatter, the Task File Loader, the validation cascade, and the OS Adapter are exercised through their own test suites and are supplied to the Task Editor's tests as the fakes documented in each service's `testing.py` (`11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`). The Task Editor's own tests never touch the real filesystem except in the top-level integration tests, which use a temporary directory.
