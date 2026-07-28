---
id: STORY-101
title: Remove the real-task probe admission from the breaker
status: done
spec_clauses:
  - 08_Cross_Cutting/08-F_spec_issues_log.md#dd-71--circuit-breaker-probing-uses-a-lightweight-liveness-probe-not-a-full-task-2026-06-06
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#62-the-three-states
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#63-state-diagram
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3
modules:
  - backend/circuit_breaker/
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-101-AC-1
  - STORY-101-AC-2
  - STORY-101-AC-3
  - STORY-101-AC-4
  - STORY-101-AC-5
  - STORY-101-AC-6
  - STORY-101-AC-7
  - STORY-101-AC-8
edge_cases:
  - EC-PROV-3
depends_on:
  - STORY-100
adrs:
  - ADR-0013
owner: coder
estimate: L
---

# STORY-101 — Remove the real-task probe admission from the breaker

## Goal

Finish DD-71's adoption by deleting the breaker's old real-task probe-slot mechanism, now that
STORY-100 has landed the dedicated lightweight probe that replaces it. `should_skip` becomes a
pure function of the breaker's state, with no side effect and no probe slot to claim — while
`PROBING`, it always returns `True`, and the pipeline's per-row `run_provider_probe` hook is the
only thing that ever resolves a `PROBING` provider. This story also carries the supersession
bookkeeping the removal requires: two already-`done` stories (STORY-023, STORY-082) each own an
acceptance criterion that only made sense under the old real-task-probe design, and this story
retires those two stories, restates every one of their still-valid criteria as its own, and
repoints the tests that prove them, so the traceability gate never has a moment where a `done`
story's acceptance criterion has no proving test.

## In scope

- `backend/circuit_breaker/_internal/state.py`: remove `probe_slot_claimed` from
  `_ProviderRecord` — there is no longer a slot to claim.
- `backend/circuit_breaker/_internal/breaker.py`: `should_skip`'s `PROBING` branch collapses to
  `return True` unconditionally, making `should_skip` a pure function of `state()` with no side
  effect; drop the `probe_slot_claimed` resets in `_trip`, `record_success`, and
  `_maybe_transition_to_probing`.
- `backend/circuit_breaker/protocols.py`: docstring-only correction — `PROBING` admits no task;
  the probe is issued by the pipeline (DD-71, ADR-0013). No method is added or resignatured.
- `backend/circuit_breaker/__init__.py`: correct the module docstring, which currently says the
  breaker "lazily admits exactly one real task as a liveness probe."
- `backend/benchmark_pipeline/_internal/stability_dispatch.py`: delete the PROBING conditional
  entirely, returning the exhausted-timeout branch to
  `except HttpTimeoutError: return on_timeout_exhausted()`; reduce the comment to the §6.4/§6.9
  rationale plus a DD-71 note; delete the now-unused `CircuitState` import. The
  `except AppError:` branch is left exactly as it is — it is now correct, because a real task can
  no longer be a probe.
- Supersession bookkeeping: flip `docs/stories/story-023-provider-circuit-breaker.md` and
  `docs/stories/story-082-breaker-ignores-per-task-timeout.md` to `status: superseded`, each
  with a Notes line naming STORY-101 as the superseding story; repoint the nine `Proves:`
  docstring lines that currently name a retired `STORY-023-AC-3`/`STORY-082-AC-3` (or a carried
  criterion under its old id) onto the matching STORY-101 criterion below.

## Out of scope

- The dedicated probe itself (`lightweight_call.py`, `provider_probe.py`, the `before_row` hook)
  — delivered by STORY-100, a prerequisite for this story so the tree is never left with a
  `PROBING` state that has no resolver.
- The parametrized zero-breaker-failure conformance test across all three breaker states, and
  the `CHANGELOG.md` entry — owned by STORY-102.
- Correcting `08_CIRCUIT_BREAKER.md`'s stale real-task-probe prose (§6.2's `should_skip` column,
  §6.3's note, §6.5, §6.6, §10.2, §10.3, CB-05, CB-06, CB-14) — owned by STORY-103, the one
  story in this plan sanctioned to edit the vendored specification.

## Spec inputs

- `08_Cross_Cutting/08-F_spec_issues_log.md#dd-71--circuit-breaker-probing-uses-a-lightweight-liveness-probe-not-a-full-task-2026-06-06` —
  the decision this deletion completes: the probe is a lightweight call, never a real task, so
  `should_skip` need never carve out an admission window for one.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#62-the-three-states` — the three-state
  meanings this story's state machine and `should_skip` behaviour must continue to match, minus
  the retired probe-slot bookkeeping.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#63-state-diagram` — the
  `CLOSED → TRIPPED → PROBING → (CLOSED | TRIPPED)` transitions the `RuleBasedStateMachine` test
  (STORY-101-AC-1) walks; the transitions themselves are unchanged by this story, only the
  probe-slot side effect on `should_skip` is removed.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#65-cooldown-and-the-transition-to-probing` —
  the lazy `TRIPPED → PROBING` transition this story preserves; per ADR-0013's precedence
  ruling, DD-71 governs the parts of this clause's prose that still describe an admitted probe
  task.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout` — the
  rule that a per-task timeout feeds only adaptive timeout, never the breaker, which
  STORY-101-AC-6/AC-7 (carried from STORY-082) continue to prove.
- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3` — a provider tripping the breaker mid-run; this
  story keeps that recovery path correct once the real-task admission window is gone.

