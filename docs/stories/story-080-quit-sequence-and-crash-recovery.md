---
id: STORY-080
title: Complete the ordered shutdown, the WAL checkpoint on close, and the crash-recovery sweep call sites
status: done
spec_clauses:
  - 08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence
  - 08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
  - 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#8-shutdown-ordering-guarantees
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#9-crash-recovery-sweep
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-4
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-6
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-7
modules:
  - ui/main_window/
  - backend/benchmark_pipeline/
  - backend/persistence/results/
  - backend/infra/
  - adapters/qt_runnables/
acceptance_criteria:
  - STORY-080-AC-1
  - STORY-080-AC-2
  - STORY-080-AC-3
  - STORY-080-AC-4
  - STORY-080-AC-5
  - STORY-080-AC-6
  - STORY-080-AC-7
  - STORY-080-AC-8
edge_cases:
  - EC-M-4
  - EC-M-6
  - EC-M-7
depends_on:
  - STORY-076
  - STORY-077
  - STORY-078
  - STORY-079
adrs:
  - ADR-0010
owner: coder
estimate: L
---

# STORY-080 — Complete the ordered shutdown, the WAL checkpoint on close, and the crash-recovery sweep call sites

## Goal

Give the application a shutdown that actually shuts things down, and a launch that actually
recovers from the previous crash. Today, confirming a quit closes the window and the process ends
without ever draining the worker pool, joining the dispatcher thread, closing the HTTP client,
checkpointing the database, or releasing the instance lock — and no crash-recovery sweep runs
anywhere, so a run interrupted mid-task comes back with result rows frozen half-way through and
never re-runs those tasks cleanly. After this story, quitting persists the user-interface state,
performs the six ordered shutdown steps, and exits; launching sweeps the previous session's
half-finished result rows back to `pending` while leaving the interrupted run itself available to
resume; and resuming a run sweeps again before it dispatches anything.

## In scope

- **Completing `AppHandle.shutdown()` in the composition root from steps 3–4 to steps 1–5** of the
  fixed shutdown order, exactly as ADR-0010 settlement 2 already specifies: hard-cancel the run,
  join the dispatcher thread and drain the `TaskRunner` pool, close the one synchronous HTTP
  client, `PRAGMA wal_checkpoint(TRUNCATE)` and close the write connection, release the instance
  lock. Every handle the five steps need is already a field on `AppHandle` except the pipeline
  facade that owns step 1's cancellation token; adding that one field is this story's single new
  public-surface change.
- **Calling that shutdown from the process entry point.** `__main__.py` currently ends with
  `sys.exit(app.exec())`, so on a normal quit nothing in the ordered shutdown ever runs. It
  becomes: capture the exit code from `app.exec()`, call `handle.shutdown()` (steps 1–5), then
  exit with that code (step 6).
- **Persisting the active workspace at quit.** `MainWindowGateway.set_active_workspace(...)` has
  existed since STORY-105 and has no production caller anywhere, so `ui.active_workspace` is read
  at launch but never written. The main window's confirmed-quit path writes it from
  `WorkspaceController.active()` alongside the window-geometry/splitter-sizes flush that already
  happens there.
- **A save-all hook on the quit sequence, plus the factory widening that makes both quit hooks
  injectable.** `CloseHandler` already distinguishes "Save all" from "Discard all" but then treats
  them identically — choosing "Save all" today silently discards every unsaved buffer. This story
  adds the injected `save_all_buffers` callable and invokes it on the "Save all" choice, before the
  quit proceeds. It also widens `make_main_window` with two optional keyword parameters,
  `dirty_buffer_count` and `save_all_buffers`, forwarded unchanged to `CloseHandler` — the same
  additive pattern STORY-077 used for `settings_requested`/`about_requested`, and the missing link
  that lets a later story inject real suppliers without reopening `ui/main_window/` again. The real
  Task Editor implementations behind both callables are STORY-114's; this story delivers, forwards
  and proves the hooks with test-supplied ones.
