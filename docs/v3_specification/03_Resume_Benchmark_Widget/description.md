# Resume Benchmark Widget — Description

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `03_Resume_Benchmark_Widget/state_machine.md`, `03_Resume_Benchmark_Widget/flow_diagram.md`, `03_Resume_Benchmark_Widget/implementation_structure.md`, `01_Main_Window/description.md`, `04_Progress_Widget/description.md`, `05_Result_Widget/description.md`, `07_Common_Dialogs/`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-H_app_modes.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `10_Domain_and_Data/05_EXPORT_FORMATS.md`, `10_Domain_and_Data/07_FILE_LAYOUT.md`, `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`

The Resume Benchmark widget is the **Resume** tab of the Benchmark workspace left panel. It is the single source of truth for run management: it lists every past run in a table and, through its footer and a right-click context menu, lets the user resume an unfinished run, retry selected failed tasks, clone a run as a fresh retry run, rename a run, delete a run, export a run's data, and open a run's log file. This document is the primary specification for the widget — its layout, the behaviour of every element, its validation rules, its persistence, its event-bus integration, its service dependencies, its edge cases, and a flat inventory of every callable behaviour.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Behaviour per element
4. Validation rules
5. State transitions (summary)
6. Persistence
7. Event bus integration
8. Service dependencies
9. Edge cases
10. Function inventory

---

## 1. Role and ownership

The Resume Benchmark widget owns the **catalog of runs and their lifecycle actions**. It is responsible for:

- Presenting every persisted `BenchmarkRun` as a sortable, searchable table.
- Letting the user select one run; selecting a run drives the centre Progress panel and the right Result panel into a read-only view of that run.
- Resuming an unfinished run, with a pre-resume environment validation and a task picker.
- Retrying a chosen subset of a run's failed tasks.
- Cloning a run into a new retry run that preserves the original for comparison.
- Renaming a run.
- Deleting a run.
- Exporting a run's Summary, Details, and consolidated Run Analysis.
- Revealing a run's log file in the operating-system file manager.

It is **not** responsible for:

- Creating a new run — that is the New Benchmark widget (`02_New_Benchmark_Widget/`).
- Executing or controlling a live run — that is the Progress widget (`04_Progress_Widget/`) and `BenchmarkFlowApi`.
- Rendering a run's results, charts, or analysis in detail — that is the Result widget (`05_Result_Widget/`).
- Editing settings, providers, or task files.

The Resume Benchmark widget is the **only** surface that can rename or delete a run that is not currently executing. The Result widget exposes neither action. The Progress widget exposes rename only while a run is actively executing (see `04_Progress_Widget/description.md`). Resume, Retry, Clone, Rename, Delete, and Export are all forbidden while the selected run is the run currently executing — the application-modes contract (`08_Cross_Cutting/08-H_app_modes.md`) disables them and the widget reflects that.

---

## 2. Layout

The widget is a single vertical panel. The mockup is `mockup.html`.

```
+-----------------------------------------------------------------+
| [ Search runs by name or mode............ ]        [ Refresh ]  |  search row
+-----------------------------------------------------------------+
| Run name              | Mode          | Started     | Status   | Tasks  |
|-----------------------|---------------|-------------|----------|--------|
| Graded Benchmark 05-16    | Graded Benchmark      | 2026-05-16  | Stopped  | 60/80  |  run table
| System Run 05-15      | Synthetic Benchmark| 2026-05-15  | Done     | 120/120|
| Task Benchmark Pass 05-14      | Task Benchmark             | 2026-05-14  | Failed   | 12/30  |
| ...                   |               |             |          |        |
+-----------------------------------------------------------------+
|                                                    [ Resume Run ] |  footer
+-----------------------------------------------------------------+
```

| Region | Purpose |
|---|---|
| Search row | A single-line text input that filters the run table, and an inline small (`sm`) Refresh button to its right. |
| Run table | A read-only, single-selection table of every persisted run. The full management surface is the right-click context menu. |
| Footer | The primary action only: Resume Run (SPEC-120 — the redundant footer Refresh was removed; Refresh lives once, inline in the search row). |

**One Refresh control (SPEC-120).** Refresh lives in **one** place: the small (`sm`) inline button in the search row, where it is at hand while the user filters. The previously-redundant footer Refresh was removed so the footer carries only the primary Resume Run action. Refresh is enabled at all times, including in the empty state.

