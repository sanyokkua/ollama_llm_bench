---
id: STORY-029
title: Drive a run to a terminal status through the five-phase batched pipeline with pause, stop, and resume
status: done
spec_clauses:
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#3-the-five-phase-batched-pipeline
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#4-provider-and-model-grouping
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#5-per-task-result-lifecycle
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#8-pause-resume-and-stop
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#9-crash-recovery
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#10-terminal-status-resolution
  - 11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#62-serial-execution-d-r-16
  - 11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#68-pause-stop-and-resume-mechanics
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#4-preconditions
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#11-benchmark-pipeline-flow-api
modules:
  - backend/benchmark_pipeline/
  - backend/persistence/results/
acceptance_criteria:
  - STORY-029-AC-1
  - STORY-029-AC-2
  - STORY-029-AC-3
  - STORY-029-AC-4
  - STORY-029-AC-5
  - STORY-029-AC-6
  - STORY-029-AC-7
depends_on:
  - STORY-011
  - STORY-015
  - STORY-028
owner: coder
estimate: L
---

# STORY-029 — Drive a run to a terminal status through the five-phase batched pipeline with pause, stop, and resume

## Goal

Give the application its single backend run engine: a `BenchmarkFlowApi` that admits a run
under the single-inference gate, hands it to the dedicated dispatcher thread, and drives it
through the five phases in strict order — every eligible task of a phase completing before the
next phase begins, provider-then-model grouped, one inference in flight app-wide — persisting
each unit's result durably before the next starts. It honours a cooperative pause (finish and
save the in-flight unit), a hard stop (abort promptly, persist nothing for the in-flight unit),
and resume from the persisted rows, and it settles the run to exactly one persisted terminal
status per the DD-42 outcome matrix. The engine never raises to its caller.

## In scope

- The `BenchmarkFlowApi` Protocol (`08-E` §11) and its concrete implementation:
  `start(request) -> RunId`, `resume(run_id)`, `pause()`, `resume_paused()`, `stop()`,
  `shutdown(timeout_ms)`, `is_running()`, `current_run()`, with gate admission
  (`InferenceActivityStore.try_acquire(BENCHMARK_RUN)`) as the first synchronous step of
  `start`/`resume` (SPEC-036, DD-50) and lease release in the dispatcher's terminal `finally`.
- The five-phase batched dispatch loop on the dispatcher thread (DD-38): phase ordering with the
  batching rule (a phase fully drains before the next), provider-then-model grouping, and strict
  serial execution — submit one unit to the `TaskRunner`, block on its `Future`, classify,
  persist, then submit the next.
- Per-unit result-lifecycle transitions (`PENDING → RUNNING_INFERENCE → AWAITING_* → COMPLETED`
  or a retryable-terminal status), invoking the STORY-028 evaluators for the grading phases in
  `GRADED` and writing each phase's `ResultPatch` durably through the `ResultsStore` single DB
  writer.
- The run-start embedding fail-fast probe (DD-48): one `embed("probe")` under the held
  `BENCHMARK_RUN` gate before Phase 2 when the run needs embeddings, settling the run `FAILED`
  before inference on probe failure.
- Pause (soft cancel — finish and save the in-flight unit, park `INCOMPLETE`/in-memory `PAUSED`),
  stop (hard cancel — abort within `provider.hard_cancel_max_ms`, row stays `PENDING`, persist
  `STOPPED`), the Stop-during-draining-Pause soft→hard upgrade, and the DD-42 outcome matrix read
  from a single atomic `token.snapshot()`.
- Resume: a fresh `CancellationToken`, `ResultsStore.list_resumable_results` selection of
  `PENDING` + elected retryable-failure rows, `RUNNING_INFERENCE → PENDING` reset, and reuse of
  the original run's frozen settings snapshot; plus the crash-recovery interaction with
  `ResultsStore.recover_in_flight_results` at startup.
- Terminal status resolution (§10) and run-domain / stage / per-task event emission
  (`_stage_changed`, `_progress_updated`, `_task_completed`, `_run_paused`, `_run_stopped`, …)
  and the `emit_progress_during(...)` live-progress helper for the per-task main inference
  (`context=BENCHMARK_TASK`).
