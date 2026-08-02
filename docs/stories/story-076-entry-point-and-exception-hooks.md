---
id: STORY-076
title: Install the process entry point and the two top-level exception hooks
status: done
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
- Opening the single database write connection — owned by STORY-077, which opens it once and
  injects it into its dependents.
- The database schema check, the app-data-directory hardening, and default seeding — owned by
  STORY-078.
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
- **The two hook functions live in `__main__.py`, not on `backend/infra/`'s public surface.** This
  story adds no new public API symbol, which is what keeps it inside the `S` bound. It cites
  `backend/infra/` because that is the module it *wires* (`configure_logging`, the clock) —
  `__main__.py` is not an extractable `modules:` value, and ADR-0010 sanctions Phase-11 stories
  citing the modules they wire rather than only the ones they change.
- No `asyncio`, `anyio`, or `qasync`; the only event loop is `app.exec()`.
- The exception logged by the hook is redacted before it reaches the application log (no secret
  value is written), reusing the existing `backend/errors/` redaction — this story adds no new
  redaction path.
- The user-interface-thread hook's exit path performs the ordered shutdown through the `AppHandle`
  shutdown handle (STORY-077) so the database is checkpointed and closed cleanly before exit.
- **The `compose.py` 50–200-line budget is shared.** STORY-077-AC-5 asserts that budget as a
  standing invariant on the *final* `compose.py`, not as a snapshot at STORY-077's merge. Any line
  this story adds to `compose.py` or its entry-point glue spends from the same budget, so keep the
  entry-point surface in `__main__.py` and add nothing to `compose.py` that does not have to be
  there.
- Reuse the existing `make_error_dialog` on `ui/common_dialogs/`'s public surface for the blocking
  modal (its `FATAL` pattern already requires a `quit_callback`, which is exactly this hook's
  shape) rather than hand-building a `QMessageBox` — it costs fewer lines and needs no new public
  symbol.

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
- STORY-076-AC-1 — integration, `tests/integration/test_ui_thread_exception_hook.py`,
  `test_ui_thread_uncaught_programmer_error_logs_critical` (parametrized over this codebase's
  own `ProgrammerError` and `icontract`'s own `ViolationError`) — proves the hook logs at
  CRITICAL, not ERROR, for both must-crash exception hierarchies.
- STORY-076-AC-1 — integration, `tests/integration/test_ui_thread_exception_hook.py`,
  `test_ui_thread_second_exception_during_modal_does_not_show_second_dialog` — proves a second
  uncaught exception arriving while the fatal dialog is already showing is logged but never
  shown in a second stacked dialog (EC-ERR-3 in `07_Common_Dialogs/error_dialog.md`).
- STORY-076-AC-2 — integration, `tests/integration/test_worker_thread_exception_hook.py`,
  `test_worker_thread_uncaught_exception_is_logged_and_app_stays_alive`.
- STORY-076-AC-2 — integration, `tests/integration/test_worker_thread_exception_hook.py`,
  `test_worker_thread_system_exit_is_not_logged` — proves a worker thread ending itself with
  `SystemExit` produces no `app.log` record, matching the standard library's own default
  `threading.excepthook` behaviour.

## Known limitations / follow-ups

An independent spec-conformance review of this story's first implementation pass found three
things a future reader needs to know without re-deriving them.

1. **Where logging gets configured deviates from ADR-0010's literal text.** ADR-0010's
   settlement 1 literally lists "configure logging" as one of `build_app`'s internal steps.
   This implementation instead calls `configure_logging` from `__main__.py`, right after
   platform detection and before either exception hook is installed — not inside `build_app`.
   This was a deliberate, reviewed choice, not an oversight: `compose.py` had exactly one line
   of headroom left against its owner-approved 50-200-line budget (shared with two other
   not-yet-implemented stories), and this story's own design constraints already said not to
   add anything to `compose.py` that doesn't have to be there. `configure_logging` only needs
   the platform detector's `app_data_root`, which `__main__.py` can obtain directly by calling
   `make_platform_detector().detect()` a second, harmless, side-effect-free time (`build_app`
   already does this once, unchanged). This placement is also strictly *safer* than the literal
   ADR reading: logging is active for the entire window during which both exception hooks are
   armed, not only from `build_app`'s first statement onward.

1. **`AppHandle.shutdown()` only performs two of the specification's six ordered shutdown
   steps.** `12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md` §8 defines a six-step shutdown
   sequence. Today `shutdown()` performs only steps 3-4 (closing the HTTP client and
   checkpointing/closing the database) — the exact two steps this story's UI-thread crash hook
   needs. Steps 1-2 (hard-cancel any in-flight run, drain the `QThreadPool`, join the dispatcher
   thread) and step 5 (release the single-instance advisory lock) are not performed by the crash
   hook's `quit_callback` today. This is a known, already-tracked gap, not a silent limitation:
   it was already the documented scope boundary of STORY-077's `AppHandle`, and closing it is
   STORY-080's job ("Quit sequence and crash recovery"). Until STORY-080 lands, a crash that
   happens while the dispatcher thread is mid-write could theoretically race with the crash
   hook's database close.

1. **The fatal crash dialog's "Copy Details" action copies to the clipboard but shows no
   confirmation toast.** `error_dialog.md` §9 and EC-ERR-6 require the dialog to emit a
   confirmation toast (`"Details copied."` / `"Could not copy to the clipboard."`) over the
   application's `EventBus` when the user clicks Copy Details. `__main__.py` cannot reach the
   real, composed `EventBus` that `MainWindow`'s `NotificationService` subscribes to — that bus
   is created inside `build_app` and is never exposed on `AppHandle`. So the crash dialog is
   wired to a separate, dedicated `EventBus` instance built in `__main__.py` with no
   subscribers: the clipboard copy itself genuinely works (it is a real OS clipboard write),
   but the confirmation toast is silently swallowed because nothing is listening on that bus.
   Fixing this properly means exposing the composed `EventBus` (and/or `NotificationService`)
   on `AppHandle`, which is a `compose.py` change deliberately deferred rather than made under
   this story's exhausted line budget. This is flagged as follow-up work for whichever story
   next touches `compose.py`'s `AppHandle` — STORY-080 is the natural owner, since it already
   needs to extend `AppHandle` for the fuller shutdown sequence described in item 2 above.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-076.
- [x] EC-M-8 has a passing test.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.
