---
id: STORY-082
title: Stop per-task timeout exhaustion from tripping the provider circuit breaker
status: done
spec_clauses:
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#66-probe-behaviour
modules:
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-082-AC-1
  - STORY-082-AC-2
  - STORY-082-AC-3
edge_cases:
  - EC-PROV-3
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
  call `circuit_breaker.record_failure(provider_id)` only when the breaker is in the PROBING state
  (resolving a timed-out probe per §6.6); otherwise do **not** call it. Still record the timeout with
  the adaptive-timeout service and still contain the failure as a `FAILED_TIMEOUT` result in every
  case.
- The tests proving the corrected behaviour, including the PROBING-state probe-resolution case
  (STORY-082-AC-3).

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
  from an ordinary CLOSED-state per-task `FAILED_TIMEOUT`.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing` — a
  TRIPPED breaker whose cooldown has elapsed lazily moves to PROBING and admits exactly one task as
  the live probe.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#66-probe-behaviour` — the probe's outcome resolves
  the breaker: success closes it, failure re-trips it with a fresh cooldown; this is the mechanism a
  timed-out probe must also drive, or the probe slot stays claimed forever with no further probe ever
  admitted.

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

### STORY-082-AC-3

Given a provider whose circuit breaker is in the PROBING state and whose admitted probe task
exhausts its retry ladder with `HttpTimeoutError`, when the pipeline handles the exhausted timeout,
then it resolves the probe by recording a breaker failure, so the breaker re-trips with a fresh
cooldown and the provider can be probed again — rather than leaving the probe slot claimed and the
provider permanently un-probeable.

## Test plan