- **The crash-recovery sweep's two call sites**, both of which are missing entirely today even
  though `ResultsStore.recover_in_flight_results()` is fully implemented and unit-tested:
  - **At launch** — in `build_app`, immediately after `ensure_schema(...)` returns successfully and
    before the main window is built, alongside default seeding (ADR-0010 settlement 1's launch
    step 6).
  - **On resume** — in `BenchmarkFlowApi.resume(run_id)`, before the run is handed to the
    dispatcher. This *replaces* the ad-hoc partial reset that method performs today (it resets only
    `running_inference` rows via `reset_results(...)` and never touches the three
    `awaiting_*_check` statuses, and it never deletes the orphaned `benchmark_result_terms` /
    `benchmark_result_attempts` child rows the spec requires deleting).

## Out of scope

- **Building the quit-confirmation dialogs.** `ui/main_window/_internal/close_handler.py`
  (STORY-053) already implements the whole two-confirmation sequence: the running-benchmark prompt,
  the bounded non-blocking wait for `_run_stopped`, the unsaved-buffers prompt with its three
  choices, and the `on_confirmed_quit` callback. This story wires what happens *after* that
  sequence resolves, plus the one save-all hook named above. Do not rebuild the dialogs.
- **The recovery-sweep SQL itself.** `ResultsStore.recover_in_flight_results()` (STORY-011)
  already deletes the child rows, resets in-flight rows to `pending`, clears the in-flight columns,
  and leaves terminal rows untouched. This story only calls it, at the two sites above.
- **The pipeline's hard-cancel and bounded-shutdown mechanics.**
  `BenchmarkFlowApi.shutdown(timeout_ms)` (STORY-029/STORY-030) already hard-cancels the live token
  and joins the dispatcher thread. This story calls it as step 1 plus half of step 2 and adds the
  missing pool drain.
