---
id: STORY-023
title: Trip a consistently-failing provider out of a run and probe it before closing
status: done
spec_clauses:
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#62-the-three-states
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#63-state-diagram
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#67-per-provider-scope
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#7-configuration
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#9-threading-and-concurrency
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#18-provider-circuit-breaker
modules:
  - backend/circuit_breaker/
  - backend/settings/
acceptance_criteria:
  - STORY-023-AC-1
  - STORY-023-AC-2
  - STORY-023-AC-3
  - STORY-023-AC-4
  - STORY-023-AC-5
depends_on:
  - STORY-001
  - STORY-004
  - STORY-014
owner: coder
estimate: M
---

# STORY-023 — Trip a consistently-failing provider out of a run and probe it before closing

## Goal

Give the pipeline a per-provider circuit breaker that watches the stream of per-provider task
outcomes, trips a provider out of the run after a configured number of consecutive
provider-attributable failures, skips every remaining task against it for a fixed cooldown
window without a network call, then lazily admits exactly one real task as a liveness probe when
the cooldown elapses — closing the breaker on success or re-tripping it for a fresh window on
failure. This stops a genuinely down provider from grinding the whole run's time budget away,
while leaving every other targeted provider running at full speed.

## In scope

- The `ProviderCircuitBreaker` Protocol and its concrete implementation (`08-E` §18): `state`,
  `record_failure`, `record_success`, `should_skip`, and `cooldown_remaining_seconds`, over a
  per-provider record of `CircuitState`, a consecutive-failure counter, and the monotonic
  cooldown-start instant.
- The three-state machine `CLOSED → TRIPPED → PROBING → (CLOSED | TRIPPED)` of §6.2–§6.4: trip on
  the `failure_threshold`-th consecutive `CLOSED` failure; `record_success` resets the counter
  when `CLOSED` and closes the breaker when `PROBING`; `record_failure` while `PROBING` re-trips;
  a `record_failure` while `TRIPPED` is neutral skipped-task bookkeeping.
- The **lazy** `TRIPPED → PROBING` transition (§6.5), evaluated on every `state` / `should_skip`
  / `cooldown_remaining_seconds` query when `monotonic_ms() - cooldown_started >= cooldown_ms`,
  with the probe-slot bookkeeping: the first post-cooldown `should_skip` returns `False` (admits
  the one probe task), every subsequent query returns `True` until the probe resolves, and
  `cooldown_remaining_seconds` returns `None` once `PROBING`.
- Reading the three keys **once from the frozen run snapshot** at construction:
  `circuit_breaker.enabled` (default `true`), `circuit_breaker.failure_threshold` (default `5`),
  `circuit_breaker.cooldown_seconds` (default `60`) — and the inert no-op behaviour when
  `enabled` is `false` (§7).
- Making every state transition observable via `state()` / `should_skip()` /
  `cooldown_remaining_seconds()` immediately after the triggering call, so a caller (the future
  pipeline) can detect the transition and construct the composite `_model_stability_changed`
  event itself.
- The `make_circuit_breaker` factory on `api.py`, guarded by `icontract` on programmer invariants
  only, and `backend/circuit_breaker/testing.py`.

## Out of scope

- The pipeline's decision of which task outcomes to report as `record_failure` versus
  `record_success` (the `FAILED_PROVIDER`-counts / per-task `FAILED_TIMEOUT`-does-not / warmup-
  timeout-does / `FAILED_INFERENCE`-neutral / cancellation-neither classification of §6.4) —
  owned by `backend/benchmark_pipeline/`; this breaker counts only the clean success/failure
  verdicts it is told.
- The warmup liveness call itself and its adaptive-timeout budget — owned by the pipeline and
  STORY-022; the breaker performs no network work and holds no `LLMClient` (§6.6).
- The per-`(provider, model)` adaptive-timeout exclusion — owned by STORY-022; the two services
  share no state (§6.9).
- The Qt bridge marshalling `_model_stability_changed` to the Progress widget — a later
  adapter/UI phase.
- **Literal construction/emission of `ModelStabilityChangedEvent`.** That struct is composite —
  it also requires `model_name`/`model_consecutive_successes`/`model_promotion_threshold`,
  fields this module has no access to and, per §6.9, must not share state with
  (`backend/adaptive_timeout` owns them). Following the identical precedent already shipped in
  STORY-022 (which hit the same conflict and deferred literal event-bus emission to
  `backend/benchmark_pipeline/`), this module makes every transition observable through its
  Protocol's query methods instead; `backend/benchmark_pipeline/` combines this module's state
  with `AdaptiveTimeoutService`'s in a later phase and publishes the real composite event. No
  `backend/events` import appears in this module.

## Spec inputs

- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#62-the-three-states` — the `CLOSED` /
  `TRIPPED` / `PROBING` meanings and each state's `should_skip` value.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#63-state-diagram` — the exact transitions
  the `RuleBasedStateMachine` test must walk.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold` —
  the consecutive-failure counting, the trip on threshold, and the `record_failure` /
  `record_success` pseudocode per state.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing` —
  the lazy transition, the one-probe-slot rule, and the fixed (non-exponential) cooldown.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#67-per-provider-scope` — the per-`provider_id`
  independence and the run-scoped (no durable state) lifetime.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#7-configuration` — the three snapshot keys,
  their defaults, and the `enabled == false` inert behaviour.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#9-threading-and-concurrency` — the
  fast-synchronous, dispatcher-thread-only, lock-free, timer-free contract.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#18-provider-circuit-breaker` — the five method
  signatures, the `CircuitState` enum, and the never-raises rule.

## Design constraints

