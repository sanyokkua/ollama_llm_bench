---
id: STORY-006
title: Provide the two-level CancellationToken and the TaskRunner concurrency port
status: done
spec_clauses:
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#3-the-taskrunner-port-and-the-qt-adapter
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken
  - 11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#61-the-taskrunner-and-the-worker-pool
  - 11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#63-the-single-cancellationtoken
modules:
  - backend/concurrency/
acceptance_criteria:
  - STORY-006-AC-1
  - STORY-006-AC-2
  - STORY-006-AC-3
  - STORY-006-AC-4
  - STORY-006-AC-5
depends_on:
  - STORY-001
  - STORY-004
owner: coder
estimate: M
---

# STORY-006 — Provide the two-level CancellationToken and the TaskRunner concurrency port

## Goal

Provide the two Qt-free, asyncio-free concurrency primitives every backend module that
submits work or must be interruptible depends on: the swappable `TaskRunner` scheduling port
and the cooperative, two-level `CancellationToken`. Together these let the backend stay
plain, blocking, synchronous Python while remaining safely cancellable and while the adapter
layer freely swaps in a `QThreadPool`-backed runner, a `ThreadPoolExecutor`-backed runner, or
an inline synchronous test runner behind the same port.

## In scope

- The `TaskRunner` Protocol: `submit(fn: Callable[[], T], *, token: CancellationToken) -> Future[T]`, defined purely in terms of the standard library (`concurrent.futures.Future`)
  — no Qt, no asyncio.
- The `CancellationToken` class: two monotonic levels (`NONE -> SOFT -> HARD`, never
  downgraded, DD-39), backed by `threading.Event`(s), with `cancel(*, reason: CancelReason, hard: bool = False)`, `is_cancelled`, `is_hard_cancelled`, `raise_if_cancelled()` (raises
  `TaskCancelledError`), `wait(timeout: float | None = None) -> bool` (cancellation-aware
  sleep that returns early once cancelled), `snapshot() -> tuple[CancelLevel, CancelReason | None]`, `add_hard_cancel_hook(hook)` / `remove_hard_cancel_hook(hook)`.
- The rule that a token is single-use per run: constructed fresh for each run, threaded
  through every unit of that run, never reused or shared across runs, never a process-wide
  singleton.
- An inline/synchronous `TaskRunner` implementation suitable for tests (executes `fn`
  immediately on the calling thread, still honouring `token` for pre-submission cancellation
  checks) — the Qt-backed and `ThreadPoolExecutor`-backed implementations belong to
  `adapters/qt_runnables/` and a later headless-frontend story respectively, not here.

## Out of scope

- The `QThreadPool` / `QRunnable`-backed concrete `TaskRunner` and the dispatcher thread's
  Qt-side wiring — owned by `adapters/qt_runnables/` in a later phase; this story supplies
  only the Protocol and the framework-agnostic pieces the adapter implements against.
- The dispatcher thread's own orchestration loop (`run_phase`, the single-inference gate,
  circuit-breaker/adaptive-timeout consultation) — owned by `backend/benchmark_pipeline/` in
  a later phase; this story provides the primitives the dispatcher uses, not the dispatcher.
- `TaskCancelledError` itself and the rest of the error taxonomy — owned by STORY-002; this
  story's `raise_if_cancelled()` raises that existing type.
- The `CancelReason` / `CancelLevel` enums' definitions — owned by STORY-001; this story
  consumes them.

## Spec inputs

- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#3-the-taskrunner-port-and-the-qt-adapter`
  — the exact `TaskRunner.submit` signature, the three-implementation contract (Qt, headless,
  test), and the rule that no backend module imports `QThreadPool` or constructs a runner
  inline.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken` — the two
  monotonic levels and their soft/hard semantics, the `threading.Event`-backed
  implementation requirement (never `asyncio.Event`), and the hard-cancel abort-hook
  mechanism bounded by `provider.hard_cancel_max_ms`.
- `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#61-the-taskrunner-and-the-worker-pool`
  — confirms the pipeline never creates threads itself and only ever holds the `TaskRunner`
  port.
