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

## Notes

- **Export Summary/Details (CSV/Markdown) functional wiring is deferred to a not-yet-created
  follow-up story (STORY-056b).** `ResumeGateway` (08-E §7b.3) has no `serialize_table`-shaped
  method, unlike its sibling `ResultGateway` (`serialize_table(run_id, table, fmt) -> str`), and
  `ui/resume_benchmark/` is not permitted to import `backend/csv_export` directly. This pass
  implements exactly what AC-4 requires — the four Export Summary/Details context-menu actions
  exist and are gated "always enabled" — and wires their `.triggered` connection to a
  `_global_message` toast reading "Export not yet available"
  (`_internal/actions.py::export_table_not_yet_available`) rather than leaving them disconnected,
  per `08-L_ui_standardization.md`'s no-placeholder-UI rule. Landing real export content requires
  a `ResumeGateway.serialize_table` protocol amendment (mirroring `ResultGateway.serialize_table`)
  and a fold-back into `08_Cross_Cutting/08-E_interfaces_contracts.md` §7b.3 — this session did
  not attempt that amendment, consistent with the implementation plan's Escalation section.
- Two other design decisions were resolved during planning, not spec-mandated, and are baked
  into this implementation: (1) the Delete confirmation is an inline stock
  `QMessageBox.question(...)` (native OS chrome, no `setStyleSheet`) rather than a new themed
  `common_dialogs` factory — no prior confirmation-dialog pattern exists and no acceptance
  criterion tests one; (2) the `log_file_exists`/`log_file_path` gating boolean (AC-4's "Show
  run-log file" gate) is answered by extending `adapters/file_system_actions/protocols.py`'s
  `FileSystemActions` Protocol with two new methods, `run_log_exists(*, run_id, started_at)` and
  `run_log_path_str(*, run_id, started_at)`, both deriving the path via
  `backend.infra.run_log_path` — the real log-path construction lives in `backend/infra`, which
  `ui/*` cannot import directly, so `adapters/*` (which may import any `backend/*` package)
  supplies the derived boolean/path instead.

### Post-review gap-closure pass (spec-conformance review, 2026-07-19)

An independent spec-conformance review found the seven authored acceptance-criteria tests
passing but five clauses this story itself cites were under-covered. Fixed, in the review's
severity order:

1. **§3.3 — missing per-row pencil/⋯ buttons, missing sort caret, misleading caption.** Added
   `_internal/row_actions_delegate.py` (`RowActionsDelegate`, a `QStyledItemDelegate` painted
   over the Tasks column) providing hover-revealed pencil (`pencil_clicked`) and ⋯
   (`more_clicked`) icon glyphs — painted only for the currently-hovered row so the table stays
   virtualised (EC-RB-12), never one persistent widget per row. `ResumeBenchmarkView` tracks
   hover via `QTableView.entered` (`setMouseTracking(True)`) and clears it on viewport `Leave`
   via an installed event filter; `pencil_clicked`/`more_clicked` route to new controller
   methods `on_pencil_clicked`/`on_more_clicked`, the former reusing the existing
   `_on_rename_triggered` path, the latter reusing `on_context_menu_requested`. Added
   `_internal/theme_lookup.py::resolve_theme_tokens` (a small internal helper, not exported)
   so the delegate can resolve the `text.primary` icon colour through `ui/theme` with no colour
   literal. `RunTableModel.headerData` now appends a `▼`/`▲` caret to the active sort column's
   `DisplayRole` label (verified to flip on repeated `set_sort` calls) and optionally returns a
   `primary.base`-coloured `ForegroundRole` when an (optional, defaults to `None`) `ThemeManager`
   is wired — mirroring `ui/new_benchmark/_internal/task_files.py`'s established
   optional-`ThemeManager` fallback pattern so existing theme-less unit tests are unaffected.
   The caption now reads "Right-click a row, use the pencil to rename, or ⋯ for more actions."
   Tests: `tests/test_row_actions_delegate.py` (6 tests), `test_run_table_model.py ::test_header_caret_reflects_active_sort_column_and_direction`.
1. **§4.3 — Status column rendered as plain text, not a coloured badge.** Added
   `_internal/status_badge_delegate.py` (`StatusBadgeDelegate` + the extracted pure
   `resolve_status_badge_colors` helper) and wired it via `setItemDelegateForColumn(COL_STATUS, ...)`. It reuses `ui/shared`'s exact badge colour-role mapping via a new public
   `ui/shared.resolve_badge_color_roles(status: BadgeStatus) -> tuple[str, str]` function
   (extracted from `BadgeLabelWidget`'s private `_BASE_ROLE`/`_FILL_ROLE` dicts, now shared by
   both) resolved through `ui/theme.resolve_color` — no new colour literal, no `setStyleSheet`.
   `RunTableModel.data()` now also answers `Qt.ItemDataRole.UserRole` for `COL_STATUS` with
   `row.status_badge_status`, the delegate's paint-time input. Falls back to the base
   `QStyledItemDelegate.paint` when no `ThemeManager` is wired (same optional-collaborator
   pattern as gap 1). Tests: `tests/test_status_badge_delegate.py` (6 tests, table-driven over
   all four `status_badge_status` values against the same theme roles
   `ui/shared/tests/test_badge_label.py` asserts for `BadgeLabelWidget`).
1. **Selection dropped on every model reset (search/sort/rebuild).** `RunTableModel.set_rows`/
   `set_search_term`/`set_sort` all call `beginResetModel`/`endResetModel`, which clears Qt's
   own selection model — previously nothing re-applied the controller's tracked selection
   afterward. Added `ResumeBenchmarkController.current_selected_run_id()` (read accessor) and
   `ResumeBenchmarkView._on_model_reset` (connected to `table_model.modelReset`), which restores
   the QTableView's visual selection to the tracked run id's row when it is still present —
   wrapped in `selectionModel().blockSignals(True/False)` so the restoration never re-emits
   `selectionChanged`/`_run_id_changed`. When the row is no longer present, this is a no-op and
   the controller's pre-existing `_clear_selection_if_filtered_out` path (already covered by
   AC-2) fires as before. Test (mounted-view, real `make_resume_benchmark_widget`):
   `test_controller.py::test_selection_restored_across_sort_reset_with_view_mounted` — selects a
   row, fires a header `sectionClicked` (the exact signal a real header click emits), and asserts
   the same row is still selected with no `_run_id_changed(None)` emitted in between.
