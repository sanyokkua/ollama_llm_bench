---
id: STORY-080
title: Wire the quit sequence, WAL checkpoint on close, and crash-recovery handling
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence
  - 08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy
  - 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#8-shutdown-ordering-guarantees
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#9-crash-recovery-sweep
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-4
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-6
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-7
modules:
  - ui/main_window/
  - backend/settings/
  - backend/persistence/results/
acceptance_criteria:
  - STORY-080-AC-1
  - STORY-080-AC-2
  - STORY-080-AC-3
  - STORY-080-AC-4
  - STORY-080-AC-5
edge_cases:
  - EC-M-4
  - EC-M-6
  - EC-M-7
depends_on:
  - STORY-077
adrs:
  - ADR-0010
owner: coder
estimate: M
---

# STORY-080 — Wire the quit sequence, WAL checkpoint on close, and crash-recovery handling

## Goal

Give the application a clean, cancellable quit and a clean recovery from a previous crash. Closing
the window asks the user to confirm stopping a running benchmark and to save unsaved task-editor
buffers, persists the user-interface state, checkpoints and closes the database, and exits — and a
cancel at any confirmation returns the application to its running state. At the next launch, a run
that was interrupted mid-flight is left available to resume rather than discarded, and its in-flight
result rows are reset so the tasks re-run cleanly.

## In scope

- The quit sequence driven from the main window's close handler: the running-benchmark confirmation
  (Cancel / Confirm), then the unsaved-changes confirmation (Save all / Discard all / Cancel), shown
  in that order when both apply.
- On confirm-to-stop, requesting a bounded pipeline shutdown before proceeding.
- Persisting the user-interface state (window geometry, active workspace, last task-editor folder,
  splitter sizes) through the settings service, then closing the database with
  `PRAGMA wal_checkpoint(TRUNCATE)`, then exiting — the ordered shutdown carried by the `AppHandle`
  shutdown handle (STORY-077).
- Crash-recovery handling at launch: a run persisted `INCOMPLETE` is left `INCOMPLETE` and offered for
  resume; the result-level recovery sweep resets in-flight result rows to `pending`.

## Out of scope

- The window close (X) control quitting on every platform — already delivered by STORY-053.
- The result-level recovery-sweep SQL itself (`recover_in_flight_results`) — already delivered by
  STORY-011; this story invokes it at launch and asserts the run-status outcome.
- The pipeline's hard-cancel / bounded-shutdown mechanics — already delivered by STORY-029/STORY-030;
  this story requests the shutdown and honours the bounded timeout.
- The exception hooks and the entry point — owned by STORY-076.
- The launch glue (app-data, DB open, schema check, seed) — owned by STORY-078.

## Spec inputs

- `08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence` — the ordered, cancellable quit:
  running-benchmark confirmation first (Cancel aborts; Confirm requests a bounded pipeline shutdown),
  then the unsaved-changes confirmation (Save all / Discard all / Cancel), then persist UI state, then
  close the database so its write-ahead log is checkpointed, then exit; when both confirmations apply
  they are shown in sequence.
- `08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy` — a run found persisted as `INCOMPLETE` at
  launch is left `INCOMPLETE` for resume and never silently discarded.
- `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#8-shutdown-ordering-guarantees` — the fixed
  shutdown order: hard-cancel the run, drain the pool and join the dispatcher, close the HTTP client,
  checkpoint (`wal_checkpoint(TRUNCATE)`) and close the database, release the instance lock, exit.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#9-crash-recovery-sweep` — the sweep runs at startup and
  resets every result left in a non-terminal in-flight status back to `pending`, clearing its
  in-flight columns and child rows; terminal rows are left untouched.

## Design constraints

- `backend/settings/` and `backend/persistence/results/` are Qt-free; the confirmation modals are
  Qt and are driven from `ui/main_window/`.
- The UI state is persisted through the settings service before the database is closed.
- The database is closed with `PRAGMA wal_checkpoint(TRUNCATE)` at clean shutdown (WAL reclamation at
  the quiescent point).
- A cancel at either confirmation aborts the quit and leaves the application running; a confirmed stop
  leaves the affected run at the status its pipeline records (`STOPPED` for a user stop).

## Acceptance criteria

### STORY-080-AC-1

Given a benchmark is running,
when the user requests a quit,
then the running-benchmark confirmation is shown; Cancel returns to the running state, and Confirm
requests a bounded pipeline shutdown before the quit proceeds (EC-M-6).

### STORY-080-AC-2

When a quit is requested with both a running benchmark and unsaved task-editor buffers, the two
confirmations behave per the user's choice:

| Confirmation and choice                                         | Outcome                                            |
| --------------------------------------------------------------- | -------------------------------------------------- |
| Running-benchmark → Cancel                                      | Quit aborted; application returns to running state |
| Running-benchmark → Confirm, then unsaved-changes → Cancel      | Quit aborted; application returns to running state |
| Running-benchmark → Confirm, then unsaved-changes → Save all    | Every unsaved task file is written; quit proceeds  |
| Running-benchmark → Confirm, then unsaved-changes → Discard all | No task file is written; quit proceeds             |

The running-benchmark confirmation is always shown before the unsaved-changes confirmation (EC-M-7).

### STORY-080-AC-3

Given a quit is proceeding,
when the shutdown runs,
then the window geometry, active workspace, last task-editor folder, and splitter sizes are persisted
through the settings service before the database is closed.

### STORY-080-AC-4

Given a quit is proceeding,
when the database is closed,
then it is closed with `PRAGMA wal_checkpoint(TRUNCATE)` so the write-ahead log is reclaimed.

### STORY-080-AC-5

Given a run persisted `INCOMPLETE` with in-flight result rows at launch,
when the crash-recovery sweep runs,
then the run is left `INCOMPLETE` and offered for resume (never discarded) and its in-flight result
rows are reset to `pending` (EC-M-4).

## Test plan

- STORY-080-AC-1 — integration, `tests/integration/test_quit_sequence.py`,
  `test_quit_while_running_confirms_then_requests_bounded_shutdown`. Covers EC-M-6.
- STORY-080-AC-2 — integration (table-driven, one `@pytest.mark.parametrize` row per confirmation
  path), same file, `test_quit_with_running_and_unsaved_shows_both_confirmations_in_order`. Covers
  EC-M-7.
- STORY-080-AC-3 — integration, same file, `test_quit_persists_ui_state_before_closing_db`.
- STORY-080-AC-4 — integration, same file, `test_quit_closes_db_with_wal_checkpoint_truncate`.
- STORY-080-AC-5 — integration, `tests/integration/test_launch_crash_recovery.py`,
  `test_incomplete_run_left_for_resume_and_in_flight_rows_reset_to_pending`. Covers EC-M-4.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-080.
- [ ] EC-M-4, EC-M-6, and EC-M-7 each have a passing test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
