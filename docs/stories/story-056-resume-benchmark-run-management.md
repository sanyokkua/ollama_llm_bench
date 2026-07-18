---
id: STORY-056
title: Build the Resume Benchmark widget — run table, search, sort, and the clone/rename/delete/export/log actions
status: ready
spec_clauses:
  - 03_Resume_Benchmark_Widget/description.md#33-run-table
  - 03_Resume_Benchmark_Widget/description.md#35-context-menu
  - 03_Resume_Benchmark_Widget/description.md#36-clone-as-new-retry-run
  - 03_Resume_Benchmark_Widget/description.md#43-status-badge
  - 03_Resume_Benchmark_Widget/description.md#7-event-bus-integration
  - 07_Common_Dialogs/rename_run_dialog.md#5-validation-rules
  - 07_Common_Dialogs/rename_run_dialog.md#10-commit-effects
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/resume_benchmark/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-056-AC-1
  - STORY-056-AC-2
  - STORY-056-AC-3
  - STORY-056-AC-4
  - STORY-056-AC-5
  - STORY-056-AC-6
  - STORY-056-AC-7
edge_cases:
  - EC-PERSIST-2
depends_on:
  - STORY-049
  - STORY-051
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-056 — Build the Resume Benchmark widget — run table, search, sort, and the clone/rename/delete/export/log actions

## Goal

Deliver the run-catalog surface of the Resume tab: a virtualised, sortable, searchable table
of every persisted run with its status badge and completion fraction; row selection that emits
`_run_id_changed` to drive the centre and right panels; and the management context menu —
Clone as new retry run, Rename (with the Rename Run dialog), Delete, the Export
Summary/Details/Run-Analysis actions, and Show run-log file. The Resume/Retry flows are added
by STORY-057.

## In scope

- `ui/resume_benchmark/protocols.py`: the `ResumeGateway` Protocol declared locally with the
  exact method signatures of 08-E §7b.3.
- `ui/resume_benchmark/api.py`: `make_resume_benchmark_widget(...) -> QWidget`.
- `_internal/run_table_model.py`: the `QAbstractTableModel` over `RunRow` tuples (validated
  with `QAbstractItemModelTester`), the default `started_at`-descending sort, the persisted
  sort column/direction, and the case-insensitive name-or-mode search predicate.
- `_internal/context_menu.py`: the grouped right-click / ⋯ menu and per-item gating from the
  selected row's derived flags.
- `_internal/actions.py`: the Clone, Rename, Delete, Export (Summary/Details CSV+Markdown, Run
  Analysis Markdown), and Show-run-log actions, and the `_global_message` toasts on outcome.
- The controller subscriptions (`_run_list_changed`, `_run_renamed`, `_run_id_changed`,
  `_run_started`, terminal events, `_run_analysis_received`, `_task_file_changed`) and the
  selection-preserving reload.
- `ui/common_dialogs/` Rename Run dialog factory with its live validation (V-1..V-5) and
  Use-default path.

## Out of scope

- The Resume Run button behaviour, the Resume Summary dialog, and the Retry Selection dialog —
  owned by STORY-057.
- The concrete `RunsStore` / `ResultsStore` / `TasksStore` / `NativePickers` /
  `FileSystemActions` — consumed as Protocols behind the gateway or as OS-adapter helpers.
- Wiring the concrete `ResumeGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `03_Resume_Benchmark_Widget/description.md#33-run-table` — the five columns, single-row
  selection emitting `_run_id_changed`, the sort caret rules, and the inline pencil / ⋯ buttons.
- `03_Resume_Benchmark_Widget/description.md#35-context-menu` — the grouped menu, its item set,
  and the per-item enablement gates with disabled-reason tooltips.
- `03_Resume_Benchmark_Widget/description.md#36-clone-as-new-retry-run` — the atomic
  clone-as-new-retry-run algorithm across the three stores.
- `03_Resume_Benchmark_Widget/description.md#43-status-badge` — the `RunStatus`-to-badge
  colour-and-label mapping.
- `03_Resume_Benchmark_Widget/description.md#7-event-bus-integration` — the subscribed events
  and the emitted `_run_id_changed` / `_global_message`.
- `07_Common_Dialogs/rename_run_dialog.md#5-validation-rules` — the V-1..V-5 live validation and
  the empty-input default-intent handling.
