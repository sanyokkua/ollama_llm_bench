---
id: STORY-022
title: Compute per-role adaptive timeout budgets and track per-model exclusion
status: ready
spec_clauses:
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#13-per-role-bucket-independence
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#61-per-bucket-state
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#62-state-machine
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#63-the-escalation-ladder-per-role
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#64-recording-an-outcome
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#7-configuration
  - 11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#9-threading-and-concurrency
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#17-adaptive-timeout-service
modules:
  - backend/adaptive_timeout/
acceptance_criteria:
  - STORY-022-AC-1
  - STORY-022-AC-2
  - STORY-022-AC-3
  - STORY-022-AC-4
  - STORY-022-AC-5
  - STORY-022-AC-6
depends_on:
  - STORY-001
  - STORY-004
  - STORY-014
owner: coder
estimate: M
---

# STORY-022 — Compute per-role adaptive timeout budgets and track per-model exclusion

## Goal

Give the pipeline a per-`(provider_id, model_name, role)` timeout budget that starts at a
configured minimum, escalates across retries toward a configured maximum when calls time out,
promotes a last-known-good budget when a call succeeds, and excludes a model from one role after
a run of consecutive maximum-budget timeouts — so one slow-but-capable model converges on the
budget that works for it while one genuinely hung model can neither stall the run nor be excluded
by a heavy-but-succeeding pattern. The `INFERENCE` and `JUDGE` roles keep fully independent state
buckets: a model excluded as a judge stays usable for inference, and vice versa.

## In scope

- The `AdaptiveTimeoutService` Protocol and its concrete implementation
  (`08-E` §17): `next_budget`, `record_success`, `record_timeout`, `is_excluded`, and
  `model_state`, over the per-`(provider, model, role)` `TimeoutState` bucket.
- Reading the two parallel parameter sets **once from the frozen run snapshot** at construction:
  the `role=INFERENCE` `benchmark.*` ladder and the `role=JUDGE` `eval.judge_timeout_*` ladder
  (§7); each `role` selects its own parameter set and bucket.
- The escalation ladder of §6.3:
  `budget = floor + (ceil - floor) × min(attempt_index - 1, steps) / steps`, with
  `floor = last_known_good_ms`, `ceil = role.max × 1000`, `steps = role.escalation_steps`, then
  clamped into `[role.min × 1000, role.max × 1000]`; attempt 1 and `steps == 0` and
  `floor >= ceil` all collapse to `floor`.
- The `record_outcome` bookkeeping of §6.4 behind the two façade methods: a `SUCCESS` promotes
  `last_known_good_ms` (never lowers it) and resets the consecutive-max counter; a `TIMEOUT` at
  the role's max increments the counter and excludes at the role's `consecutive_threshold`; a
  sub-max `TIMEOUT` escalates state but never touches the counter; an already-`EXCLUDED` bucket
  ignores late outcomes.
- The four-node state machine (`FRESH → PROMOTED → AT_MAX → EXCLUDED`) surfaced as
  `AdaptiveTimeoutModelState` (`OK`/`WARN`/`EXCLUDED`) via `model_state`.
- The `make_adaptive_timeout_service` factory on `api.py`, guarded by `icontract` on programmer
  invariants only, and `backend/adaptive_timeout/testing.py`.

## Out of scope

- The Phase 2 inference loop and Phase 4 judge loop that consume `next_budget`, build
  `BenchmarkResultAttempt` rows, and apply the exclusion handoff of §6.5 (marking pending
  results `FAILED_TIMEOUT` / `FAILED_JUDGE_TIMEOUT`, emitting `_model_stability_changed` /
  `_judge_model_excluded`) — owned by `backend/benchmark_pipeline/` in a later phase; this story
  produces only the budget and the per-role exclusion verdict.
- The resume replay that reconstructs `TimeoutState` from persisted attempt/judge-metadata rows
  (§9) — orchestrated by the pipeline's resume use case; this story provides the `record_*`
  façades the replay drives.