## Design constraints

- `backend/circuit_breaker/` stays Qt-free and asyncio-free; access remains confined to the
  dispatcher thread, so `should_skip` losing its side effect only simplifies an already
  single-threaded, lock-free contract.
- `should_skip` must be idempotent: calling it any number of times with no intervening
  `record_success`/`record_failure` returns the same value every time, in every state — the
  property the old probe-slot design violated for `PROBING` and the property this story's tests
  must assert directly.
- No `ProviderCircuitBreaker` Protocol method is added, removed, or resignatured — the Protocol
  is frozen verbatim in `08_Cross_Cutting/08-E_interfaces_contracts.md` §18.
- `stability_dispatch.py`'s `except AppError:` branch is untouched; only the PROBING conditional
  on the `HttpTimeoutError` branch and the now-unused `CircuitState` import are removed.
- The supersession of STORY-023 and STORY-082 is data bookkeeping (front-matter `status` plus a
  Notes line, and repointed test docstrings) — it changes no acceptance-criterion wording that
  is carried forward, only which story id the criterion and its test are attributed to.

## Acceptance criteria

### STORY-101-AC-1

Given any interleaving of `record_success`, `record_failure`, clock advances, and state queries
against one provider, the breaker's observable `(state, should_skip, cooldown_remaining_seconds)`
after each step matches the §6.3 state machine for every legal transition — walked by a
`RuleBasedStateMachine` whose rules are the three mutators, a monotonic clock advance, and the
three query methods.

### STORY-101-AC-2

Given a `CLOSED` provider, when `failure_threshold` consecutive `record_failure` calls are made
with no intervening `record_success`, then the breaker becomes `TRIPPED` on exactly the
`failure_threshold`-th call (`state() == TRIPPED`, `should_skip() == True` from that call
onward); a `record_success` at any count below the threshold resets the counter so no trip
occurs.

### STORY-101-AC-3

Given a provider in the `PROBING` state, when `should_skip` is queried any number of times with
no intervening `record_success`/`record_failure`, then every query returns `True` and no query
mutates the breaker's record — `should_skip` is a pure function of `state()` with no probe-slot
side effect, so it never admits a benchmark task.

### STORY-101-AC-4

Given a `PROBING` provider, when `record_success` is reported, then the breaker moves to
`CLOSED` with a zero counter (`state() == CLOSED`, `should_skip() == False`); when
`record_failure` is reported instead, then the breaker re-trips to `TRIPPED` and stamps a fresh
`cooldown_seconds` window (`cooldown_remaining_seconds()` reports the full window again, not the
elapsed remainder of the prior one).

### STORY-101-AC-5

Given `circuit_breaker.enabled` is `false`, when `failure_threshold` or more `record_failure`
calls are made, then `state` stays `CLOSED`, `should_skip` stays `False`, and no
`_model_stability_changed` event is emitted; and given two providers, tripping one leaves the
other `CLOSED` — the two records are independent.

### STORY-101-AC-6

Given a per-task inference that exhausts its retry ladder with `HttpTimeoutError`, when the
pipeline handles the exhausted timeout, then it does not call
`circuit_breaker.record_failure(provider_id)` — the breaker's consecutive-failure count for that
provider is unchanged.

### STORY-101-AC-7

Given a per-task inference that exhausts its retry ladder with `HttpTimeoutError`, when the
pipeline handles the exhausted timeout, then the result settles to `FAILED_TIMEOUT`, the
adaptive-timeout service is informed of the timeout, and the run advances to the next unit.

### STORY-101-AC-8

Given a provider whose circuit breaker is in the `PROBING` state, when the dispatcher's per-row
loop reaches a row targeting that provider, then `should_skip` returns `True` before
`run_task_with_stability` is ever invoked for that row — the row is skipped as an ordinary
tripped/probing skip, and neither `record_success` nor `record_failure` is called from the
per-task dispatch path for it.

## Test plan

- STORY-101-AC-1 — property (`RuleBasedStateMachine`), colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_state_machine.py`,
  `test_circuit_breaker_state_machine_matches_spec` — repointed from `STORY-023-AC-1`.
- STORY-101-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_tripping.py`,
  `test_trips_on_exact_threshold_and_success_resets_counter` — repointed from `STORY-023-AC-2`.