The footer carries only Resume Run so that the act of *choosing a different run in the table* stays visually and conceptually separate from the act of *operating on the chosen run* (Refresh is the inline search-row button). Every operation that acts within a run — retry, clone, rename, delete, export, show log — lives in the context menu.

When the run table is empty, the table area is replaced by an empty state (Section 4.4).

---

## 3. Behaviour per element

### 3.1 Search input

A single-line text input. As the user types, the run table is filtered to rows whose run name **or** mode display label contains the entered text, case-insensitively. Filtering is applied on a 150 ms debounce so that fast typing does not re-filter on every keystroke. Clearing the input restores the full list. The filter is a view-only predicate; it never changes the underlying run set. Selection is preserved across a filter change when the selected row still matches; when the selected row is filtered out, selection clears and the centre and right panels return to their no-selection state.

### 3.2 Refresh button

There is one Refresh button — the inline `sm` button in the search row (Section 2). It is enabled at all times. Clicking it re-reads the run list through `RunsStore.list_runs()`, rebuilds the table, and re-applies the current search filter and sort. Refresh preserves the current selection by `run_id` when that run still exists. Refresh exists as an explicit affordance even though the widget also updates live (Section 7); it is the recovery action if the user ever suspects the view is stale.

### 3.3 Run table

A table view bound to the run list. Five columns:

| Column | Source | Notes |
|---|---|---|
| Run name | The run's effective name — the user-set name if present, otherwise the generated name. | Sortable. |
| Mode | The display label for `BenchmarkRun.run_mode` — *Synthetic Benchmark*, *Task Benchmark*, or *Graded Benchmark*. | Sortable. |
| Started | `BenchmarkRun.started_at` formatted `YYYY-MM-DD HH:MM` in local time. | Default sort key, descending — newest run first. |
| Status | `BenchmarkRun.status` rendered as a coloured status badge (Section 4.3). | Sortable. |
| Tasks | The fraction *completed task count / total task count*, derived from the run's result rows. | Sortable by completion ratio. |

Behaviour:

- **Single-row selection.** Exactly zero or one row is selected at a time.
- **Selecting a row** emits `_run_id_changed` (Section 7), which drives the centre Progress panel and the right Result panel into a read-only post-run view of that run. Selecting the row does **not** start, resume, or modify anything.
- **Double-clicking a resumable row** opens the Resume Summary dialog — the same action as the Resume Run footer button. Double-clicking a non-resumable row does nothing.
- **Right-clicking a row** selects that row and opens the context menu (Section 3.5).
- **Sorting** by clicking a column header re-orders rows; the chosen sort column and direction persist (Section 6). The **active sort column displays a direction caret** in its header — `▲` for ascending, `▼` for descending — rendered in the `primary` tone; the other column headers carry no caret. The default state shows `▼` on the **Started** column (newest first). Clicking the already-active column header toggles its direction and flips the caret; clicking a different column makes it the active sort column with a default direction and moves the caret to it. The caret is a textual indicator paired with the header label, so direction is never conveyed by position alone.
- Each row carries an inline pencil Icon Button, revealed on hover, that opens the Rename Run dialog for that row — an inline equivalent to the context menu's Rename item.
- Each row also carries a **⋯ (more actions) Icon Button**, revealed on hover, that opens the **same context menu** as a right-click (Section 3.5) — a visible, discoverable entry point so mouse-only users need not guess that right-click exists (SPEC-078). It duplicates no action; it is just a second way to open the one menu. A muted caption under the table reads **"Right-click a row or use ⋯ for actions."**

### 3.4 Footer buttons

| Button | Enabled when | Action |
|---|---|---|
| Refresh | Always. | Same as Section 3.2. |
| Resume Run | A row is selected, that row is **resumable** (Section 4.1), and that row is not the run currently executing. | Opens the Resume Summary dialog (`07_Common_Dialogs/`). |

Resume Run is the primary button of the widget. When it is disabled, its tooltip states the reason — "Select a run to resume", "This run is fully completed — nothing to resume", or "This run is currently running".

### 3.5 Context menu

Right-clicking a run row selects it and opens a context menu. The menu is the full run-management surface, grouped by purpose. Items that do not apply to the selected run are disabled, with a tooltip stating why.

The menu renders a literal uppercase sub-heading above each group, in the order shown: **"Resume"**, **"Naming"**, **"Export"**, **"File"**. The destructive group has **no** visible heading — the **Delete** item is rendered alone below the final separator, styled in the `error` (red) tone. The displayed heading strings are exactly those four; "Destructive" is the internal name of the group, not a rendered label.

