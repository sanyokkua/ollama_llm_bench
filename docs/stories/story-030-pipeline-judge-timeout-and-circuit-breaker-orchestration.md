---
id: STORY-030
title: Orchestrate the judge phase with adaptive timeout, judge-model exclusion, and circuit-breaker consultation
status: done
spec_clauses:
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#65-stage-4--judge-phase
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#8-error-handling
  - 11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#66-batching-within-a-model-group
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#6-adaptive-timeout-state-machine
  - 08_Cross_Cutting/08-B_benchmark_state_machine.md#7-provider-circuit-breaker-state-machine
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#52-stage-and-progress
modules:
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-030-AC-1
  - STORY-030-AC-2
  - STORY-030-AC-3
  - STORY-030-AC-4
  - STORY-030-AC-5
depends_on:
  - STORY-022
  - STORY-023
  - STORY-029
owner: coder
estimate: L
---

# STORY-030 — Orchestrate the judge phase with adaptive timeout, judge-model exclusion, and circuit-breaker consultation

## Goal

Complete the benchmark pipeline's grading half by wiring the per-unit stability services into
its dispatch loop: request a per-attempt budget from the Adaptive Timeout Service for each
inference and each judge call, consult the Provider Circuit Breaker before submitting a unit and
report every clean outcome to both services, settle a judge call that exhausts its role=JUDGE
ladder to `FAILED_JUDGE_TIMEOUT`, exclude the judge model run-wide after the configured
consecutive max-budget timeouts (skipping the judge for the remaining tasks without aborting the
run), and support the stage-preserving retry of a judge-only failure. This is the orchestration
that turns the STORY-028 judge evaluator and the STORY-022/STORY-023 stability services into the
run's Phase 5 behaviour.

## In scope

- Per-unit consumption of the `AdaptiveTimeoutService` (`next_budget(provider_id, model_name, role, attempt_index)` with `role=INFERENCE` for the per-task inference call and `role=JUDGE`
  for the per-task judge call), and reporting each clean `record_success` / `record_timeout` on
  the dispatcher thread; embedding calls remain exempt (fixed budget).