- STORY-101-AC-3 — property/unit, same files: a new `should_skip_is_idempotent` Hypothesis rule
  and a `probing_implies_no_admission` invariant in `test_state_machine.py`, plus
  `test_tripping.py`'s `test_cooldown_elapse_moves_to_probing_and_admits_no_task` (rewritten
  from the old `test_lazy_probe_slot_admits_exactly_one_task`, repointed from `STORY-023-AC-3`).
- STORY-101-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_probe_outcome.py`,
  `test_probe_success_closes_and_probe_failure_retrips` — repointed from `STORY-023-AC-4`.
- STORY-101-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/circuit_breaker/tests/test_config_and_scope.py`,
  `test_disabled_breaker_is_inert_and_providers_are_independent` — repointed from
  `STORY-023-AC-5`.
- STORY-101-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_stability_dispatch.py`,
  `test_exhausted_per_task_timeout_does_not_record_breaker_failure` — repointed from
  `STORY-082-AC-1`.
- STORY-101-AC-7 — unit, same file,
  `test_exhausted_per_task_timeout_settles_failed_timeout_and_advances` — repointed from
  `STORY-082-AC-2`.
- STORY-101-AC-8 — unit, same file, driving the real `ProviderCircuitBreaker`,
  `test_probing_provider_task_is_skipped_and_reports_nothing` — new test replacing the retired
  `STORY-082-AC-3`'s `test_probing_provider_whose_probe_task_times_out_re_trips_the_breaker`.
- EC-PROV-3 — covered by STORY-101-AC-3/AC-4/AC-8 together: a tripped provider still recovers
  correctly once the real-task admission window is removed.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-101.
- [x] EC-PROV-3 has a passing test.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [x] `docs/stories/story-023-provider-circuit-breaker.md` and
  `docs/stories/story-082-breaker-ignores-per-task-timeout.md` are `status: superseded`,
  each naming STORY-101 as the superseding story.
- [x] All nine `Proves:` docstring lines that named a retired criterion are repointed onto their
  STORY-101 equivalent, with no orphan test left naming a superseded story's AC.
- [x] The traceability record validates with no orphan clause and no orphan test, and no error
  arising from the two supersessions.
- [x] The module inventory is unchanged.

## Notes

- **Implementation landed 2026-07-28.** Deleted `_ProviderRecord.probe_slot_claimed`
  (`_internal/state.py`) and every reader/writer of it in `_internal/breaker.py`:
  `should_skip`'s `PROBING` branch now collapses to `return record.state is not CircuitState.CLOSED`, with the resets removed from `_trip`, `record_success`, and
  `_maybe_transition_to_probing`. A whole-tree grep for `probe_slot_claimed` after the change
  returns zero matches. `protocols.py` and `__init__.py` got docstring-only corrections; no
  `ProviderCircuitBreaker` method was added, removed, or resignatured.
  `benchmark_pipeline/_internal/stability_dispatch.py`'s PROBING conditional and its
  `CircuitState` import were deleted; the `except HttpTimeoutError:` branch returned to
  `return on_timeout_exhausted()`, and the `except AppError:` branch was left byte-for-byte
  unchanged.
- **TDD evidence for the two new state-machine rules.** With the pre-fix `breaker.py`/`state.py`
  restored via `git stash` (new tests kept in place), `uv run pytest src/ollama_llm_bench/backend/circuit_breaker/tests/test_state_machine.py src/ollama_llm_bench/backend/circuit_breaker/tests/test_tripping.py -q` fails: the
  `probing_implies_no_admission` invariant and `test_cooldown_elapse_moves_to_probing_and_admits_no_task`
  both fail with `assert False is True` on the old `should_skip`'s first post-cooldown call (it
  returned `False` to admit the one probe task). Isolating `should_skip_is_idempotent` alone
  (invariant `probing_implies_no_admission` temporarily disabled) reproduces the same failure
  independently: `assert first == second` fails with `False == True` on the old implementation —
  confirming the idempotence rule by itself would have caught the original bug class. Restoring
  the fixed `breaker.py`/`state.py` returns both files to green
  (`uv run pytest src/ollama_llm_bench/backend/circuit_breaker src/ollama_llm_bench/backend/benchmark_pipeline -q` → 114 passed).
- **Eight acceptance criteria, estimate `L`** — the project owner decided that retiring
  `STORY-023` and `STORY-082` must not silently drop the still-valid acceptance criteria they
  own today. Six of this story's eight criteria are carried forward verbatim from those two
  already-`done` stories; only two criteria (`AC-3`, `AC-8`) are newly written for this story's
  own scope. Since eight criteria exceed the `M` bound of six (per `02_STORY_FORMAT.md` §7), the
  estimate is `L`.
