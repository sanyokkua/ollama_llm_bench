---
id: STORY-082
title: Stop per-task timeout exhaustion from tripping the provider circuit breaker
status: draft
spec_clauses:
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout
modules:
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-082-AC-1
  - STORY-082-AC-2
depends_on: []
adrs: []
owner: coder
estimate: S
---

# STORY-082 — Stop per-task timeout exhaustion from tripping the provider circuit breaker

## Goal

Fix a live specification violation in the benchmark pipeline: when a single task's inference times
out repeatedly and exhausts its retry ladder, the pipeline currently records that as a circuit-breaker
failure. The specification is explicit that a per-task timeout is a model-level signal handled by the
adaptive-timeout service and must never count toward the provider breaker — a single slow or stuck
model must not skip the provider's other models. This story corrects the dispatch so an exhausted
per-task timeout feeds only adaptive timeout, and proves the corrected behaviour with tests.

## In scope

- The exhausted-per-task-timeout branch of the pipeline's stability dispatch in
  `backend/benchmark_pipeline/_internal/`: on `HttpTimeoutError` after the retry ladder is exhausted,
  do **not** call `circuit_breaker.record_failure(provider_id)`; still record the timeout with the
  adaptive-timeout service and still contain the failure as a `FAILED_TIMEOUT` result.
- The tests proving the corrected behaviour.

## Out of scope

- The warmup-probe path at a model switch, which legitimately calls `record_failure` on a warmup
  timeout or transport error (a separate provider-attributable signal, `08_CIRCUIT_BREAKER.md` §6.4).
- The `FAILED_PROVIDER` path, which correctly counts toward the breaker and is unchanged.
- The adaptive-timeout escalation/exclusion algorithm itself — already delivered; this story only
  ensures the per-task timeout continues to reach it and stops reaching the breaker.

## Spec inputs

- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold` — a
  task ending in `FAILED_TIMEOUT` does **not** count toward the breaker (MISS-25); a timeout is a
  model-level signal handled by the adaptive-timeout service, so per-task timeouts never trip the
  breaker directly.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout` — per-task
  timeouts feed **only** adaptive timeout (which escalates the budget and can exclude the one model);
  the breaker's timeout-based signal comes exclusively from the warmup probe at a model switch, not
  from per-task `FAILED_TIMEOUT`.

## Design constraints

- `backend/benchmark_pipeline/` is Qt-free; the breaker and adaptive-timeout services are touched
  only on the dispatcher thread (D-R-01), which this change preserves.
- The change is confined to the exhausted-timeout branch; the containment result and run-advancement
  behaviour stay exactly as they are — only the erroneous `record_failure` call is removed.
- The breaker's `record_success`/`record_failure` accounting for `FAILED_PROVIDER` and warmup
  outcomes is untouched.

## Acceptance criteria

### STORY-082-AC-1

Given a per-task inference that exhausts its retry ladder with `HttpTimeoutError`,
when the pipeline handles the exhausted timeout,
then it does not call `circuit_breaker.record_failure(provider_id)` — the breaker's consecutive-failure
count for that provider is unchanged.

### STORY-082-AC-2

Given a per-task inference that exhausts its retry ladder with `HttpTimeoutError`,
when the pipeline handles the exhausted timeout,
then the result settles to `FAILED_TIMEOUT`, the adaptive-timeout service is informed of the timeout,
and the run advances to the next unit.

## Test plan

- STORY-082-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_stability_dispatch.py`,
  `test_exhausted_per_task_timeout_does_not_record_breaker_failure`.
- STORY-082-AC-2 — unit, same file,
  `test_exhausted_per_task_timeout_settles_failed_timeout_and_advances`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-082.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