- The `make_benchmark_pipeline` factory and the never-raises exception-containment mechanism
  (DD-44, `08-E` §11a) on `api.py`, guarded by `icontract` on programmer invariants only.

## Out of scope

- The role=JUDGE per-task judge-call orchestration inside Phase 5, the adaptive-timeout budget
  request per unit, the circuit-breaker consultation, and the judge-model-exclusion /
  `FAILED_JUDGE_TIMEOUT` handling — owned by STORY-030 (depends on this story); this story wires
  the STORY-028 keyword/cosine/sanity evaluators and the judge evaluator's happy/transport paths,
  and leaves the timeout-ladder and exclusion mechanics to STORY-030.
- The `EmbeddingService`, the evaluators themselves, and the judge parser — owned by STORY-027
  and STORY-028; this story consumes their Protocols.
- The run-creation use case's snapshot building and the `ANTHROPIC`-embedding rejection — owned
  by `backend/settings/` (STORY-014, done) and the run-creation use case; this story trusts the
  frozen snapshot and does not re-validate business rules on it.
- The `TaskRunner`, dispatcher-thread construction, and Qt marshalling — owned by
  `backend/infra`, `adapters/qt_runnables/`, and `adapters/qt_event_bus/`; this story consumes
  the `TaskRunner` port and emits on the Qt-free bus.
- Resume-selection UI, run drift warnings, and clone/rename/delete use cases — later UI phases.

## Spec inputs

- `08_Cross_Cutting/08-B_benchmark_state_machine.md#3-the-five-phase-batched-pipeline` — the
  fixed phase order, the batching rule, and per-mode phase applicability.
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#4-provider-and-model-grouping` — the
  provider-then-model grouping and the no-mid-phase-provider-switch rule.
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#5-per-task-result-lifecycle` — the
  `ResultStatus` transitions and the terminal/non-terminal split.
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#8-pause-resume-and-stop` — pause/stop/resume
  semantics, the safe-boundary guarantee, and the resume row-selection algorithm.
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#9-crash-recovery` — the orphan-run sweep and
  the reset-to-`PENDING` rule.
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#10-terminal-status-resolution` — the
  pipeline-outcome → persisted-`RunStatus` mapping.
- `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#62-serial-execution-d-r-16` — the
  one-inference-in-flight, submit-await-persist-next serial loop.
- `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#68-pause-stop-and-resume-mechanics` — the
  DD-42 outcome matrix, the single atomic `token.snapshot()`, and the soft→hard upgrade.
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#4-preconditions` — the DD-48 run-start
  embedding fail-fast probe and its `FAILED`-before-inference behaviour.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#11-benchmark-pipeline-flow-api` — the
  `BenchmarkFlowApi` method contracts, the gate-admission-first rule, and the never-raises
  guarantee.

## Design constraints

- `backend/benchmark_pipeline/` is Qt-free and asyncio-free; it may not import a concrete
  provider adapter (`01_MODULE_INVENTORY.md` §4.4). It consumes Protocols only: `ResultsStore`,
  `RunsStore`, `TasksStore` (`backend/persistence/*`), `EmbeddingService`, the four evaluators
  (`backend/evaluation/`), `EventBus`, `InferenceActivityStore`, `TaskRunner`, `Clock`, and
  `CancellationToken`.
- `start`/`resume` are fast-synchronous on the GUI thread; only the dispatcher thread blocks on
  a unit's `Future.result()` (DD-38). No worker unit writes to the DB or emits a run-domain
  event (DD-41).
- **DD-42 outcome-matrix timing (gap resolution).** `token.snapshot()` is read exactly once per
  halt, immediately after the in-flight unit's `Future.result()` resolves (soft: unit saved;
  hard: discarded) and **before** any terminal status is persisted or terminal event emitted.
- The pipeline never raises to its caller; every failure becomes result-row / run-header data via
  the DD-44 containment mechanism (`08-E` §11a). A `ProgrammerError` is never caught.
- The `BENCHMARK_RUN` gate is held for the whole run and released in `finally` at the terminal
  status; it has no watchdog auto-release (orphan-run sweep handles process death).
- Resume reuses the original run's frozen settings snapshot, never live settings; a `COMPLETED`
  row (including one with a `FAIL` verdict) is never re-run.
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-029-AC-1