| Group | Item | Enabled when | Action |
|---|---|---|---|
| Resume | Resume Run | Selected row is resumable and not executing. | Opens the Resume Summary dialog — same as the footer button. |
| Resume | Retry selected tasks… | Selected row has at least one resumable result and is not executing. | Opens the Retry Selection dialog (`07_Common_Dialogs/`). |
| Resume | Clone as new retry run | Selected row is not executing. | Clones the run (Section 3.6). |
| Naming | Rename… | Selected row is not executing. | Opens the Rename Run dialog (`07_Common_Dialogs/`). |
| Export | Export Summary (CSV) | Always. | Exports the per-model Summary table as CSV. |
| Export | Export Summary (Markdown) | Always. | Exports the per-model Summary table as Markdown. |
| Export | Export Details (CSV) | Always. | Exports the per-result Details table as CSV. |
| Export | Export Details (Markdown) | Always. | Exports the per-result Details table as Markdown. |
| Export | Export Run Analysis (Markdown) | The run's `run_analysis` field is non-empty. | Exports the consolidated run-analysis narrative as Markdown. |
| File | Show run-log file | The run's log file exists on disk. | Reveals `<app-data>/logs/run/run_<run_id>_<started_at>.log` in the OS file manager. |
| Destructive | Delete | Selected row is not executing. | Opens the Delete confirmation dialog, then deletes the run. |

The menu groups are separated by separator lines, in the order shown: Resume, Naming, Export, File, Destructive. Destructive (Delete) is last and visually separated.

The menu item label for the run-analysis export is rendered verbatim as **"Export Run Analysis (Markdown)"**. When the selected run's `run_analysis` field is empty the item is disabled, and — per `08_Cross_Cutting/08-L_ui_standardization.md` §10, which requires every disabled control to explain itself — it carries the hover tooltip **"No analysis for this run"**. (This is the same string used by the EC-RB-8 toast for the race where the analysis is cleared between the menu opening and the click.) Every other disabled menu item likewise carries the matching disabled-reason tooltip from Section 3.4 / Section 4.2.

Export filenames follow the canonical pattern fixed in `10_Domain_and_Data/05_EXPORT_FORMATS.md`: `<effective_run_name>_<kind>.<ext>`, where `kind` is `Summary`, `Details`, or `RunAnalysis`. Every export passes its content through the redaction egress functions before writing — no raw provider secret reaches a file. Export content shapes — column order, escaping, encoding, the Markdown metadata header — are defined authoritatively in `10_Domain_and_Data/05_EXPORT_FORMATS.md`; this widget never redefines them.

### 3.6 Clone as new retry run

Clone creates a new run from the selected run, intended for re-running the failed work while keeping the original for comparison:

1. Read the source run, its frozen task / model / provider / settings snapshots, and its results.
2. Build a new `BenchmarkRun` that copies the source's mode and all three frozen snapshots verbatim, sets a fresh name derived from the source name with a `(retry)` suffix, clears `run_analysis`, and sets `status = INCOMPLETE`.
3. For each source result: a result that ended in `COMPLETED` is copied as-is into the clone; every other result is created in `PENDING` with all error and in-flight fields cleared.
4. Persist the new run, its frozen tasks, and its results through `RunsStore.create_run`, `TasksStore.create_tasks`, and `ResultsStore.create_results` in one transaction (the use case shares one connection across the three stores so the clone is atomic).
5. The new run appears at the top of the table (it is the newest run); the widget selects it.

Clone reuses the source's snapshot exactly — the clone is reproducible against the same providers, models, and settings the original used. The user resumes the clone like any other unfinished run.

### 3.7 Selecting a run drives the centre and right panels

When the user selects a row, the widget emits `_run_id_changed`. As a consequence:

1. The centre Progress panel switches to its read-only post-run view, showing the selected run's final progress counters and log.
2. The right Result panel auto-selects the same run in its run dropdown and renders that run's results, charts, and analysis.
3. The user may still switch to the New Benchmark tab and start an unrelated new run; doing so does not change this widget's selection.