- `backend/circuit_breaker/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`ProviderId`, `BenchmarkRunSettingEntry`) and `backend/infra` (`Clock` for `monotonic_ms`). No
  PySide6, and no `backend/events` import — see the Out-of-scope note on deferred event
  emission; this module exposes observable state instead of constructing
  `ModelStabilityChangedEvent` itself.
- `CircuitState` is contract-local to this module (defined in `08-E` §18); the module introduces
  no new persisted enum.
- The breaker owns no thread, timer, or executor; the `TRIPPED → PROBING` move is evaluated
  lazily on query. All access is confined to the dispatcher thread, so it stays serialised and
  lock-free (§9) — the probe-slot bookkeeping is correct only under this single-threaded access.
- The `Clock` is injected and monotonic; the cooldown is measured with `monotonic_ms()`, never
  wall-clock.
- The breaker never raises; every operation is in-memory arithmetic (§8). An unseen `provider_id`
  reads as implicit `CLOSED`.
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-023-AC-1

Given any interleaving of `record_success`, `record_failure`, clock advances, and state queries
against one provider, the breaker's observable `(state, should_skip, cooldown_remaining_seconds)`
after each step matches the §6.3 state machine for every legal transition — walked by a
`RuleBasedStateMachine` whose rules are the three mutators, a monotonic clock advance, and the
three query methods.

### STORY-023-AC-2

Given a `CLOSED` provider, when `failure_threshold` consecutive `record_failure` calls are made
with no intervening `record_success`, then the breaker becomes `TRIPPED` on exactly the
`failure_threshold`-th call (`state() == TRIPPED`, `should_skip() == True` from that call
onward); a `record_success` at any count below the threshold resets the counter so no trip
occurs.

### STORY-023-AC-3

Given a `TRIPPED` provider whose cooldown has just elapsed, the probe-slot admission behaves per
this table across successive queries with no intervening outcome:

| Query sequence after `monotonic_ms() - cooldown_started >= cooldown_ms` | Result                                       |
| ----------------------------------------------------------------------- | -------------------------------------------- |
| first `should_skip`                                                     | `False` (this task is admitted as the probe) |
| `state` after that first query                                          | `PROBING`                                    |
| second and later `should_skip`                                          | `True` (no second task admitted)             |
| `cooldown_remaining_seconds` while `PROBING`                            | `None`                                       |

### STORY-023-AC-4

Given a `PROBING` provider, when `record_success` is reported, then the breaker moves to `CLOSED`
with a zero counter (`state() == CLOSED`, `should_skip() == False`); when `record_failure` is
reported instead, then the breaker re-trips to `TRIPPED` and stamps a fresh `cooldown_seconds`
window (`cooldown_remaining_seconds()` reports the full window again, not the elapsed remainder
of the prior one).

### STORY-023-AC-5

Given `circuit_breaker.enabled` is `false`, when `failure_threshold` or more `record_failure`
calls are made, then `state` stays `CLOSED`, `should_skip` stays `False`, and no
`_model_stability_changed` event is emitted; and given two providers, tripping one leaves the
other `CLOSED` — the two records are independent.

## Test plan

- STORY-023-AC-1 — property (`RuleBasedStateMachine` walking every legal transition with an
  injected fake monotonic clock), colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_state_machine.py`,
  `test_circuit_breaker_state_machine_matches_spec`.
- STORY-023-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_tripping.py`,
  `test_trips_on_exact_threshold_and_success_resets_counter`. Covers CB-02/CB-03.
- STORY-023-AC-3 — unit (table-driven over the query sequence with an advanced fake clock), same
  file, `test_lazy_probe_slot_admits_exactly_one_task`. Covers CB-04/CB-05/CB-06.
- STORY-023-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_probe_outcome.py`,
  `test_probe_success_closes_and_probe_failure_retrips`. Covers CB-07/CB-08.
- STORY-023-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_config_and_scope.py`,
  `test_disabled_breaker_is_inert_and_providers_are_independent`. Covers CB-10/CB-12.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-023.
- [x] A `RuleBasedStateMachine` Hypothesis test walks every legal transition of the §6.3 state
  machine (STORY-023-AC-1).
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/circuit_breaker/`.
- [x] An architecture test confirms `backend/circuit_breaker/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-023.
- [x] The module inventory is unchanged.

## Notes

- `just trace-check` still fails on the same three pre-existing, STORY-023-unrelated gaps
  already documented by STORY-003/STORY-005/STORY-010/STORY-013/STORY-014/STORY-016's own Notes
  sections (`EC-PERSIST-6` dangling row; `EC-PROV-1a`/`EC-RUN-1a` uncovered) — confirmed present
  before this story's work began (`git stash` + re-run reproduced the identical three failures).
  These trace to a permanent cross-reference gap between the read-only vendored
  `08-I_edge_cases.md` catalog and `06_EDGE_CASE_TO_TEST_MAPPING.md` (neither file may be edited
  in place per `repository-documentation.md`). STORY-023 itself has zero orphan clauses/ACs/
  tests — all 8 spec clauses and all 5 ACs show non-empty `tests:`/`stories:` lists in
  `traceability.yaml`.
- Per the two planning decisions recorded in this story's In-scope/Out-of-scope sections: this
  module emits no `_model_stability_changed` event and imports no `backend/events` symbol,
  making every transition observable via `state()`/`should_skip()`/`cooldown_remaining_seconds()`
  instead (mirroring STORY-022's identical precedent); and the three `circuit_breaker.*` settings
  keys were added to `backend/settings/_internal/registry.py`'s `DEFAULTS`/`PER_RUN_OVERRIDABLE`
  as part of this story (mirroring STORY-016's identical precedent for
  `provider.probe_timeout_ms`/`readiness.snapshot_staleness_ms`), which is why `modules:` lists
  `backend/settings/` alongside `backend/circuit_breaker/`.