- The provider circuit breaker's warmup-timeout signal — owned by STORY-023; per-task
  `FAILED_TIMEOUT` feeds only this service, never the breaker.
- The `run_analysis` service's `role=RUN_ANALYSIS` bucket wiring — this story's per-role state
  machine already supports an independent third bucket, but the Run Analysis Service that drives
  it is a later phase.

## Spec inputs

- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#13-per-role-bucket-independence` — the
  `(provider, model, role)` keying and the independence of the INFERENCE and JUDGE buckets.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#61-per-bucket-state` — the `TimeoutState`
  fields (`state`, `last_known_good_ms`, `consecutive_max_timeouts`) and their initial values.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#62-state-machine` — the exact
  `FRESH`/`PROMOTED`/`AT_MAX`/`EXCLUDED` transitions the property test must walk.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#63-the-escalation-ladder-per-role` — the
  budget formula, the attempt-1/`steps == 0`/`floor >= ceil` collapse cases, and the clamp.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#64-recording-an-outcome` — the SUCCESS /
  TIMEOUT / ERROR branches, the "promote never demote" and "strictly-consecutive-at-max" rules,
  and the `record_success` / `record_timeout` façade mapping.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#7-configuration` — the eight per-run
  snapshot keys and their defaults per role.
- `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md#9-threading-and-concurrency` — the
  synchronous, single-owner, lock-free, no-I/O contract.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#17-adaptive-timeout-service` — the five method
  signatures, `AdaptiveTimeoutModelState`, and the never-raises rule.

## Design constraints

- `backend/adaptive_timeout/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`AdaptiveTimeoutRole`, `AttemptOutcome`, `ProviderId`, `ModelName`,
  `BenchmarkRunSettingEntry`) and `backend/infra` (`01_MODULE_INVENTORY.md` §4.4). No PySide6.
- `AdaptiveTimeoutRole` and `AttemptOutcome` are consumed from `backend/domain/` (STORY-001);
  `AdaptiveTimeoutModelState` is contract-local to this module. The module defines no new
  persisted enum.
- The service is pure in-memory bookkeeping: no database handle, no I/O, no locking; called only
  from the dispatcher thread, one `(target, role)` bucket at a time (§9).
- The service never raises to its caller; a degenerate `role.min > role.max` snapshot is valid —
  the clamp caps every budget at `role.max` and a warning is logged, not raised (§8).
- `next_budget` returns seconds; the caller multiplies by 1000 when crossing to the LLM client.
- `icontract` on the `api.py` factory guards programmer invariants only — never a snapshot value
  or an outcome report.

## Acceptance criteria

### STORY-022-AC-1

For every `(role, attempt_index)` drawn from a fresh bucket with any valid per-role min/max/steps
configuration, the budget `next_budget` returns is always within `[role.min, role.max]` seconds
inclusive, equals `role.min` at `attempt_index == 1`, and lands exactly on `role.max` at
`attempt_index == 1 + role.escalation_steps`.

### STORY-022-AC-2

Given an ordered sequence of recorded outcomes for one `(provider, model, role)` bucket, the
bucket's `state`, `last_known_good_ms`, and consecutive-max-timeout counter after each outcome
match the state machine of §6.2 for every legal transition — walked by a `RuleBasedStateMachine`
whose rules are `record_success`, `record_timeout` (at max and sub-max), and `next_budget`.

### STORY-022-AC-3

The effect of one recorded outcome on the consecutive-max-timeout counter and
`last_known_good_ms` is determined by the outcome per this table, for a bucket at
`last_known_good_ms = LKG` with counter `C`:

| Recorded outcome | Budget of the attempt | Counter after | `last_known_good_ms` after |
| ---------------- | --------------------- | ------------- | -------------------------- |
| `SUCCESS`        | any                   | `0`           | `max(LKG, observed_ms)`    |
| `TIMEOUT`        | at `role.max`         | `C + 1`       | `LKG`                      |
| `TIMEOUT`        | below `role.max`      | `C`           | `LKG`                      |
| `ERROR`          | any                   | `C`           | `LKG`                      |

### STORY-022-AC-4

Given a bucket at the role's maximum budget, when `record_timeout` is reported for the
`role.consecutive_threshold`-th consecutive at-max timeout with no success in between, then
`is_excluded(provider, model, role)` returns `True` on exactly that report and not before, and
any `SUCCESS` before the threshold resets the counter so exclusion does not occur.

### STORY-022-AC-5

Given a `(provider, model)` used at both roles, when the `JUDGE` bucket reaches `EXCLUDED`, then
`is_excluded(provider, model, JUDGE)` is `True` while `is_excluded(provider, model, INFERENCE)`
is `False` — and each role's `last_known_good_ms` and counter evolve independently of the other.

### STORY-022-AC-6

Given a bucket that is already `EXCLUDED`, when any further outcome is recorded for it, then the
bucket's state, `last_known_good_ms`, and counter are unchanged and no exception is raised; and
given a snapshot where `role.min > role.max`, every `next_budget` result is `<= role.max` seconds
and the service does not raise.

## Test plan

- STORY-022-AC-1 — property (Hypothesis over role parameters × attempt_index), colocated
  `src/ollama_llm_bench/backend/adaptive_timeout/tests/test_ladder_bounds.py`,
  `test_next_budget_stays_within_bounds_and_lands_on_max`. Covers T-1/T-2/T-13.
- STORY-022-AC-2 — property (`RuleBasedStateMachine` walking every legal transition), colocated
  `src/ollama_llm_bench/backend/adaptive_timeout/tests/test_state_machine.py`,
  `test_timeout_state_machine_matches_spec`.
- STORY-022-AC-3 — unit (table-driven over the four outcome/budget cases), colocated
  `src/ollama_llm_bench/backend/adaptive_timeout/tests/test_record_outcome.py`,
  `test_recorded_outcome_updates_counter_and_lkg`. Covers T-4/T-5/T-6/T-11.
- STORY-022-AC-4 — unit, same file,
  `test_exclusion_after_exactly_threshold_consecutive_max_timeouts`. Covers T-7/T-8/T-9.
- STORY-022-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/adaptive_timeout/tests/test_role_independence.py`,
  `test_judge_exclusion_leaves_inference_bucket_usable`. Covers T-16.