- `07_Common_Dialogs/rename_run_dialog.md#10-commit-effects` — the `rename_run` commit and the
  emitted `_run_renamed` / `_run_list_changed`.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway` — the gateway surface this
  widget's `protocols.py` declares.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The controller depends only on its `ResumeGateway` Protocol plus `EventBus`, `NativePickers`,
  and `FileSystemActions`; it holds no `RunsStore`/`ResultsStore`/`TasksStore` directly (D-R-06).
- The run table is virtualised so a large catalog stays responsive; every reload preserves the
  current selection by `run_id`.
- Exports are written verbatim without a redaction step (own-machine data); the export path
  imports no redaction function.
- `RunRow` carries pre-derived gating booleans (`is_resumable`, `is_executing`, `has_analysis`,
  `log_file_exists`); the view and menu never re-derive gating.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-056-AC-1

Given a populated run list, when the widget renders the table, then rows default to
`started_at` descending (newest first), and typing a term filters the visible rows to those
whose run name OR mode label contains the term, case-insensitively.

### STORY-056-AC-2

Given a row is selected, when the selection changes, then the widget emits `_run_id_changed`
carrying the selected run's `run_id`; and when the selected row is filtered out by a search
change, then the selection clears and `_run_id_changed` reports no selection.

### STORY-056-AC-3

For each `RunStatus`, the Status column renders the specified badge:

| RunStatus  | Badge label | Tone    |
| ---------- | ----------- | ------- |
| COMPLETED  | Done        | success |
| STOPPED    | Stopped     | warning |
| FAILED     | Failed      | error   |
| INCOMPLETE | Pending     | muted   |

### STORY-056-AC-4

For each context-menu item, its enabled state matches the selected row's gating:

| Menu item                      | Enabled when                 |
| ------------------------------ | ---------------------------- |
| Clone as new retry run         | row not executing            |
| Rename…                        | row not executing            |
| Delete                         | row not executing            |
| Export Summary / Details       | always                       |
| Export Run Analysis (Markdown) | run `run_analysis` non-empty |
| Show run-log file              | run log file exists          |

### STORY-056-AC-5

Given a source run, when the user chooses Clone as new retry run, then a new run is created
that copies the source mode and all three frozen snapshots, carries a `(retry)`-suffixed name,
clears `run_analysis`, sets status INCOMPLETE, copies each COMPLETED result as-is and every
other result as PENDING, and the new run is selected at the top of the table.

### STORY-056-AC-6

Given a run row, when the user renames it through the Rename Run dialog to a valid unique name,
then `ResumeGateway.rename_run(run_id, name)` is called with the trimmed name; and when the
user chooses Use default, then `rename_run` is called with `None`.

### STORY-056-AC-7

For each of this story's factory functions, constructing it with a fake `ResumeGateway` and
mounting it under `qtbot`, then showing it (`qtbot.addWidget(...)`, `.show()`, one
`qtbot.wait(0)`/event-loop pump), raises no exception, reports `isVisible()`, and captures no
`error`/`critical`-level `structlog` record — verified by wrapping construction+show in
`structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`:

| Factory function               | Owning module          |
| ------------------------------ | ---------------------- |
| `make_resume_benchmark_widget` | `ui/resume_benchmark/` |
| `make_rename_run_dialog`       | `ui/common_dialogs/`   |

## Test plan

- STORY-056-AC-1 — unit, colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_run_table_model.py`,
  `test_default_sort_and_name_or_mode_search`.
- STORY-056-AC-2 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller.py`,
  `test_selection_emits_run_id_changed_and_clears_on_filter_out`.
- STORY-056-AC-3 — table-driven unit, `test_run_table_model.py`,
  `test_status_badge_per_run_status`. Covers EC-PERSIST-2 (INCOMPLETE renders as resumable).
- STORY-056-AC-4 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_context_menu_gating.py`,
  `test_menu_item_gating_per_row_state`.
- STORY-056-AC-5 — unit (`pytest-qt`, fake `ResumeGateway`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py`,
  `test_clone_creates_new_retry_run`.
- STORY-056-AC-6 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_rename_run_dialog.py`,
  `test_rename_commits_name_or_none`.
- STORY-056-AC-7 — unit (`pytest-qt`, fake `ResumeGateway`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_controller.py`,
  `test_resume_widget_constructs_and_shows_with_no_error_logs`, and colocated
  `src/ollama_llm_bench/ui/common_dialogs/tests/test_rename_run_dialog.py`,
  `test_rename_dialog_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-056.
- [ ] EC-PERSIST-2 has a passing test (an INCOMPLETE run renders with the Pending badge and is
  offered as resumable).
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises every state in
  `03_Resume_Benchmark_Widget/state_machine.md`; the run-table model passes
  `QAbstractItemModelTester`.
- [ ] An architecture test confirms the controller depends only on `ResumeGateway` (plus the
  OS-adapter helpers and Event Bus), that the export path imports no redaction function, and
  that the modules reference no `setStyleSheet`, embed no colour literal, and import no
  `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/resume_benchmark/` and
  `ui/common_dialogs/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-056.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