- **Wiring the Task Editor into the quit sequence — owned by STORY-114.** The real
  `dirty_buffer_count` supplier (`CloseHandler`'s parameter still defaults to always-zero), the
  real save-all implementation that writes each dirty file, persisting `ui.task_editor_last_folder`
  when a file or folder is opened or created, and writing `ui.active_workspace` on *every*
  workspace switch (not only at quit) all belong to STORY-114. This story's confirmation-path
  acceptance criteria are therefore proven with a test-supplied dirty-buffer count and a
  test-supplied save-all callable, which is exactly how `CloseHandler`'s existing STORY-053 tests
  already drive it.
- **The exception hooks and the entry point's own structure** — owned by STORY-076. This story adds
  two statements to `main()` and changes nothing else in `__main__.py`.
- **The launch prelude** (app-data directory, instance-lock acquisition, database open, schema
  check, seeding) — owned by STORY-078. This story inserts one sweep call after that prelude.

## Spec inputs

- `08_Cross_Cutting/08-M_app_lifecycle.md#7-quit-sequence` — the ordered, cancellable quit:
  the running-benchmark confirmation first (Cancel aborts and returns to the running state; Confirm
  requests a pipeline shutdown with a bounded timeout, and the affected run is left at the status
  its pipeline records, `STOPPED` for a user stop), then the unsaved-changes confirmation
  (Save all / Discard all / Cancel), then persist the user-interface state — window geometry,
  active workspace, last task-editor folder, splitter sizes — through the settings service, then
  close the database so its write-ahead log is checkpointed, then exit. When both confirmations
  apply they are shown in sequence, running-benchmark first.
- `08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy` — a run found persisted as `INCOMPLETE`
  at launch is the trace of a process that exited before the run reached a terminal status; it is
  left `INCOMPLETE` so the user can resume it and is never silently discarded.
- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the schema check is
  launch step 5 and default seeding is step 6; the sweep's "immediately after the schema-version
  check passes" therefore lands between them, which is where `build_app` performs it per ADR-0010.
- `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md#8-shutdown-ordering-guarantees` — the fixed
  six-step order: (1) hard-cancel the in-progress run through the `CancellationToken`, bounded by
  `app.shutdown_timeout_ms`; (2) drain the `TaskRunner`'s `QThreadPool` via `waitForDone` and join
  the pipeline dispatcher thread; (3) close the single synchronous HTTP client; (4) checkpoint and
  close the database connection, releasing the `-wal` and `-shm` files; (5) release the application
  data directory's instance lock; (6) exit the process.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#9-crash-recovery-sweep` — nothing is swept on
  `benchmark_runs` (an interrupted run is correctly `incomplete` already); recovery is required
  only at the result level. The sweep runs once at startup, immediately after the schema-version
  check passes, and again whenever a run is resumed, inside a single transaction: delete the
  `benchmark_result_terms` and `benchmark_result_attempts` child rows of every result left in
  `running_inference` / `awaiting_keyword_check` / `awaiting_cosine_check` / `awaiting_judge_check`,
  then reset those results to `pending` and clear their in-flight columns. Terminal rows are left
  untouched.

## Design constraints

- **`AppHandle.shutdown()` is the single owner of steps 1–5; `__main__.py` owns step 6.** This is
  not a new decision — ADR-0010 settlement 2 already defines `AppHandle` as carrying "a shutdown
  handle that encapsulates the ordered shutdown of `05_CONCURRENCY_GUARANTEES.md` §8". STORY-077
  shipped a deliberately partial version (steps 3–4 only) and recorded the remainder as this
  story's job. Putting all five steps behind that one method is what makes the normal quit and the
  user-interface-thread crash hook share one shutdown path: the crash hook in `__main__.py` already
  calls `handle.shutdown()`, so completing the method also closes STORY-076's documented
  limitation that a crash could race the dispatcher thread against the database close.
- **The user-interface layer never performs a shutdown step.** `ui/main_window/`'s confirmed-quit
  callback does exactly two things: persist the user-interface state it owns, and close the window.
  It holds no database connection, no `TaskRunner`, no dispatcher, and no instance-lock handle — it
  reaches the settings layer only through `MainWindowGateway` (D-R-06). Closing the last window
  ends `app.exec()`, which is what hands control back to `__main__.py` for steps 1–6.
- **Within step 2, join the dispatcher before draining the pool.** The dispatcher thread is the
  only thing that submits units to the pool; draining the pool first would let the still-running
  dispatcher submit fresh work into a pool that was just declared empty.
  `BenchmarkFlowApi.shutdown(timeout_ms)` already performs the hard cancel and the dispatcher join
  together, and `TaskRunner.shutdown()`'s own docstring already states it is "called once by the
  composition root during application shutdown — after the dispatcher thread has been joined".
  `05_CONCURRENCY_GUARANTEES.md` §8 states both halves as one step without fixing their internal
  order, so this ordering is a design choice recorded here.
- **A confirmed quit is a user stop, not an app-shutdown cancel — do not "fix" the cancel reason.**
  `BenchmarkFlowApi.shutdown()` cancels with `CancelReason.USER_STOP`, and the pipeline's
  halt-outcome mapping turns `USER_STOP` into a persisted `STOPPED` run and `APP_SHUTDOWN` into no
  persisted status change at all. `08-M` §7 step 2 says explicitly that a quit-confirmed stop
  leaves the run at "the persisted status its pipeline records (`STOPPED` for a user stop)", so
  `USER_STOP` is the correct reason for this path and must stay. `APP_SHUTDOWN` remains reserved
  for a shutdown the user never confirmed.
- **The sweep is deliberately unscoped by run.** `recover_in_flight_results()` takes no `run_id`
  and sweeps every in-flight row, matching the specification's own SQL. That is safe on the resume
  path because at most one run executes anywhere in the application at a time (D-R-16), so no other
  run can own an in-flight row when a resume begins.
- **On resume, sweep before selecting rows.** The sweep must run before `list_resumable_results` /
  `list_results` are read, otherwise the selection is computed against the stale half-finished
  statuses the sweep is about to rewrite.
- `backend/benchmark_pipeline/`, `backend/persistence/results/`, and `backend/infra/` are Qt-free;
  the confirmation modals are Qt and stay in `ui/main_window/`.
- **`compose.py`'s line budget is shared and was fully spent, not "nearly."** This Design constraint
  originally (2026-08-02, at promotion to `ready`) claimed the file was at 399 of the then-current
  50–500-line bound (STORY-077-AC-5). That claim was stale: STORY-078's own session had already
  pushed the file to 499/500 lines in its final fix wave, leaving zero headroom, not "roughly a
  dozen lines." This story's minimal, spec-mandated compose-side work (the `flow: QtBenchmarkFlow`
  field, `AppHandle.shutdown()`'s growth to the full 5-step sequence, and the one
  `res.recover_in_flight_results()` sweep call) landed at 508 lines with no further
  import-collapsing room available (per STORY-078's own exhaustive prior attempt at exactly that).
  The owner approved a third widening, 500→520 (see `tests/architecture/test_compose_line_budget.py`'s
  own updated docstring for the full history) rather than distorting this story's minimal diff to
  chase a stale ceiling.
- `compose.py` and `__main__.py` are not extractable `modules:` values (the traceability tooling
  recognises only `backend/…`, `adapters/…`, `ui/…` paths), so this story cites the modules it
  wires and extends, per ADR-0010's own note and STORY-076's precedent. `backend/settings/` is
  deliberately *not* listed: no code in it changes and the main window reaches it only through
  `MainWindowGateway`.

## Acceptance criteria

### STORY-080-AC-1

Given a benchmark is running and the user requests a quit, the running-benchmark confirmation is
shown and each choice produces its outcome (EC-M-6):

| Choice  | Outcome                                                                                                                   |
| ------- | ------------------------------------------------------------------------------------------------------------------------- |
| Cancel  | The quit is abandoned: no pipeline shutdown is requested and the confirmed-quit callback never runs.                      |
| Confirm | A bounded pipeline shutdown is requested with the configured timeout, and the quit proceeds only after that wait settles. |

### STORY-080-AC-2

Given a quit is requested while a benchmark is running **and** the dirty-buffer count is non-zero,
each confirmation path produces its outcome (EC-M-7):

| Running-benchmark choice | Unsaved-changes choice | Save-all hook invoked | Quit proceeds |
| ------------------------ | ---------------------- | --------------------- | ------------- |
| Cancel                   | never shown            | no                    | no            |
| Confirm                  | Cancel                 | no                    | no            |
| Confirm                  | Discard all            | no                    | yes           |
| Confirm                  | Save all               | yes, exactly once     | yes           |

The first row is also the proof of ordering: cancelling the running-benchmark prompt means the
unsaved-changes prompt is never reached, so the running-benchmark prompt is always first.

### STORY-080-AC-3

Given a quit has been confirmed, when the confirmed-quit path runs, then each user-interface value
this story owns has been written through the settings service before the database write connection
is closed:

| Value            | Setting key           | Source                         |
| ---------------- | --------------------- | ------------------------------ |
| Window geometry  | `ui.window_geometry`  | The debounced geometry writer  |
| Splitter sizes   | `ui.splitter_sizes`   | The debounced geometry writer  |
| Active workspace | `ui.active_workspace` | `WorkspaceController.active()` |

### STORY-080-AC-4

Given the application is quitting, when the database is closed, then
`PRAGMA wal_checkpoint(TRUNCATE)` runs on the write connection before it is closed, and the
database's `-wal` file is reclaimed (zero-length or absent) after the process exits.

### STORY-080-AC-5

Given a database holding a run persisted `INCOMPLETE` whose result rows include one row in each of
`running_inference`, `awaiting_keyword_check`, `awaiting_cosine_check` and `awaiting_judge_check`,
each with child term and attempt rows, when the application launches, then the run's persisted
status is still `INCOMPLETE`, every one of those four rows is `pending` with its child rows
deleted, and every terminal row is unchanged (EC-M-4).

### STORY-080-AC-6

Given the application is quitting, when the ordered shutdown runs, then these six actions are each
performed exactly once, in exactly this order:

| Order | Action                                                                          |
| ----- | ------------------------------------------------------------------------------- |
| 1     | The in-progress run is hard-cancelled through its `CancellationToken`           |
| 2     | The pipeline dispatcher thread is joined, then the `TaskRunner` pool is drained |
| 3     | The single synchronous HTTP client is closed                                    |
| 4     | The write connection is checkpointed and closed                                 |
| 5     | The instance lock is released                                                   |
| 6     | The process exits with the exit code `app.exec()` returned                      |

### STORY-080-AC-7

Given the application has quit through the ordered shutdown, when a second process acquires the
single-instance lock against the same application data directory, then acquisition succeeds
immediately without needing the stale-owner reclaim path.

### STORY-080-AC-8

Given a run is resumed whose result rows include one row in each of the four in-flight statuses,
when `resume(run_id)` is called, then the crash-recovery sweep has run — those rows are `pending`
and their child term and attempt rows are deleted — before the run is submitted to the dispatcher.

## Test plan

- STORY-080-AC-1 — unit (`pytest-qt`, table-driven, one `@pytest.mark.parametrize` row per choice,
  no dirty buffers involved), colocated
  `src/ollama_llm_bench/ui/main_window/_internal/tests/test_close_handler.py`,
  `test_running_benchmark_confirmation_outcome_per_ac1_table`. Covers EC-M-6.
- STORY-080-AC-2 — unit (`pytest-qt`, table-driven, one `@pytest.mark.parametrize` row per path,
  with a fake dirty-buffer count and a recording save-all callable), same file,
  `test_confirmation_paths_produce_documented_outcomes_per_ac2_table` — shares its assertion body
  (`_assert_quit_confirmation_outcome`) with `test_quit_with_running_run_and_dirty_buffers_confirms_in_order`,
  the pre-existing STORY-053-AC-6 test this AC's table extends (adding the save-all/discard-all
  distinction). Covers EC-M-7.