Given a `GRADED` run with all phases active, when the pipeline runs to completion, then no
result row enters a later phase's `AWAITING_*` status before every eligible row of the earlier
phase has left it — each phase is fully drained before the next begins — and no provider switch
occurs inside a `(provider, model)` group.

### STORY-029-AC-2

At every instant during a run at most one inference unit is in flight across the whole
application: the dispatcher submits exactly one unit to the `TaskRunner`, blocks on its
`Future`, persists the result through the `ResultsStore` single DB writer, and only then submits
the next — with no fan-out and no concurrency setting.

### STORY-029-AC-3

Given a run that needs embeddings, when the run-start `embed("probe")` fails, then the run
settles to persisted `RunStatus.FAILED` before any Phase 2 inference unit is submitted, with an
error naming the embedding pair; when the probe succeeds, Phase 2 proceeds.

### STORY-029-AC-4

Given a unit in flight, when the user requests Pause, then that unit runs to completion and its
result is durably persisted, no not-yet-submitted unit starts (its row stays `PENDING`), the
persisted `RunStatus` stays `INCOMPLETE`, and `_run_paused` is emitted; when the user requests
Stop instead, then the in-flight unit is aborted within `provider.hard_cancel_max_ms` with
nothing persisted for it (its row stays `PENDING`), and the persisted `RunStatus` becomes
`STOPPED`.

### STORY-029-AC-5

The persisted run outcome is derived from exactly one atomic `token.snapshot()` per halt per
this table, read after the in-flight unit settles and before any terminal write:

| `CancelLevel` | `CancelReason`              | Persisted outcome                                             |
| ------------- | --------------------------- | ------------------------------------------------------------- |
| `NONE`        | —                           | `COMPLETED` if every row is `COMPLETED`, else `STOPPED` (§10) |
| `SOFT`        | `USER_PAUSE` / `AUTO_PAUSE` | no terminal write; stays `INCOMPLETE`, parked `PAUSED`        |
| `HARD`        | `USER_STOP`                 | `STOPPED`                                                     |
| `HARD`        | `APP_SHUTDOWN`              | no terminal write; left `INCOMPLETE` for next-launch recovery |

### STORY-029-AC-6

Given a `STOPPED` or `FAILED` run, when it is resumed, then a fresh `CancellationToken` is
created, `list_resumable_results` selects the non-terminal rows plus the elected retryable-failure
rows, any `RUNNING_INFERENCE` row is reset to `PENDING`, every `COMPLETED` row is left untouched,
and the run's original frozen settings snapshot is reused rather than live settings.

### STORY-029-AC-7

For every taxonomy category except `ProgrammerError` raised by a pipeline dependency, the
invoked `BenchmarkFlowApi` method returns normally with the failure recorded as result-row or
run-header data (never propagated to the caller); a `ProgrammerError` is not caught.

## Test plan

- STORY-029-AC-1 — integration (inline-runner pipeline over fakes), colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_batching.py`,
  `test_phases_drain_in_order_and_grouping_holds`.
- STORY-029-AC-2 — integration, same directory
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_serial_execution.py`,
  `test_at_most_one_unit_in_flight_and_persist_before_next`.
- STORY-029-AC-3 — integration,
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_embedding_probe.py`,
  `test_run_start_embed_probe_fails_fast_before_inference`.
- STORY-029-AC-4 — integration,
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_pause_stop.py`,
  `test_pause_finishes_and_saves_stop_aborts_and_discards`.
- STORY-029-AC-5 — unit (table-driven over the outcome matrix), colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_outcome_matrix.py`,
  `test_dd42_outcome_matrix_from_single_snapshot`.
- STORY-029-AC-6 — integration,
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_resume.py`,
  `test_resume_selects_resumable_rows_and_reuses_snapshot`.
- STORY-029-AC-7 — unit (parametrized over taxonomy categories against rigged fakes), colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_never_raises.py`,
  `test_flow_api_never_raises_except_programmer_error`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-029.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/benchmark_pipeline/`.
- [x] An architecture test confirms `backend/benchmark_pipeline/` imports no Qt, no `asyncio`,
  and no concrete provider adapter.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-029.
- [x] The module inventory is unchanged.
