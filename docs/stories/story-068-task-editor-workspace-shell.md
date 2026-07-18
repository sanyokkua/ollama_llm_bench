---
id: STORY-068
title: Build the Task Editor workspace shell — toolbar, Files pane, Tasks pane, buffer model, and view-model
status: ready
spec_clauses:
  - 09_Task_Editor/description.md#2-layout
  - 09_Task_Editor/description.md#32-editor-toolbar
  - 09_Task_Editor/description.md#33-files-pane
  - 09_Task_Editor/description.md#34-tasks-pane
  - 09_Task_Editor/description.md#7-event-bus-integration
  - 09_Task_Editor/implementation_structure.md#5-controller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b7-taskeditorgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/task_editor/
acceptance_criteria:
  - STORY-068-AC-1
  - STORY-068-AC-2
  - STORY-068-AC-3
  - STORY-068-AC-4
  - STORY-068-AC-5
  - STORY-068-AC-6
  - STORY-068-AC-7
edge_cases:
  - EC-WS-4
depends_on:
  - STORY-049
  - STORY-051
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-068 — Build the Task Editor workspace shell — toolbar, Files pane, Tasks pane, buffer model, and view-model

## Goal

Deliver the Task Editor workspace skeleton and its file/task lifecycle: the editor toolbar
(Open File / Open Folder / New File / Save / Save All / Reload / View YAML / validation pill),
the Files pane (flat buffer list with per-file badges and dirty markers, drag-drop, context
menu, and the in-use-by-run marker), the Tasks pane (per-task list with add/duplicate/remove/
reorder), the in-memory buffer model, and the `TaskEditorViewModel` the controller computes.
The field editor, YAML preview, save/validation cascade, and the confirmation dialogs are added
by STORY-069.

## In scope

- `ui/task_editor/protocols.py`: the `TaskEditorGateway` Protocol declared locally with the exact
  method signatures of 08-E §7b.7 (`get_setting` / `set_setting`, `active_workspace`,
  `active_run_task_paths`).
- `ui/task_editor/api.py`: `make_task_editor_workspace(...) -> QWidget` — the single public
  symbol — and the `TaskEditorController` with its subscriptions and derived-state computation.
- `_internal/toolbar.py`: the toolbar buttons, the `Save All (N)` dirty-count suffix, and the
  aggregate validation pill.
- `_internal/files_pane.py`: the flat buffer list, per-file badges (clean/dirty/warning/error/
  reload-pending), drag-drop acceptance, the context menu, the footer open/create controls, and
  the in-use banner marking.
- `_internal/tasks_pane.py`: the per-file task list, per-task badges, add/duplicate/remove/reorder
  with the generated `task_id` rules, and multi-select.
- `_internal/buffer.py` and `_internal/view_model.py`: the in-memory buffer model (dirty flag,
  draft task list, Form B/C to Form A conversion, unknown-key preservation) and the frozen
  `TaskEditorViewModel` computed by the controller.

## Out of scope

- The Field-editor pane, the field rows, the YAML preview panel, the Save/validation cascade
  integration, and the leave/quit/close/reload/in-use/save-failure dialogs — owned by STORY-069.
- The `YamlFormatter`, `TaskFileLoader`, `TaskFileValidator`, `ValidationCascade`, and
  `FileChangeWatcher` — consumed as Protocols.
- Wiring the concrete `TaskEditorGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `09_Task_Editor/description.md#2-layout` — the three/four-pane layout, the Empty vs With-files
  states, the recent-files list, and the status-bar aggregate.
- `09_Task_Editor/description.md#32-editor-toolbar` — every toolbar control, its action, its
  enablement gate, and the `Save All (N)` suffix.
- `09_Task_Editor/description.md#33-files-pane` — the flat list, the per-file badges, the drag-drop
  behaviour, and the context menu.
- `09_Task_Editor/description.md#34-tasks-pane` — the task list, the per-task badges, and the
  add/duplicate/remove/reorder controls with their id-generation rules.
- `09_Task_Editor/description.md#7-event-bus-integration` — the subscribed events (incl.
  `_run_started` marking in-use files) and the emitted `_task_file_changed` / `_workspace_changed`
  / `_global_message`.
