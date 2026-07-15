---
id: STORY-041
title: Implement the QThreadPool-backed TaskRunner with Future-completion on the worker thread
status: done
spec_clauses:
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#3-the-taskrunner-port-and-the-qt-adapter
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
modules:
  - adapters/qt_runnables/
acceptance_criteria:
  - STORY-041-AC-1
  - STORY-041-AC-2
  - STORY-041-AC-3
  - STORY-041-AC-4
depends_on:
  - STORY-006
owner: coder
estimate: M
---

# STORY-041 — Implement the QThreadPool-backed TaskRunner with Future-completion on the worker thread

## Goal

Provide the Qt implementation of the backend `TaskRunner` port: a `QRunnable` wrapper that runs
a blocking backend unit on a fixed-size `QThreadPool` and completes the unit's thread-safe
stdlib `Future` directly on the worker thread. No Qt signal participates in the completion path,
because the dispatcher thread that waits on the `Future` runs no Qt event loop and would never
receive a queued signal. This is the scheduling substrate every serial run unit and every
fan-out probe runs on.

## In scope

- The `QRunnable` wrapper factory that adapts a backend `Callable[[], T]` plus a
  `CancellationToken` into a pool-schedulable unit and a `TaskRunner.submit(...) -> Future[T]`
  surface over a `QThreadPool`.
- Completing the unit by calling `future.set_result(value)` / `future.set_exception(exc)`
  **directly on the worker thread** inside a `try/except`, so a dispatcher blocked in
  `Future.result()` wakes via the Future's own condition variable — never a Qt signal.
- Carrying the `CancellationToken` into the backend callable so cancellation stays cooperative
  (the callable polls the token and hard-cancel hooks fire), never a Qt-side abort.
- The fixed pool size (`maxThreadCount = 4`) configured once at construction.

## Out of scope

- The `CancellationToken` and the `TaskRunner`/`Future` Protocols themselves — owned by
  STORY-006; this story provides the Qt-backed implementation of that port.
- The dispatcher thread that submits units and blocks on their Futures — owned by
  `adapters/qt_benchmark_flow/` (STORY-042); this story provides the pool it submits onto.
- Pause/Stop/Shutdown semantics and the outcome matrix — the pipeline's concern, not the
  runnable's.

## Spec inputs

- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#3-the-taskrunner-port-and-the-qt-adapter`
  — the `TaskRunner.submit` signature, the `QThreadPool` + `QRunnable` implementation, the
  "complete the Future on the worker thread, no Qt signal in the completion path" rule, and the
  fixed `maxThreadCount = 4`.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38` — why the
  completion path carries no Qt signal (the dispatcher runs no event loop) and that a pool
  worker must never submit-and-wait on the pool.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken` — the
  cooperative, two-level token the runnable carries into the callable; cancellation is polled by
  the callable and driven by hard-cancel hooks, never a Qt abort signal.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — the app-wide
  thread-affinity rules the runnable must honour.

## Design constraints

- `adapters/qt_runnables/` imports PySide6 and the `backend/concurrency` Protocols
  (`01_MODULE_INVENTORY.md` §5). No `asyncio`.
- The completion path sets the stdlib `Future` result/exception on the worker thread; no
  `Signal` is emitted to report unit completion.
- The token is carried into the runnable unchanged (never copied or wrapped); the runnable
  calls `token.raise_if_cancelled()` as a pre-start checkpoint (mirroring `InlineTaskRunner`)
  but never mutates cancellation state itself. The backend callable itself is zero-arg
  (`Callable[[], T]`) and never receives the token directly — cooperative polling inside a
  unit's own logic happens via a token closed over by the dispatcher, not via the runnable
  forwarding it as an argument.
- The pool is owned by the adapter and drained cleanly at shutdown.

## Acceptance criteria

### STORY-041-AC-1

Given a backend callable that returns a value, when it is submitted through the runnable and the
returned `Future.result()` is read, then the result equals the callable's return value and the
value was set on the worker thread (the completion path used no Qt signal).

### STORY-041-AC-2

Given a backend callable that raises an exception, when it is submitted and the returned
`Future.result()` is read, then that exception is re-raised to the reader (captured on the
Future via `set_exception`, not swallowed).

### STORY-041-AC-3

Given a submitted unit, when the runnable's `run()` executes, then the exact
`CancellationToken` object passed to `submit` is the one `run()` calls `raise_if_cancelled()`
on (identity preserved, never copied or wrapped) as a pre-start checkpoint before invoking the
backend callable.

### STORY-041-AC-4

Given the `TaskRunner` is constructed, then its underlying `QThreadPool` reports
`maxThreadCount == 4` (the fixed pool size is configured once at construction).

## Test plan

- STORY-041-AC-1 — integration (`pytest-qt`), `tests/integration/test_qt_runnables.py`,
  `test_submit_completes_future_with_result_on_worker_thread`.
- STORY-041-AC-2 — integration (`pytest-qt`), same file,
  `test_submit_propagates_worker_exception_via_future`.
- STORY-041-AC-3 — unit, colocated
  `src/ollama_llm_bench/adapters/qt_runnables/tests/test_runnable.py`,
  `test_cancellation_token_is_passed_into_callable_unchanged`.
- STORY-041-AC-4 — unit, same file, `test_pool_max_thread_count_is_four`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-041.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/qt_runnables/`.
- [x] An architecture test confirms no Qt signal participates in the unit-completion path and
  the module imports no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for this
  story's clauses/ACs (repo-wide `trace-check` has three pre-existing, unrelated failures —
  `EC-PERSIST-6`, `EC-PROV-1a`, `EC-RUN-1a` — confirmed via `git stash` diff against the
  pre-story baseline; tracked as repo backlog, not introduced by this story).
- [x] The module inventory is unchanged.

## Notes

- `QtTaskRunner.shutdown()` calls `QThreadPool.waitForDone()` with no timeout and is reachable
  only through the concrete class, not the `TaskRunner` Protocol returned by
  `make_qt_task_runner()`. This is intentional per this story's "out of scope" section
  (pause/stop/shutdown semantics belong to the pipeline); a bounded, Protocol-reachable
  shutdown path is deferred to the composition-root shutdown story (`compose.py` /
  `adapters/qt_benchmark_flow/`, STORY-042 and after). No test covers `shutdown()` in this
  story, by design.
- The pre-start `raise_if_cancelled()` checkpoint's behaviour with an already-cancelled *real*
  token (as opposed to a mock) is not exercised by this story's tests — AC-3 proves token
  identity/pass-through only. Cooperative-cancellation semantics are this story's dependency
  (STORY-006) and the pipeline's concern, not re-verified here.