- Per-unit consultation of the `ProviderCircuitBreaker` before submitting a unit (skip a tripped
  provider's remaining group units as provider failures without a network call), and reporting
  each clean success/failure outcome; a cancelled unit reports no outcome to either service.
- Per-task judge-timeout exhaustion: a judge call that exhausts its role=JUDGE ladder settles the
  result to `FAILED_JUDGE_TIMEOUT` with `error_kind = JUDGE_TIMEOUT` and `verdict = None`, the
  combination step is not applied, and the run continues.
- Run-wide judge-model exclusion: on crossing `eval.judge_timeout_consecutive_threshold`
  consecutive max-budget judge timeouts, emit `_judge_model_excluded` exactly once, set the
  pipeline's `judge_excluded` flag, settle every remaining judge-eligible task to
  `FAILED_JUDGE_TIMEOUT` directly (no judge call), and continue Phase 2/3 work — never aborting
  the run.
- Stage-preserving retry (DD-66): a row the Retry/Resume use case reset to `AWAITING_JUDGE_CHECK`
  re-enters the pipeline at the judge stage and runs only the judge against its preserved
  `sanitized_response`, while a row reset to `PENDING` re-runs the whole task; and the
  `FAILED_JUDGE_TIMEOUT` retryable-terminal class (DD-34) whose whole-task retry re-runs
  end-to-end.
- The judge-call `emit_progress_during(...)` invocation with `context=BENCHMARK_JUDGE`, and the
  `_model_stability_changed` composite event assembled from the two stability services' observable
  state.

## Out of scope

- The Adaptive Timeout Service and Provider Circuit Breaker algorithms themselves — owned by
  STORY-022 and STORY-023 (done); this story consumes their Protocols and reports outcomes.
- The judge evaluator's prompt assembly, parsing, and parse-retry — owned by STORY-028; this
  story governs only the timeout ladder, exclusion, and per-task terminal-status settling around
  the judge call.
- The five-phase batching skeleton, gate admission, pause/stop/resume mechanics, the DD-42
  outcome matrix, and crash recovery — owned by STORY-029 (this story builds on it).
- The Progress-widget stability boxes and event-log rendering — a later adapter/UI phase; this
  story only emits the Qt-free events.

## Spec inputs

- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#65-stage-4--judge-phase` — the role=JUDGE
  adaptive-timeout ladder, per-task exhaustion → `FAILED_JUDGE_TIMEOUT`, and the run-wide
  judge-model-exclusion sequence with `_judge_model_excluded`.
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#8-error-handling` — the
  `FAILED_JUDGE_TIMEOUT` handling, the excluded-mid-run handling, the transport-failure fallback,
  and the DD-66 stage-preserving retry note.
- `11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md#66-batching-within-a-model-group` — the
  before-submit circuit-breaker check, the per-unit `next_budget` request, and the
  dispatcher-thread-only reporting to both stability services (a cancelled unit reports nothing).
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#6-adaptive-timeout-state-machine` — the
  per-target promotion/escalation/exclusion behaviour the pipeline drives via recorded outcomes.
- `08_Cross_Cutting/08-B_benchmark_state_machine.md#7-provider-circuit-breaker-state-machine` —
  the trip/probe/close consultation the pipeline performs per provider group.
- `08_Cross_Cutting/08-J_event_bus_catalog.md#52-stage-and-progress` — the `_judge_model_excluded`
  and `_model_stability_changed` payloads, emitters, and one-shot semantics.

## Design constraints

- `backend/benchmark_pipeline/` is Qt-free and asyncio-free and imports no concrete provider
  adapter (`01_MODULE_INVENTORY.md` §4.4). It consumes the `AdaptiveTimeoutService` and
  `ProviderCircuitBreaker` Protocols; it constructs neither.
- The `AdaptiveTimeoutService` and `ProviderCircuitBreaker` are touched **only on the dispatcher
  thread**, never inside a worker unit, so their state stays serialized and lock-free.
- **DD-66 stage-preserving retry (gap resolution).** The pipeline's terminal `FAILED_JUDGE_TIMEOUT`
  class always retries whole-task end-to-end (DD-34); the *stage-preserving* re-entry is driven
  by the Retry/Resume use case's explicit reset of a row to `AWAITING_JUDGE_CHECK`, which re-runs
  **only** the judge against the preserved `sanitized_response`. The pipeline honours whichever
  reset status it finds; it does not itself decide to preserve a stage. This reading is consistent
  with the DD-66 name (stage-preserving) and with `04_EVALUATION_PIPELINE.md` §8 and
  `08-B` §5, which state the `FAILED_JUDGE_TIMEOUT` *class* retry re-runs the whole task while a
  row reset to `AWAITING_JUDGE_CHECK` runs only the judge.
- The role=JUDGE and role=INFERENCE buckets are independent (DD-34): judge exclusion never
  excludes the same `(provider, model)` at role=INFERENCE.
- `_judge_model_excluded` fires at most once per `BENCHMARK_RUN` activity, on the
  not-excluded → excluded transition of the role=JUDGE bucket.
- `icontract` on the touched `api.py` surface guards programmer invariants only.

## Acceptance criteria

### STORY-030-AC-1

For each per-task inference and per-task judge call, the dispatcher requests the per-attempt
budget from the `AdaptiveTimeoutService` with the matching role (`INFERENCE` / `JUDGE`) and
reports the clean outcome (`record_success` / `record_timeout`) exactly once; an embedding call
requests no adaptive budget, and a cancelled unit reports no outcome to the service.

### STORY-030-AC-2

Before submitting a unit, the dispatcher consults the `ProviderCircuitBreaker`: given a tripped
provider, when the next unit for that provider's group would be submitted, then it is recorded as
a provider failure with no network call; and each clean unit outcome is reported to the breaker
exactly once, while a cancelled unit reports nothing.

### STORY-030-AC-3

Given a per-task judge call that exhausts its role=JUDGE adaptive-timeout ladder, the result
settles to `FAILED_JUDGE_TIMEOUT` with `error_kind = JUDGE_TIMEOUT` and `verdict = None`, the
verdict-combination step is not applied to it, and the pipeline continues to the next task.

### STORY-030-AC-4

Given the role=JUDGE bucket crosses `eval.judge_timeout_consecutive_threshold` consecutive
max-budget timeouts, when exclusion is signalled, then `_judge_model_excluded` is emitted exactly
once, every remaining judge-eligible task settles to `FAILED_JUDGE_TIMEOUT` directly with no
judge call attempted, Phase 2/3 work for those tasks still runs, and the run does not abort.

### STORY-030-AC-5

On retry, a row's re-entry is determined by its reset status per this table:

| Reset status the retry/resume use case produced                | Pipeline re-entry                                                                                                              |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `PENDING`                                                      | re-runs the whole task end-to-end (re-inference + re-grade)                                                                    |
| `AWAITING_JUDGE_CHECK`                                         | runs only the judge against the preserved `sanitized_response`; inference/keyword/cosine outputs on the row are not recomputed |
| `FAILED_JUDGE_TIMEOUT` selected for retry (reset to `PENDING`) | re-runs the whole task end-to-end (DD-34)                                                                                      |

## Test plan

- STORY-030-AC-1 — integration (inline-runner pipeline over fakes recording calls), colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_adaptive_timeout_consumption.py`,
  `test_per_role_budget_requested_and_outcome_reported`.
- STORY-030-AC-2 — integration, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_circuit_breaker_consultation.py`,
  `test_tripped_provider_skipped_and_outcomes_reported`.
- STORY-030-AC-3 — integration, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_judge_timeout.py`,
  `test_per_task_judge_timeout_settles_failed_judge_timeout`.
- STORY-030-AC-4 — integration, same file,
  `test_run_wide_judge_exclusion_skips_remaining_and_continues`.
- STORY-030-AC-5 — integration (table-driven over the reset statuses), colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_stage_preserving_retry.py`,
  `test_retry_re_entry_by_reset_status`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-030.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/benchmark_pipeline/`.
- [x] An architecture test confirms the `AdaptiveTimeoutService` and `ProviderCircuitBreaker` are
  touched only on the dispatcher thread (no worker-unit access) —
  `tests/architecture/test_stability_dispatcher_thread_only.py`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-030.
  (`just trace-check` still fails on three pre-existing, unrelated edge-case gaps —
  `EC-PERSIST-6`, `EC-PROV-1a`, `EC-RUN-1a` — tracked as backlog before this story started; see
  `docs/stories/` history / project memory `project_preexisting_gate_failures`.)
- [x] The module inventory is unchanged.

## Verification notes (fix-up pass)

- `just check` initially failed `mypy --strict` on two colocated test doubles
  (`test_serial_execution.py::_InlineTaskRunner`, `test_batching_drain.py::_InlineTaskRunner`)
  typed `Callable[[], ResultPatch]`/`Future[ResultPatch]`, which no longer structurally satisfies
  `run_phase`/`run_all_phases`'s `TaskRunner[object]` parameter. Retyped both to
  `Callable[[], object]`/`Future[object]`, matching the convention already used by this
  package's shared `conftest.py` double and by `backend/readiness`. No behavior change.
- Added `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_judge_target.py` (2 tests)
  to directly cover `resolve_judge_target`'s both-branches (judge entry present / absent) —
  the only real coverage gap left in a STORY-030-touched file (`judge_target.py` was 78%
  covered, missing its `None`-return guard clause). Both AC-3 and AC-4 now additionally cite
  these tests.
- `just check` (lint, format-check, typecheck, import-check, arch-test, test): all green —
  733 architecture tests, 749 in `tests/unit tests/integration src`.
- `just coverage-layers`: backend layer 91% (>= 90% required). The UI-layer sub-gates still
  fail with "No data to report" — pre-existing, documented backlog (no `ui/` controllers exist
  yet at this phase of the rewrite), not a STORY-030 regression.
- `just trace` / `just trace-check`: traceability.yaml regenerated; STORY-030's AC-1..AC-5 all
  map to passing tests with zero gaps. The only `trace-check` failures are the three
  pre-existing EC gaps noted above.