1. **Clone timestamp — verified `RunsStore.create_run` does NOT re-stamp.** Read
   `backend/persistence/runs/_internal/store_impl.py::_insert_run_header`: it binds
   `run.created_at`/`run.timestamp` verbatim into the `INSERT` (only `run_id` is discarded, via
   `cursor.lastrowid`) — **confirmed: the store does not re-stamp.** Fixed
   `clone_as_new_retry_run` to compute `cloned_at = datetime.now(UTC).isoformat()` once and use
   it for both `created_at` and `timestamp` on the new run (the same ISO-8601-UTC idiom
   `backend.infra.SystemClock.now_utc()` uses; `ui/resume_benchmark/` cannot import
   `backend.infra` directly per the layering table, and `ResumeGateway` carries no clock method,
   so this is the narrowest available fix, not a new time-source pattern). Tests:
   `test_clone_stamps_a_fresh_created_at_newer_than_the_source`,
   `test_clone_sorts_to_top_of_default_started_at_descending_table_order` (feeds the source +
   cloned run through the real `select_run_rows`/`RunTableModel` pipeline and asserts the clone
   is `visible_row(0)`).
1. **Clone result_id reuse — verified `ResultsStore.create_results` is autoincrement.** Read
   `backend/persistence/results/_internal/store_impl.py::_insert_result_header`: it never binds
   the incoming `result.result_id` into its `INSERT` column list — SQLite's
   `INTEGER PRIMARY KEY` always assigns a fresh id via `cursor.lastrowid`. **Confirmed: passing
   the source's `result_id` through unchanged (the existing `_clone_result`/
   `msgspec_replace_run_id` behaviour) is safe — no code change was needed.** Added a regression
   test using a new `_FakeAutoIncrementResumeGateway` (mimics the real store's id-reassignment
   behaviour) proving the clone's result ids are disjoint from the source's:
   `test_clone_result_ids_are_reassigned_by_an_autoincrement_store`.

Also converted `test_run_table_model.py::test_status_badge_per_run_status`'s in-body loop to
`@pytest.mark.parametrize` (its trailing `INCOMPLETE`-only resumability assertion was split out
into its own `test_incomplete_run_with_pending_result_is_resumable`, since a parametrized test
must not also carry a conditional assertion) per `testing.md`'s no-`if`/no-`for` rule.

`just check`, `just coverage-layers`, `just trace`, and `just trace-check` were all re-run.
`just trace-check` fails with a pre-existing backlog of ~34 dangling/untested `EC-` ids (none
of them `EC-RB-*`/`EC-PERSIST-*`) unrelated to this story or this pass — see the
`project_preexisting_gate_failures` note; `git status` confirms none of the files this pass
touched introduced a new dangling edge case.