- `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#63-the-single-cancellationtoken` — one
  token per run, controller calls `cancel`, worker code calls `raise_if_cancelled()` at safe
  checkpoints; a soft cancel can be upgraded to hard, never the reverse.

## Design constraints

- `backend/concurrency/` is Qt-free and asyncio-free; only `backend/infra` (for `Clock`,
  where a monotonic reference is needed for hook bookkeeping) and the standard library are
  imported (`01_MODULE_INVENTORY.md` §4.1).
- `CancellationToken` uses `threading.Event`, never `asyncio.Event` or any loop-affine
  primitive; it must be safe to `cancel()` from the GUI thread and observe from any worker
  thread with no additional locking required by the caller.
- The level transition is enforced inside the token itself: calling `cancel(hard=False)`
  after a prior `cancel(hard=True)` must not downgrade the level back to soft — the token's
  own internal lock guards level and reason together as one atomic unit (DD-42: reason is a
  closed enum, never free text).
- Hard-cancel abort hooks run outside the token's internal lock (so a hook cannot deadlock
  against a concurrent `cancel()`/`snapshot()` call) and are idempotent-safe to add/remove
  from any thread.
- This module defines no `max_parallel_units` / `phase_concurrency` setting or knob of any
  kind — serial execution is structural, not configurable (D-R-16).

## Acceptance criteria

### STORY-006-AC-1

`TaskRunner` is a `typing.Protocol` declaring exactly `submit(fn, *, token) -> Future[T]`;
the inline test implementation executes `fn` synchronously on the calling thread and returns
a resolved `Future` carrying the result or the raised exception.

### STORY-006-AC-2

A fresh `CancellationToken` starts at level `NONE`; calling `cancel(reason=CancelReason. USER_PAUSE, hard=False)` transitions it to `SOFT`; a subsequent `cancel(reason=CancelReason. USER_STOP, hard=True)` transitions it to `HARD`; a further `cancel(hard=False)` call after
reaching `HARD` leaves the level at `HARD` (never downgraded).

### STORY-006-AC-3

After any `cancel()` call, `raise_if_cancelled()` raises `TaskCancelledError`; before any
`cancel()` call it returns normally. `is_cancelled` is `True` at both `SOFT` and `HARD`;
`is_hard_cancelled` is `True` only at `HARD`.

### STORY-006-AC-4

`wait(timeout)` blocks for up to `timeout` seconds and returns early (before `timeout`
elapses) as soon as `cancel()` is called from another thread, returning a value indicating
the token was cancelled; called on an already-cancelled token it returns immediately.

### STORY-006-AC-5

`add_hard_cancel_hook(hook)` registers `hook`; a subsequent `cancel(hard=True)` call invokes
every registered hook exactly once; `remove_hard_cancel_hook(hook)` prevents a hook from
being invoked by a later hard cancel; a hook that raises is caught inside the token so one
misbehaving hook does not prevent the others from running or prevent `cancel()` from
returning to its caller.

## Test plan

- STORY-006-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/concurrency/tests/test_task_runner.py`,
  `test_inline_task_runner_executes_synchronously_and_resolves_future`.
- STORY-006-AC-2 — unit, `src/ollama_llm_bench/backend/concurrency/tests/ test_cancellation_token.py`, `test_cancellation_level_is_monotonic_never_downgraded`.
- STORY-006-AC-3 — unit, same file, `test_raise_if_cancelled_and_level_query_properties`.
- STORY-006-AC-4 — unit, same file, `test_wait_returns_early_on_cross_thread_cancel`.
- STORY-006-AC-5 — unit, same file,
  `test_hard_cancel_hooks_invoked_once_removable_and_isolate_failures`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-006.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/concurrency/`.
- [ ] An architecture test confirms `backend/concurrency/` imports no Qt and no `asyncio`.
- [ ] Backend branch coverage for `backend/concurrency/` meets the Phase 1 ≥90% gate.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