When a *new* run is created elsewhere, the new run is inserted at the top of this widget's table, but the widget's current selection does **not** jump to it — the user keeps reviewing whatever run they had selected. (The Result widget's run dropdown does auto-jump to the new run; see `05_Result_Widget/description.md`.)

---

## 4. Validation rules

### 4.1 Resumable run

A run is **resumable** when both hold:

- `BenchmarkRun.status` is one of the resumable persisted statuses — `INCOMPLETE`, `STOPPED`, or `FAILED`; and
- the run has at least one **resumable result** — a result whose `ResultStatus` is `PENDING`, any of the non-terminal pipeline-position states (`RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`), or one of the five retryable terminal-failure states (`FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`).

A run whose status is `COMPLETED` is **not** resumable: the Resume Run button and the Resume Run menu item are disabled for it. A `COMPLETED` result (verdict `PASS` or `FAIL`) is never automatically resumable — it is not a failure — but the user may still re-run individual `COMPLETED` results by explicitly checking them in the Retry Selection dialog.

The five terminal-failure states are retryable; the `COMPLETED` terminal state is not. There is no `TASK_CHECK_FAILED`-style "validation failed but not retryable" state: a graded result that did not pass ends in `COMPLETED` with verdict `FAIL`, which is a finished result, not an error.

### 4.2 Action gating

| Action | Gate |
|---|---|
| Resume Run | Selected row resumable (§4.1) and not executing. |
| Retry selected tasks… | Selected row has ≥ 1 resumable result and not executing. |
| Clone as new retry run | Selected row not executing. |
| Rename… | Selected row not executing. |
| Delete | Selected row not executing. |
| Export Summary / Details | Always available; works for any persisted run. |
| Export Run Analysis | `BenchmarkRun.run_analysis` is non-empty. |
| Show run-log file | The run's log file exists on disk. |

"Executing" means the selected run is the one currently owned by `BenchmarkFlowApi` (`BenchmarkFlowApi.is_running()` and `current_run().run_id` equals the selected run id). The application-modes contract (`08_Cross_Cutting/08-H_app_modes.md`) is the binding source of these gates; the widget mirrors it.

### 4.3 Status badge

The Status column renders `BenchmarkRun.status` as a coloured badge:

| `RunStatus` | Badge colour | Badge label |
|---|---|---|
| `COMPLETED` | Success (green) | Done |
| `STOPPED` | Warning (amber) | Stopped |
| `FAILED` | Error (red) | Failed |
| `INCOMPLETE` | Muted (grey) | Pending |

The transient `RUNNING` and `PAUSED` states are not persisted statuses and never appear in this table; while a run executes it shows the badge of its persisted status (`INCOMPLETE`), and the live run state is reflected by the Progress widget instead.

### 4.4 Empty state

When `RunsStore.list_runs()` returns an empty tuple, the table area is replaced by an empty-state message:

> No runs yet. Switch to the New Benchmark tab to start your first run.

The search input and the Refresh button stay visible and enabled; the Resume Run footer button is disabled.

---

## 5. State transitions (summary)

The widget moves between an **Empty** state (no runs), a **Listing / no-selection** state (runs present, none selected), and a **Row-selected** state. A selected row is further classified **Resumable** or **Terminal** (fully completed). From a selected row the user opens one of the modal dialogs — Resume Summary, Retry Selection, Rename Run, Delete confirmation — each of which returns the widget to the selected-row state on cancel, or, for Resume and Retry, hands off to the pipeline. The complete diagram, with every transition trigger, is in `state_machine.md`.

---

## 6. Persistence

| State | Stored where | Lifetime |
|---|---|---|
| The run catalog itself | SQLite `benchmark_runs` and child tables, via `RunsStore`; result rows via `ResultsStore`; frozen task rows via `TasksStore`. | Durable. |
| Sort column and sort direction | UI preferences (settings store). | Survives close / reopen. |
| Search text | In-memory only. | Cleared on app restart. |
| Current row selection | In-memory only; mirrored to the run-selection store as the selected run id. | Cleared on app restart; not restored. |

The widget itself never writes run data except through `RunsStore`, `ResultsStore`, `TasksStore`, and `BenchmarkFlowApi`. On reopen the table is rebuilt from `RunsStore.list_runs()`, the saved sort is re-applied, the search box is empty, and no row is selected.

---

## 7. Event bus integration

Event names and payload types are defined authoritatively in `08_Cross_Cutting/08-J_event_bus_catalog.md`; this widget references them and never redefines them. Every subscription is owner-bound to the widget, so the subscription is torn down with the widget and never fires on a deleted Qt object.

### Events subscribed

| Event | Payload | Effect on the widget |
|---|---|---|
| `_run_list_changed` | `RunListChangedEvent` | A run was created, deleted, or cloned. Rebuild the table from `RunsStore.list_runs()`, re-apply the search filter and sort, and preserve the current selection by `run_id` when that run still exists. |
| `_run_renamed` | `RunRenamedEvent` | Update the affected row's Run name cell in place without rebuilding the table. |
| `_run_id_changed` | `RunIdChangedEvent` | If the selected run changed elsewhere (for example a new run started), sync the table selection to match. |
| `_run_started` | `RunStartedEvent` | Re-evaluate action gating for the affected row — it is now executing, so Resume / Retry / Clone / Rename / Delete are disabled for it. |
| `_run_finished` / `_run_stopped` / `_run_failed` | `RunFinishedEvent` / `RunStoppedEvent` / `RunFailedEvent` | The run reached a terminal persisted status; refresh that row's Status badge and Tasks fraction and re-evaluate its action gating. |
| `_run_analysis_received` | `RunAnalysisReceivedEvent` | The run's consolidated analysis is now available; enable the Export Run Analysis menu item for that run. |
| `_task_file_changed` | `TaskFileChangedEvent` | A YAML task file was saved; refresh the rows for any run whose snapshot referenced that file path so the Tasks count stays consistent. |

### Events emitted

| Event | Payload | When |
|---|---|---|
| `_run_id_changed` | `RunIdChangedEvent` | The user selects a different row, or the selection clears. |
| `_global_message` | `GlobalMessageEvent` | A user-facing outcome must be shown as a status-bar toast — "Exported", "No analysis for this run", "This run is fully completed — nothing to resume", a refused resume, or an export / file-open failure. |

Run-list mutations (clone, delete) are performed through the persistence stores (`RunsStore`, `TasksStore`, `ResultsStore`) and the rename / delete use cases; the resulting `_run_list_changed` and `_run_renamed` events are emitted by those use cases, not by this widget directly, and the widget then reacts to them like any other subscriber.

---

## 8. Service dependencies

The widget's controller is constructed with the following dependencies, all passed as plain keyword arguments by the composition root. Every name below is a Protocol or function group defined in `08_Cross_Cutting/08-E_interfaces_contracts.md`.

| Dependency | Protocol / group | Used for |
|---|---|---|
| Runs Store | `RunsStore` | `list_runs`, `get_run`, `create_run`, `delete_run`, `rename_run` (table population, clone-target creation, delete, rename). |
| Results Store | `ResultsStore` | `list_results`, `list_resumable_results`, `reset_results`, `create_results` (clone, retry-row reset, results read for the resume / clone use cases). |
| Tasks Store | `TasksStore` | `list_tasks`, `create_tasks` (read the source run's frozen task snapshot for clone; copy it verbatim into the clone). |
| Benchmark Flow API | `BenchmarkFlowApi` | `resume(run_id)` — start the pipeline on a resumed or retried run; `is_running` / `current_run` — determine the executing run for action gating. |
| Readiness Service | `ReadinessService` | Refresh the readiness snapshot immediately before the Run Drift Detector runs (pre-resume environment validation). |
| Event Bus | `EventBus` | Subscribe to and emit the events in Section 7. |
| File-system actions | `FileSystemActions` | `open_in_file_manager` to reveal the run-log file in the OS file manager. |
| Native pickers | `NativePickers` | `save_file` to choose the export destination for the run-export action. |
| Redaction module | `redact` (used only at the provider adapter boundary; the `app.*` log uses `redact_for_log`) | Not consumed by this widget's export path. Exports are written verbatim per `10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1. |
| Settings Service | `SettingsService` | Persist and restore the sort column and direction (Section 6). |

The Run Drift Detector (`11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`) is invoked as part of the Resume use case while the Resume Summary dialog is being assembled; it is a synchronous, read-only algorithm and is not a constructor dependency of this widget.

---

## 9. Edge cases

| ID | Situation | Handling |
|---|---|---|
| EC-RB-1 | The user clicks Resume Run while the selected run is the one currently executing. | The button and menu item are disabled by the action-gating contract; the disabled tooltip states "This run is currently running". |
| EC-RB-2 | Resume of a previously `STOPPED` run. | Allowed. The Resume Summary dialog opens, the drift detector runs, and `pending` plus retryable-failure results are pre-checked in the task picker. |
| EC-RB-3 | Resume of a `FAILED` run. | Allowed. Same flow as EC-RB-2; the dialog warns if the fatal cause is environmental drift. |
| EC-RB-4 | Resume of a run whose frozen configuration is no longer satisfiable by the environment — a provider removed/disabled/unreachable, a frozen model no longer served, the frozen API-key environment variable unset, or the frozen embedding pair unavailable. | The Run Drift Detector (DD-57) produces `DriftWarning` items; the Resume Summary dialog surfaces them. A `BLOCKING` warning gates Resume behind an explicit "Resume anyway" acknowledgement; a `WARNING` is informational. Configuration *differences* (live settings, live embedding selection) are not drift — the run resumes on its frozen snapshot. See `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md`. |
| EC-RB-5 | Resume of a run whose provider's api key names an environment variable that is no longer set. | The readiness probe reports the provider as `MISSING_ENV`; the drift detector emits a `BLOCKING` `PROVIDER_NOW_UNREACHABLE` warning; the Resume Summary dialog blocks an unacknowledged resume and offers Fix in Settings. |
| EC-RB-6 | A crash left a run mid-execution; on the next launch the crash-recovery sweep reset its in-flight results to `PENDING` and the run shows as `INCOMPLETE`. | The run appears in the table as `INCOMPLETE` (Pending badge) and is resumable like any other unfinished run. |
| EC-RB-7 | The selected run is fully `COMPLETED`. | Resume Run and Retry are disabled; Clone, Rename, Delete, Export, and Show run-log file remain available. The user may still re-run individual `COMPLETED` results from the Retry Selection dialog by explicitly checking them. |
| EC-RB-8 | The user picks Export Run Analysis on a run with no analysis. | The menu item is disabled. If the analysis was cleared between the menu opening and the click, the export emits a `_global_message` toast "No analysis for this run" and writes nothing. |
| EC-RB-9 | Show run-log file is chosen but the log file no longer exists on disk. | The menu item is disabled when the file is absent; if the file was deleted after the menu opened, the OS Adapter call fails and a `_global_message` toast "Run log file not found" is shown. |
| EC-RB-10 | An export's target path is unwritable (permissions, full disk). | The write fails; a `_global_message` toast reports the failure; no partial file is left (the writer writes to a temporary file and renames atomically). |
| EC-RB-11 | A run is deleted while it is the run shown in the centre and right panels. | The Delete confirmation completes, the row is removed on `_run_list_changed`, the selection clears, and the centre and right panels return to their no-selection state. |
| EC-RB-12 | The run table holds many runs (hundreds). | The table view is virtualised — only visible rows are realised — so population stays responsive; the initial load and every Refresh complete without blocking the GUI thread. |
| EC-RB-13 | The selected row is filtered out by a search change. | Selection clears; the centre and right panels return to no-selection. Clearing the search restores the full list but not the prior selection. |
| EC-RB-14 | A resume is attempted but the run is no longer resumable (its results were all completed by a concurrent action). | The Resume use case re-checks resumability via `ResultsStore.list_resumable_results`; if nothing is resumable it refuses with a `_global_message` toast "This run is fully completed — nothing to resume" and the Resume Summary dialog does not open. |

This widget participates in the workspace-wide edge-case register; the IDs above are local to this document and are cross-referenced from `08_Cross_Cutting/08-I_edge_cases.md`.

---

## 10. Function inventory

A flat list of every callable behaviour of the widget, for tester traceability.

| # | Function | Primitive | Gated by |
|---|---|---|---|
| 1 | Filter / search the run list | Single-line input | Always. |
| 2 | Refresh the run list | Button | Always. |
| 3 | Sort the run list by a column | Table header click | Always. |
| 4 | Select a run | Table row click | Always. |
| 5 | Clear the selection | Table empty-area click | A row is selected. |
| 6 | Resume Run (footer) | Primary button | Selected row resumable; not executing. |
| 7 | Resume Run (context menu) | Menu item | Selected row resumable; not executing. |
| 8 | Retry selected tasks… | Menu item | Selected row has ≥ 1 resumable result; not executing. |
| 9 | Clone as new retry run | Menu item | Selected row not executing. |
| 10 | Rename… (context menu) | Menu item | Selected row not executing. |
| 11 | Rename… (inline pencil) | Icon button | Selected row not executing. |
| 12 | Export Summary (CSV) | Menu item | Always. |
| 13 | Export Summary (Markdown) | Menu item | Always. |
| 14 | Export Details (CSV) | Menu item | Always. |
| 15 | Export Details (Markdown) | Menu item | Always. |
| 16 | Export Run Analysis (Markdown) | Menu item | Run's `run_analysis` non-empty. |
| 17 | Show run-log file | Menu item | Run log file exists on disk. |
| 18 | Delete | Menu item | Selected row not executing. |
| 19 | Open Resume Summary by double-click | Table row double-click | Selected row resumable; not executing. |
