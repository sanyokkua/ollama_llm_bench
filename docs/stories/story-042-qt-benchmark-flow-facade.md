---
id: STORY-042
title: Provide the Qt-side benchmark flow facade over the pipeline and dispatcher thread
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#11-benchmark-pipeline-flow-api
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4-serial-execution-for-a-run-d-r-16
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38
modules:
  - adapters/qt_benchmark_flow/
acceptance_criteria:
  - STORY-042-AC-1
  - STORY-042-AC-2
  - STORY-042-AC-3
  - STORY-042-AC-4
depends_on:
  - STORY-029
  - STORY-030
  - STORY-041
owner: coder
estimate: M
---

# STORY-042 — Provide the Qt-side benchmark flow facade over the pipeline and dispatcher thread

## Goal

Give the UI a thin Qt-affine facade over the backend `BenchmarkFlowApi`: it owns the dedicated
pipeline dispatcher thread and the `TaskRunner`, forwards the fast-synchronous control/query
calls (`start`, `resume`, `pause`, `resume_paused`, `stop`, `shutdown`, `is_running`,
`current_run`) to the backend pipeline, and joins the dispatcher thread cleanly at shutdown. The
facade carries no business logic; the pipeline owns all run behaviour.

## In scope

- The `QtBenchmarkFlow` and its `make_qt_benchmark_flow` factory: a thin proxy that holds the
  backend `BenchmarkFlowApi` Protocol and the `TaskRunner`, and owns the single, named
  (`pipeline-dispatcher`), long-lived dispatcher thread created at construction.
- Forwarding each `BenchmarkFlowApi` control/query method through to the backend pipeline,
  preserving the fast-synchronous-on-GUI-thread contract (`start`/`resume` enqueue a command to
  the dispatcher thread and return promptly).
- Bounded graceful `shutdown(timeout_ms)`: cancel the token, stop accepting units, wait up to
  the timeout for in-flight work to settle and the dispatcher thread to be joined.

## Out of scope

- The pipeline's run loop, five-phase batching, admission gate, and never-raises containment —
  owned by STORY-029/STORY-030; this facade forwards to them.
- The `QThreadPool`/`QRunnable` `TaskRunner` implementation — owned by STORY-041 (this facade
  submits units through it).
- Marshalling run-domain events to the UI — that travels on the event bus via
  `adapters/qt_event_bus/` (STORY-040), not through this facade's return values.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#11-benchmark-pipeline-flow-api` — the exact
  `BenchmarkFlowApi` method surface, the fast-synchronous-on-GUI-thread contract for
  `start`/`resume`, the no-op-when-idle rules for `pause`/`resume_paused`/`stop`, the
  never-raises-to-caller guarantee, and the bounded `shutdown` semantics this facade forwards.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4-serial-execution-for-a-run-d-r-16` —
  strictly serial execution: at most one in-flight unit app-wide; no parallelism knob.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38` — the
  single dispatcher thread this facade owns, names, creates once, and joins at shutdown; it is
  the only thread that blocks on a unit's `Future`.

## Design constraints

- `adapters/qt_benchmark_flow/` imports PySide6 and the `backend/benchmark_pipeline` Protocol
  (`01_MODULE_INVENTORY.md` §5); it carries no business logic — a thin proxy only.
- The dispatcher thread is the single sanctioned standalone thread (DD-38): owned, named,
  created once, joined at shutdown; not an ad-hoc per-work thread.
- `start`/`resume` do not block on the run; they enqueue a command and return promptly.
- No `asyncio`; the facade never adds a second parallel-inference path.

## Acceptance criteria

### STORY-042-AC-1

Given the facade is constructed, when `start(request)` is called on the GUI thread, then the
call returns promptly with a run id (it does not block until the run finishes) and the run
command is handed to the dispatcher thread for execution.

### STORY-042-AC-2

For each control/query method, calling it on the facade forwards to the backend
`BenchmarkFlowApi` and returns its result unchanged, per this table:

| Facade call       | Backend call forwarded to |
| ----------------- | ------------------------- |
| `start(request)`  | `start(request)`          |
| `resume(run_id)`  | `resume(run_id)`          |
| `pause()`         | `pause()`                 |
| `resume_paused()` | `resume_paused()`         |
| `stop()`          | `stop()`                  |
| `is_running()`    | `is_running()`            |
| `current_run()`   | `current_run()`           |

### STORY-042-AC-3

Given a run is active, when `shutdown(timeout_ms)` is called, then the facade cancels the run,
waits at most `timeout_ms` for in-flight work to settle, and joins the dispatcher thread before
returning.

### STORY-042-AC-4

Given no run is active, when `pause()`, `resume_paused()`, or `stop()` is called, then the
facade forwards the call and it is a no-op that returns without raising (the idle no-op contract
is preserved through the facade).

## Test plan

- STORY-042-AC-1 — integration (`pytest-qt`), `tests/integration/test_qt_benchmark_flow.py`,
  `test_start_returns_promptly_and_hands_run_to_dispatcher`.
- STORY-042-AC-2 — table-driven unit (backend pipeline fake), colocated
  `src/ollama_llm_bench/adapters/qt_benchmark_flow/tests/test_facade_forwarding.py`,
  `test_control_and_query_calls_forward_to_backend`.
- STORY-042-AC-3 — integration (`pytest-qt`), same integration file,
  `test_shutdown_cancels_waits_and_joins_dispatcher_thread`.
- STORY-042-AC-4 — unit, same forwarding test file,
  `test_idle_pause_stop_are_noops_through_facade`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-042.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/qt_benchmark_flow/`.
- [ ] An architecture test confirms the facade holds no business logic (forwards to the backend
  pipeline) and imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