- STORY-080-AC-3 — integration, `tests/integration/test_quit_sequence.py`,
  `test_quit_persists_ui_state_before_closing_db`.
- STORY-080-AC-4 — integration, same file, `test_quit_closes_db_with_wal_checkpoint_truncate`.
- STORY-080-AC-5 — integration, `tests/integration/test_launch_crash_recovery.py`,
  `test_incomplete_run_left_for_resume_and_in_flight_rows_reset_to_pending`. Covers EC-M-4.
- STORY-080-AC-6 — integration (recording fakes for the dispatcher, pool, HTTP client, connection
  and lock; assert the recorded action sequence equals the expected six-element sequence),
  `tests/integration/test_quit_sequence.py`, `test_ordered_shutdown_runs_all_six_steps_in_order`.
- STORY-080-AC-7 — integration, same file, `test_instance_lock_is_reacquirable_after_clean_quit`.
- STORY-080-AC-8 — unit, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume_recovery_sweep.py`,
  `test_resume_sweeps_in_flight_rows_before_dispatch`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-080.
- [x] EC-M-4, EC-M-6, and EC-M-7 each have a passing test.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules — verified
  repo-wide, not just touched files: `ruff check`/`ruff format --check`/`mypy --strict src/`/
  `lint-imports` all clean.
- [x] `compose.py` still satisfies STORY-077-AC-5's line-budget architecture test — the budget
  was widened a third time, 500→520 lines (owner-approved), since the file was already at
  499/500 before this story touched it (see Notes); `compose.py` is 508 lines, within the new
  bound.
- [x] The traceability record validates with no orphan clause and no orphan test caused by this
  story. `just trace-check` reports exactly one remaining finding,
  `EC-M-5 is named by a story but has no proving test` — pre-existing, owned by STORY-081
  (`status: draft`, not yet implemented), confirmed unrelated to this story's scope.
- [x] The module inventory is unchanged.

## Notes

- **`modules:` gained `adapters/qt_runnables/` during implementation planning (2026-08-02).**
  Draining the `TaskRunner`'s pool (shutdown step 2b) needs `QtTaskRunner.shutdown()`, which its
  own docstring deliberately keeps off the backend `TaskRunner` Protocol ("Not part of the
  `TaskRunner` Protocol... Called once by the composition root during application shutdown").
  Widening the shared Protocol just for this one adapter-lifecycle call would ripple into every
  `TaskRunner` implementer and test fake for no spec-mandated reason; instead `AppHandle.task_runner`
  is typed concretely as `QtTaskRunner[object]` and that type is exported from
  `adapters/qt_runnables/`'s public surface. Still within the `L` bound (5 modules, the cap).
- **Refined and promoted `draft` → `ready` (2026-08-02)** after an investigation pass compared this
  story's original 2026-07-23 draft against the tree as it stands once STORY-077, STORY-078 and
  STORY-079 landed. Three things changed materially. (1) The story is no longer "build the quit
  sequence" — `CloseHandler` already implements both confirmations end to end; what is missing is
  everything that happens *after* the confirmations resolve. (2) The three ambiguities the
  investigation flagged (who owns shutdown steps 1-2-5, how far Task Editor integration reaches,
  and where exactly the sweep is called) are now settled in the Design constraints and In-scope
  sections rather than left to the coder. (3) `modules:` was corrected: `backend/settings/` was
  dropped (no code in it changes) and `backend/benchmark_pipeline/` plus `backend/infra/` were
  added, taking the estimate from `M` to `L`.
- **No new ADR was needed.** ADR-0010 settlement 2 already assigns the full five-step ordered
  shutdown to `AppHandle`, and settlement 1 already places the crash-recovery sweep inside
  `build_app` at launch step 6. This story implements those two settlements rather than deciding
  anything new; the only genuinely new choice — joining the dispatcher before draining the pool
  within step 2 — is recorded in Design constraints, which is proportionate for an ordering detail
  inside one method.
- **`depends_on` includes STORY-076, which is `status: in-progress`.** Strictly,
  `02_STORY_FORMAT.md` §8 requires every dependency to be `done` before a story is `ready`. This
  story is marked `ready` anyway because the dependency is on an artefact that has already landed:
  `__main__.py` exists with `main()`, both exception hooks and the `AppHandle` holder, and both of
  STORY-076's acceptance-criteria test files
  (`tests/integration/test_ui_thread_exception_hook.py`, `test_worker_thread_exception_hook.py`)
  are in the tree — only STORY-076's Definition-of-done checkboxes are unflipped. Confirm STORY-076
  is genuinely complete and flip it to `done` before starting this story; if it is instead reopened
  for rework, re-check this story's two-statement change to `main()` against whatever shape
  STORY-076 settles on.
- **Two adjacent gaps this story deliberately does not close, both owned by STORY-114.** First,
  `CloseHandler`'s `dirty_buffer_count` parameter still defaults to always-zero, so in the running
  application the unsaved-changes prompt can never appear at all — the confirmation logic is
  correct but unreachable until the Task Editor supplies a real count. Second,
  `09_Task_Editor/description.md` §6 requires `ui.active_workspace` to be written on *every*
  workspace switch and `ui.task_editor_last_folder` to be written whenever a file or folder is
  opened or created; neither has any writer today. This story writes `ui.active_workspace` at quit
  only, which satisfies `08-M` §7 step 4 but not the Task Editor's own eager-write table.
  </content>
