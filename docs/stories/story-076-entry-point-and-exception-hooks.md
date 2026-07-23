---
id: STORY-076
title: Install the process entry point and the two top-level exception hooks
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
  - 08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-8
modules:
  - backend/infra/
acceptance_criteria:
  - STORY-076-AC-1
  - STORY-076-AC-2
edge_cases:
  - EC-M-8
depends_on:
  - STORY-077
adrs:
  - ADR-0010
owner: coder
estimate: S
---

# STORY-076 — Install the process entry point and the two top-level exception hooks

## Goal

Give the application its process entry point (`python -m ollama_llm_bench`) and the crash policy
the specification mandates. When an uncaught exception reaches the user-interface thread, the
application logs it, shows a blocking modal describing the failure, closes the database cleanly,
and exits — the user never sees a silent crash or a half-closed database. When an uncaught
exception reaches a background worker thread, the application logs it and stays alive, so one
failed benchmark task cannot take down the whole session.

## In scope

- `__main__.py`: the entry point that parses launch arguments, runs the platform detector,
  constructs the single `QApplication`, installs both exception hooks, then calls
  `build_app(*, app, loop)` (STORY-077), shows the window, and enters `app.exec()`.
- The user-interface-thread exception hook: log to the application log, show a blocking modal error
  dialog, close the database cleanly, then exit.
- The background-worker exception hook: log to the application log and leave the application
  running; when the worker was executing a benchmark run, the pipeline's existing FAILED handling
  applies.
- The hooks are installed before `build_app` is called, so they wrap the whole composition (ADR-0010).

## Out of scope

- The object-graph wiring, `AppHandle`, and the export-filename bridge — owned by STORY-077.
- The database open / schema check / seeding launch glue — owned by STORY-078.
- The single-instance advisory lock — owned by STORY-079.
- The quit sequence and the shutdown ordering — owned by STORY-080.
- The pipeline's own "mark the affected run FAILED on a worker exception" logic — already delivered
  by STORY-029; this story's worker hook only logs and keeps the app alive.

## Spec inputs

- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the entry point creates
  the single `QApplication` (step 7) before any widget or adapter; `app.exec()` (step 11) is the
  only event loop; there is no asyncio/qasync loop (D-R-01).
- `08_Cross_Cutting/08-M_app_lifecycle.md#8-crash-policy` — the exact behaviour of both hooks: the
  user-interface-thread hook logs, shows a blocking modal, closes the database cleanly, and exits;
  the worker-thread hook logs and the application stays running and usable.
- `08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-8` — an uncaught exception reaching the user-interface
  thread is logged by the top-level hook, shown in a blocking modal, after which the database is
  closed and the process exits gracefully.

## Design constraints

- `backend/infra/` is Qt-free; the application-log write and any redaction the hook uses are
  Qt-free, and the Qt modal is shown from `__main__.py`, never from `backend/infra/` (ADR-0010).
- No `asyncio`, `anyio`, or `qasync`; the only event loop is `app.exec()`.
- The exception logged by the hook is redacted before it reaches the application log (no secret
  value is written), reusing the existing `backend/errors/` redaction — this story adds no new
  redaction path.
- The user-interface-thread hook's exit path performs the ordered shutdown through the `AppHandle`
  shutdown handle (STORY-077) so the database is checkpointed and closed cleanly before exit.

## Acceptance criteria

### STORY-076-AC-1

Given the application is running,
when an uncaught exception reaches the user-interface thread,
then the top-level hook logs it to the application log, shows a blocking modal error dialog, closes
the database cleanly, and exits the process (EC-M-8).

### STORY-076-AC-2

Given a benchmark is executing on a background worker thread,
when an uncaught exception reaches that worker thread,
then the top-level worker hook logs it to the application log and the application stays running with
a usable user interface.

## Test plan

- STORY-076-AC-1 — integration, `tests/integration/test_ui_thread_exception_hook.py`,
  `test_ui_thread_uncaught_exception_logs_shows_modal_closes_db_and_exits`. Covers EC-M-8.
- STORY-076-AC-2 — integration, `tests/integration/test_worker_thread_exception_hook.py`,
  `test_worker_thread_uncaught_exception_is_logged_and_app_stays_alive`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-076.
- [ ] EC-M-8 has a passing test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