- STORY-082-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_stability_dispatch.py`,
  `test_exhausted_per_task_timeout_does_not_record_breaker_failure`.
- STORY-082-AC-2 — unit, same file,
  `test_exhausted_per_task_timeout_settles_failed_timeout_and_advances`.
- STORY-082-AC-3 — unit, same file, driving the real `ProviderCircuitBreaker` state machine,
  `test_probing_provider_whose_probe_task_times_out_re_trips_the_breaker`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-082.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

- **Judge-role scope decision.** The fix removes the `circuit_breaker.record_failure(provider_id)`
  call from the exhausted-timeout branch of `run_task_with_stability`, and that function serves
  both `role=INFERENCE` and `role=JUDGE` calls — the deletion (now conditional on the breaker being
  PROBING, see the review-fix note below) applies to judge-model timeouts too. This is a deliberate
  reading of the spec, not an oversight: a judge timeout has its own model-level remedy, independent
  of the provider breaker — the judge model is excluded after
  `eval.judge_timeout_consecutive_threshold` consecutive max-budget timeouts. The story text above
  only calls out the inference case explicitly; this note records that the wider blast radius
  (covering judge calls as well) was a considered decision, not an accident of where the code
  happened to live.
- **AC-2 test-strength decision.** The first draft of the AC-2 test used `retry_count=0`, which
  produces a policy with a single attempt — technically hits the `HttpTimeoutError` branch but only
  trivially satisfies the criterion's "exhausts its retry ladder" wording, since there is no ladder
  to exhaust. On review, the project owner decided to strengthen the test to drive a real
  two-attempt retry ladder instead, accepting the extra ~1 second of real backoff sleep this adds to
  the suite, so the test genuinely proves the exhausted-ladder path rather than a same-thing
  single-attempt path.
- **Review-fix wave: the original deletion was unconditional and broke probe resolution.** Two
  independent reviewers found that removing `circuit_breaker.record_failure(provider_id)`
  unconditionally (not just for the CLOSED-state trip-threshold case this story targets) meant a
  timed-out PROBING-state probe task reported nothing to the breaker at all. `record_failure` is the
  only mechanism that resolves a failing probe (`08_CIRCUIT_BREAKER.md` §6.6): with the call gone,
  `probe_slot_claimed` stayed set forever, no further probe was ever admitted, and every remaining
  task on that provider was skipped for the rest of the run with no recovery — the model warmup path
  cannot rescue this either, since `run_model_warmup` only runs when the breaker is CLOSED. The fix
  makes the deletion conditional: `record_failure` is called only when `circuit_breaker.state(...) is CircuitState.PROBING`. Verified against `_ProviderCircuitBreakerImpl.record_failure`
  (`backend/circuit_breaker/_internal/breaker.py`): the PROBING branch calls `self._trip(record)`,
  which sets `state`/`cooldown_started_ms`/`probe_slot_claimed` but never touches
  `consecutive_failures` — so a PROBING-state `record_failure` re-trips the breaker with a fresh
  cooldown without incrementing the CLOSED-state consecutive-failure counter that drives the trip
  threshold. Per-task timeouts still never count toward that threshold; only a genuinely
  PROBING-state timeout now resolves the probe. This added STORY-082-AC-3 and its test
  `test_probing_provider_whose_probe_task_times_out_re_trips_the_breaker`, which drives the real
  `ProviderCircuitBreaker` state machine (trip -> cooldown elapsed -> PROBING -> probe times out ->
  re-tripped) rather than a fake, so it proves actual recovery, not just that a call was made.
- **A spec contradiction this story resolved silently, which a future reader will trip over.**
  Within `08_CIRCUIT_BREAKER.md`, §6.4 (line ~183) and §6.9 (line ~249) state that a per-task
  `FAILED_TIMEOUT` does **not** count toward the breaker (MISS-25) — which is what this story
  implements for the CLOSED-state trip-threshold counter. But §6.6 (line ~215) and the test-case
  table row **CB-14** (line ~341, "A `FAILED_TIMEOUT` task — Counts as a provider-attributable
  failure toward the threshold") say the opposite, unqualified. This story took the §6.4/§6.9 side
  for CLOSED-state threshold counting while preserving §6.6's probe-resolution rule (a PROBING-state
  timeout does resolve the probe via `record_failure`, which is a distinct code path from the
  CLOSED-state trip-threshold counter). CB-14 remains a live, misleading row that should be corrected
  in a separate, controlled spec-correction pass — it was not, and must not be, edited as part of
  this fix (the spec tree is read-only).
- **A second spec inconsistency worth an owner decision.** §1/§5 (DD-71) describe the breaker's
  probe as a lightweight warmup-style liveness call, while §6.6 describes it as simply the next real
  benchmark task admitted through the pipeline. The code (and this fix) implements §6.6's real-task
  probe — the PROBING conditional lives in `run_task_with_stability`, the ordinary per-task dispatch
  path. If the project ever adopts DD-71's lightweight-probe design instead, this story's PROBING
  conditional should move into a dedicated probe path (mirroring how `run_model_warmup` already has
  its own, separate `record_failure` call for the warmup-liveness signal) rather than living inside
  ordinary per-task dispatch.
- **A pre-existing gap this story did not introduce and does not fix.** The neutral-outcome branch
  (`except AppError:` in `run_task_with_stability`, immediately below the `except HttpTimeoutError:`
  clause this story touches) also returns without reporting anything to the breaker. So a probe task
  that ends in a neutral (non-timeout, non-transient) outcome likewise leaves the probe slot claimed
  with no resolution. Per §6.6 the next task should become the probe in that case instead. This
  predates STORY-082, is out of this fix wave's scope, and belongs in its own follow-up story.
- **Preserved warmup signal.** `backend/benchmark_pipeline/_internal/warmup.py` keeps its own,
  separate `circuit_breaker.record_failure(provider_id)` call on a warmup timeout or transport
  error. That call does not go through `run_task_with_stability` and was deliberately left
  untouched by this story, so the breaker's legitimate timeout-based signal — a provider whose
  model fails to even warm up at a model switch — still trips the breaker as designed.
