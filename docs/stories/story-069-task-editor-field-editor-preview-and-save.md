---
id: STORY-069
title: Build the Task Editor field editor, YAML preview, save/validation cascade, and confirmation dialogs
status: ready
spec_clauses:
  - 09_Task_Editor/description.md#35-field-editor-pane
  - 09_Task_Editor/description.md#36-yaml-preview-side-panel
  - 09_Task_Editor/description.md#37-leave-confirmation-and-quit-confirmation
  - 09_Task_Editor/description.md#38-new-file-seed-scaffold
  - 09_Task_Editor/description.md#4-validation-rules
  - 09_Task_Editor/implementation_structure.md#4-view-model-struct
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b7-taskeditorgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/task_editor/
acceptance_criteria:
  - STORY-069-AC-1
  - STORY-069-AC-2
  - STORY-069-AC-3
  - STORY-069-AC-4
  - STORY-069-AC-5
  - STORY-069-AC-6
edge_cases:
  - EC-WS-3
depends_on:
  - STORY-049
  - STORY-068
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-069 — Build the Task Editor field editor, YAML preview, save/validation cascade, and confirmation dialogs

## Goal

Complete the Task Editor: the structured per-field editor with its typed input controls, help
popovers, and inline validation strips; the read-only YAML preview panel driven by the YAML
Formatter with its Copy action; the validation-cascade integration that gates Save per file; the
atomic comment-preserving Save through the YAML Formatter (emitting `_task_file_changed`); and
the confirmation dialogs (leave, quit, close, reload, in-use-on-save, save-failure).

## In scope

- `_internal/field_editor.py` and `_internal/field_rows.py`: the scrollable Form, the Field Rows
  with the type-specific controls (identifier, short/long text, enum dropdown, boolean checkbox,
  chip input), the collapsible groups, the help popovers, the position counter, and the per-field
  validation strips.
- `_internal/yaml_preview.py`: the read-only YAML preview panel rendering the exact Save output
  from the YAML Formatter (debounced re-render), with the Copy YAML action and the preview-only
  note when the file has hard errors.
- The validation-cascade integration in `_internal/controller.py`: mapping the `ValidationReport`
  onto the per-row `validation_state` fields, the aggregate toolbar counts, and
  `ToolbarViewModel.save_enabled`; the New-file seed scaffold.
- The Save orchestration: delegate serialization and the atomic write to the YAML Formatter,
  update the view-model on completion, and emit `_task_file_changed`; Save All skipping files with
  hard errors.
- `_internal/dialogs.py`: the leave-confirmation, quit-confirmation, close-confirmation,
  reload-confirmation, in-use-on-save, and save-failure dialogs.

## Out of scope

- The workspace shell, toolbar, Files pane, Tasks pane, buffer model, and view-model — delivered
  by STORY-068, which this story builds on.
- The `ValidationCascade`, `TaskFileValidator`, and `YamlFormatter` implementations — consumed as
  Protocols; this story renders their output and delegates serialization.
- The per-field schema and rules (owned by `field_reference.md` and the YAML task format) — the
  editor renders help and validation from them, it does not redefine them.
- Wiring the concrete `TaskEditorGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `09_Task_Editor/description.md#35-field-editor-pane` — the Field Row anatomy, the per-field-kind
  input controls, the help popovers, the position counter, and the validation strips.
- `09_Task_Editor/description.md#36-yaml-preview-side-panel` — the read-only preview rendering the
  exact Save output, the debounced re-render, and the Copy YAML action.
- `09_Task_Editor/description.md#37-leave-confirmation-and-quit-confirmation` — the
  Save-All/Discard-All/Cancel dialog on a dirty leave or quit and the hard-error skip.
- `09_Task_Editor/description.md#38-new-file-seed-scaffold` — the seeded task and its initial
  hard-error flags.
- `09_Task_Editor/description.md#4-validation-rules` — the three-level cascade, the three
  severities, the Save-gating hard-error set, and the per-file Save gate.