- `09_Task_Editor/implementation_structure.md#5-controller` — the controller's subscriptions, the
  file lifecycle, and the derived-state computation.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b7-taskeditorgateway` — the gateway surface this
  widget's `protocols.py` declares.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The controller depends only on its `TaskEditorGateway` Protocol plus the retained non-store
  helpers (`EventBus`, `TaskFileLoader`, `NativePickers`, `FileSystemActions`, `FileChangeWatcher`);
  it holds no `SettingsStore`/`WorkspaceStore`/`RunRegistryStore` directly (D-R-06).
- The panes are view-only: they render the `TaskEditorViewModel` slices and forward user intent;
  they hold no store subscription of their own.
- Open buffers, the active file, the selected task, and the preview-shown flag are in-memory only
  and survive a workspace switch within a session; an in-progress field edit is committed to the
  buffer before a workspace switch.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-068-AC-1

Given no files are open, when the workspace renders, then it shows the Empty state with the drop
target and the recent-files list; and when the first file is opened, then it moves to the
With-files state with that file active.

### STORY-068-AC-2

For each per-file state, the Files-pane row renders the specified badge:

| File state                 | Badge          |
| -------------------------- | -------------- |
| saved and valid            | clean          |
| unsaved edits              | dirty          |
| soft warnings              | warning        |
| hard errors                | error          |
| changed on disk while open | reload-pending |

### STORY-068-AC-3

Given the active file, when the user clicks Add Task, then a blank task is appended with the
generated `task_id` `<filename_stem>_new_<N>`, selected, and the file marked dirty; and when the
user clicks Duplicate on a selected task, then a clone is inserted below it with a unique
`_copy<N>` id.

### STORY-068-AC-4

Given a run is active, when a `_run_started` event carries the run's task paths, then every open
file whose path is in that list is marked in-use; and when a terminal run event arrives, then the
in-use markers clear.

### STORY-068-AC-5

Given a file is loaded in bare-sequence (Form B) or single-mapping (Form C) shape, when the
buffer model ingests it, then it is converted to canonical Form A in memory and any unknown YAML
key is preserved verbatim.

### STORY-068-AC-6

Given the workspace is switched away while a Task Editor field holds uncommitted text, when the
switch is handled, then the in-progress field edit is committed to the in-memory buffer and the
buffer's dirty state is preserved.

### STORY-068-AC-7

Given the workspace is constructed via its own factory function (`make_task_editor_workspace`)
with a fake `TaskEditorGateway` (and fakes for the declared non-store helpers `EventBus`,
`TaskFileLoader`, `NativePickers`, `FileSystemActions`, and `FileChangeWatcher`) and mounted
under `qtbot`, when it is shown (`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/
event-loop pump), then no exception is raised, the widget reports `isVisible()`, and no
`error`/`critical`-level `structlog` record is captured — verified by wrapping construction+show
in `structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`.

## Test plan

- STORY-068-AC-1 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_view_model.py`,
  `test_empty_to_with_files_transition`.
- STORY-068-AC-2 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_files_pane.py`,
  `test_file_badge_per_state`.
- STORY-068-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_tasks_pane.py`,
  `test_add_and_duplicate_task_id_generation`.
- STORY-068-AC-4 — unit (`pytest-qt`, fake `TaskEditorGateway`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_controller.py`,
  `test_run_started_marks_in_use_files`.
- STORY-068-AC-5 — unit (no Qt), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_buffer.py`,
  `test_form_b_c_to_a_and_unknown_key_preserved`.
- STORY-068-AC-6 — unit (`pytest-qt`), `test_controller.py`,
  `test_workspace_switch_commits_field_edit`. Covers EC-WS-4.
- STORY-068-AC-7 — unit (`pytest-qt`, fake `TaskEditorGateway`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_view_model.py`,
  `test_task_editor_workspace_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-068.
- [ ] EC-WS-4 has a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Empty / With-files
  workspace-level states and the per-file Loaded / Dirty / ExternalChanged states of
  `09_Task_Editor/state_machine.md` that the shell owns.
- [ ] An architecture test confirms the controller depends only on `TaskEditorGateway` (plus the
  declared non-store helpers) and holds no persistence-store Protocol, and that the module
  references no `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/task_editor/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-068.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
