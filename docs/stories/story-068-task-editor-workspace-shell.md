---
id: STORY-068
title: Build the Task Editor workspace shell — toolbar, Files pane, Tasks pane, buffer model, and view-model
status: done
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

## Notes

Implementation notes from the coder pass (this story's shell only — STORY-069 owns the
Field-editor pane, YAML preview, Save/validation-cascade wiring, and every confirmation
dialog):

- **`tests/` layout.** Tests are colocated at `ui/task_editor/tests/`, not
  `ui/task_editor/_internal/tests/` as the test-plan paths literally read. This matches the
  real, current precedent of every other completed workspace module in this codebase
  (`ui/results/tests/`, `ui/resume_benchmark/tests/`, `ui/new_benchmark/tests/`) and the
  documented `_internal` import boundary (nothing outside a module's own `_internal/` package
  imports it — `_internal/tests/` would sit *inside* that private package). The coder pass did
  not write these test files itself (writing acceptance-criteria tests is the tester agent's
  job in this project's pipeline); the tester should create
  `ui/task_editor/tests/{__init__.py,conftest.py,test_buffer.py,test_view_model.py, test_files_pane.py,test_tasks_pane.py,test_controller.py}` per the module shape above.
- **`_internal/view.py` added.** Not literally listed in the story's "Module shape" sub-module
  table, but required to compose the toolbar, the Empty-state drop target/recent-files list,
  and the Files/Tasks panes into the single `QWidget` the factory returns — every sibling
  workspace module (`results`, `resume_benchmark`, `new_benchmark`) has an equivalent root
  `_internal/view.py`, and this module follows that same real precedent.
- **Files-pane context menu — intentionally partial (design decision #5).** Only `Close`,
  `Close Others`, `Reveal in File Manager`, and `Reload from Disk` are wired. `Save`, `Save As`,
  and `Show in Task Files Panel` are omitted **entirely** from the menu (not shown disabled)
  because they need collaborators/behaviour this story does not have
  (`validation_cascade`/`YamlFormatter.save`, and a cross-workspace New-Benchmark handoff,
  respectively) and the no-placeholder-UI rule (`pyside6-spec-ui`) forbids a disabled control
  with no path forward. `Close`/`Close Others`/`Reload from Disk` are further restricted to
  clean (non-dirty) files this story, since the dirty-close/-reload confirmation dialogs are
  STORY-069's scope; a dirty file's `Close`/`Reload from Disk` menu item renders disabled with
  an explanatory tooltip (the permitted "transiently disabled" exception, not a placeholder).
  `Close Others` silently skips any dirty buffer rather than raising a dialog for it.
- **Toolbar Save / Save All / View YAML** render as fixed, permanent, disabled toolbar members
  with an explanatory tooltip (design decision #6) — they are not omitted, since they are fixed
  members of the spec's toolbar row (§3.2), unlike the context-menu items above which are not
  fixed/permanent and are cut outright.
- **Reorder** is offered via Move Up / Move Down footer buttons only; mouse drag-to-reorder
  (`QAbstractItemView.InternalMove`) is deferred to keep this story's scope bounded — it is not
  cited by any of this story's ACs, only by the "In scope" bullet's general "reorder" wording.
- **Remove Task** confirmation uses a plain `QMessageBox.question(...)` (a Qt built-in, not a
  bespoke dialog module) since it is cheap, destructive, and not explicitly named in the
  out-of-scope dialog list (leave/quit/close/reload/in-use/save-failure).
- **New File** writes the seed-scaffold YAML text via `FileSystemActions.write_text_file`, not
  `YamlFormatter.save` — per design decision #2, `.save()` stays completely unused until
  STORY-069; `.load_document()` is then used to open the freshly written file as a buffer, same
  as any other Open.
- **No `ThemeManager` collaborator.** `TaskEditorCollaborators` (design decision #2) does not
  carry a `theme_manager`/`platform_kind` pair the way `ResumeBenchmarkCollaborators` and
  `ResultCollaborators` do. Files-pane/Tasks-pane badges are rendered as short text glyphs
  (`[clean]`/`[dirty]`/`[warning]`/`[error]`/`[reload pending]`) with no colour channel at all,
  which is spec-conformant on its own (`08-L_ui_standardization.md`: status colour is never the
  *sole* channel) and needs no theme dependency.
- **`recent_files` is not a `TaskEditorViewModel` field.** The spec's
  `implementation_structure.md` §4 struct (declared verbatim in `models.py`) has no
  `recent_files` field, and the recent-files list is explicitly session view state, not
  persisted settings. It is pushed to the view via a dedicated
  `TaskEditorController._push_recent_files()` → `TaskEditorView.set_recent_files(...)` call,
  mirroring `ResumeBenchmarkController._push_resume_button_state()`'s identical
  push-outside-the-viewmodel precedent.
- **STORY-069 must additionally**: widen `TaskEditorCollaborators`/the factory with
  `validation_cascade`; put `YamlFormatter.save` to use for the actual Save/Save All actions;
  populate `field_rows`/`preview_shown`/`preview_text`; add the `Save`/`Save As`/
  `Show in Task Files Panel` context-menu items; wire the leave/quit/close/reload/in-use/
  save-failure confirmation dialogs; enable the toolbar's `Save`/`Save All`/`View YAML` actions
  (removing their disabled state and tooltip); and feed `TaskEditorController.stage_field_edit`
  from the real Field-editor pane's focused-field state.
- **Badge-vs-dirty-marker design ambiguity (needs a human/design decision before STORY-069).**
  The spec is internally ambiguous between showing one collapsed 5-state badge per file (what
  this story implements, via precedence: reload-pending > error/warning > dirty > clean) versus
  showing the validation badge and the dirty marker as two simultaneous orthogonal indicators
  (the same pattern already used for the `[in use]` marker added in this story's fix pass). A
  file that is both dirty and warning/error currently only shows `[warning]`/`[error]`, losing
  the unsaved-edits signal. This should be resolved with an explicit human/design decision
  before STORY-069 builds on top of the current single-badge precedence scheme.
- **Stale recent-file click has no error handling (uncovered by any AC in this story).**
  `on_recent_file_clicked` → `_open_path` currently has no failure path if the recent file's
  path no longer exists on disk (e.g. deleted since it was opened). `09_Task_Editor/ description.md`§2.3 specifies this should surface an open-failure toast and remove the stale
  entry from the recent-files list. This should be picked up by STORY-069 or a dedicated
  follow-up.