- `09_Task_Editor/implementation_structure.md#4-view-model-struct` — the `FieldRowViewModel`,
  `ToolbarViewModel`, and validation-state fields the controller computes.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b7-taskeditorgateway` — the workspace settings
  the field editor and validation debounce read.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The controller never serializes, parses, or validates YAML itself — it delegates to the YAML
  Formatter, the Task File Loader, and the validation cascade respectively (D-R-06).
- The YAML preview is read-only by design; all editing is form-driven.
- Save is gated per file: a file with any hard error is not saveable; Save All saves only the
  saveable files. The YAML Formatter is the single writer of task files (atomic, comment-preserving).
- Field-level validation runs on the configured debounce, immediately on focus loss, and
  immediately on a chip add/remove.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-069-AC-1

For each field kind, the Field Row renders the specified input control:

| Field kind                                 | Control                                              |
| ------------------------------------------ | ---------------------------------------------------- |
| `task_id` (identifier)                     | single-line input with live in-file uniqueness check |
| long text (`question`, `golden_answer`, …) | auto-growing multi-line input                        |
| `difficulty` (closed enum)                 | dropdown of `Difficulty` members                     |
| `cosine_enabled` (boolean)                 | checkbox, default checked                            |
| `required_terms.*` (term lists)            | chip input with add/remove/paste-split               |

### STORY-069-AC-2

Given a task with an empty `task_id`, `question`, or `golden_answer`, when the validation cascade
runs, then that field carries a hard-error strip, the task and file badges aggregate to error,
and the file's Save is disabled.

### STORY-069-AC-3

Given a file with no hard error and at least one dirty file, when Save All runs, then it saves
every dirty file free of hard errors through the YAML Formatter and skips (leaving dirty) every
file that still has a hard error.

### STORY-069-AC-4

Given the active file is saved successfully, when the Save completes, then the file returns to
the clean/Loaded state and a `_task_file_changed` event carrying the saved path is emitted.

### STORY-069-AC-5

Given the user opens the YAML preview for a task that has a hard error, when the panel renders,
then it still shows the syntactically valid YAML the Formatter would produce and notes that Save
is disabled while the file has errors.

### STORY-069-AC-6

Given one or more dirty buffers, when the user switches to the Benchmark workspace or quits, then
the "Save changes to N file(s)?" dialog is shown with Save All / Discard All / Cancel, and Cancel
keeps the editor unchanged.

## Test plan

- STORY-069-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_field_rows.py`,
  `test_control_kind_per_field`. Wrapped in `structlog.testing.capture_logs()`; asserts no
  captured entry's `log_level` is in `{"error", "critical"}`.
- STORY-069-AC-2 — unit (`pytest-qt`, fake `ValidationCascade`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_controller.py`,
  `test_missing_required_field_disables_save`.
- STORY-069-AC-3 — unit (`pytest-qt`, fake `YamlFormatter`), same file,
  `test_save_all_skips_hard_error_files`.
- STORY-069-AC-4 — unit (`pytest-qt`), same file,
  `test_successful_save_emits_task_file_changed`.
- STORY-069-AC-5 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_yaml_preview.py`,
  `test_preview_renders_for_hard_error_file`. Covers EC-WS-3.
- STORY-069-AC-6 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/task_editor/_internal/tests/test_dialogs.py`,
  `test_dirty_leave_shows_save_choice_dialog`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-069.
- [ ] EC-WS-3 has a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the per-file-validation
  (Valid / Warnings / Errors), per-field-validation, and YAML-preview (Hidden / Shown) states
  of `09_Task_Editor/state_machine.md`.
- [ ] An architecture test confirms the controller never serializes/parses/validates YAML itself
  (delegating to the Protocols), depends only on `TaskEditorGateway` plus the declared
  helpers, and that the module references no `setStyleSheet`, embeds no colour literal, and
  imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/task_editor/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-069.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