- STORY-022-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/adaptive_timeout/tests/test_error_handling.py`,
  `test_excluded_bucket_ignores_late_outcomes_and_degenerate_config_is_clamped`. Covers
  T-12/T-13.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-022.
- [x] A `RuleBasedStateMachine` Hypothesis test walks every legal transition of the §6.2 state
  machine (STORY-022-AC-2).
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/adaptive_timeout/`.
- [x] An architecture test confirms `backend/adaptive_timeout/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-022.
- [x] The module inventory is unchanged.

**Implementation status:** Implementation is complete — all six acceptance criteria have
passing tests, `just check` and `just trace`/`just trace-check` are green (the three
pre-existing edge-case-catalog gaps `just trace-check` reports are unrelated to this story and
predate it). `status` is deliberately left as `ready`, not `done`, pending the
`spec-conformance-reviewer` gate per the story workflow.

Two pre-DD-65 documentation gaps in the vendored spec were identified during implementation and
did not block this story (see the coder's implementation plan for detail): (1)
`07_ADAPTIVE_TIMEOUT.md` §8's error table still says "the `AdaptiveTimeoutRole` enum has exactly
two members" — stale text; the rest of that document, DD-65, and the already-implemented
`backend/domain/models.py` (STORY-001) confirm the 3-member model (`INFERENCE`, `JUDGE`,
`RUN_ANALYSIS`) this story implements. (2) `08-E_interfaces_contracts.md` §17 still describes the
pre-DD-65 "shared JUDGE bucket" model; `07_ADAPTIVE_TIMEOUT.md` is unambiguous that DD-65
supersedes it. Both are pre-existing spec-text staleness, not user-facing ambiguity requiring a
decision.
