---
id: STORY-102
title: Pin the per-task-timeout contract; record the CB-14 residue
status: ready
spec_clauses:
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout
  - 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#11-test-cases
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3
modules:
  - backend/benchmark_pipeline/
acceptance_criteria:
  - STORY-102-AC-1
edge_cases:
  - EC-PROV-3
depends_on:
  - STORY-101
adrs:
  - ADR-0013
owner: tester
estimate: S
---

# STORY-102 — Pin the per-task-timeout contract; record the CB-14 residue

## Goal

Lock down, with a single conformance test that drives the real breaker state machine, the rule
STORY-101 just finished implementing: a per-task inference that exhausts its retry ladder with a
timeout must never record a breaker failure from the ordinary per-task dispatch path, in any of
the breaker's three states. This closes the loop on the fix by proving the contract holds
independent of routing, not just in the one state the original bug report happened to describe,
and records the changelog entry and the residual stale-spec-text observations a future reader
needs so the correction lands cleanly in STORY-103.

## In scope

- A new parametrized conformance test,
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_timeout_never_reaches_breaker.py`,
  proving that a per-task `HttpTimeoutError` which exhausts its retry ladder records zero
  breaker failures regardless of which of the three breaker states (`CLOSED`, `TRIPPED`,
  `PROBING`) the breaker is in at the time, driving the real `make_circuit_breaker` state
  machine rather than asserting against a fake breaker's call log alone.
- A `CHANGELOG.md` entry under `[Unreleased]` → `Fixed`, in Keep-a-Changelog position, carrying
  a `Per 11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md §N` citation.
- Story Notes recording the nine stale `08_CIRCUIT_BREAKER.md` spec sites (§6.2's `should_skip`
  column, §6.3's note, §6.5, §6.6, §10.2, §10.3, CB-05, CB-06, CB-14) in the "spec-hygiene
  observations (record only)" form STORY-074 established — observations for STORY-103 to act
  on, not work done here.

## Out of scope

- Any production-code change — this story is test-plus-docs only; STORY-100 and STORY-101
  already delivered the behaviour this story pins down.
- Editing `08_CIRCUIT_BREAKER.md` itself — owned by STORY-103, the one story in this plan
  sanctioned to touch the vendored specification.

## Spec inputs

- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#64-failure-counting-and-the-trip-threshold` —
  the rule this story pins: a task ending in `FAILED_TIMEOUT` does not count toward the breaker
  in any state, because a timeout is a model-level signal handled by adaptive timeout, not a
  provider-attributable failure.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#69-interaction-with-adaptive-timeout` — the
  grain distinction between adaptive timeout (per model) and the breaker (per provider) that
  this test's parametrization over all three breaker states exists to keep enforced.
- `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md#11-test-cases` — the CB-14 test-case row
  ("A `FAILED_TIMEOUT` task — Counts as a provider-attributable failure toward the threshold")
  that contradicts §6.4/§6.9 and this story's own test; recorded in Notes as one of the nine
  stale sites, corrected by STORY-103.
- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-3` — a provider tripping the breaker mid-run; this
  story's conformance test guards against a timeout ever contributing to that trip.

## Design constraints

- No production code changes in this story; `backend/benchmark_pipeline/` stays exactly as
  STORY-101 left it.
- The new test drives the real `ProviderCircuitBreaker` implementation via
  `make_circuit_breaker`, not a hand-rolled fake, so the assertion is against actual state-machine
  behaviour rather than a call-log stub that could silently drift from the real implementation.
- The `CHANGELOG.md` entry follows the existing `[Unreleased]` → `Fixed` section's citation style
  used by every other entry in that file.

## Acceptance criteria

### STORY-102-AC-1

For every breaker state in `{CLOSED, TRIPPED, PROBING}`, when a per-task inference exhausts its
retry ladder with `HttpTimeoutError` while the breaker is in that state, then the pipeline
records zero breaker failures — neither the `CLOSED`-state trip-threshold counter nor the
`PROBING`-state re-trip transition is triggered from the per-task dispatch path, in any of the
three states.

## Test plan

- STORY-102-AC-1 — unit (parametrized table-driven over `{CLOSED, TRIPPED, PROBING}`, real
  breaker), new colocated
  `src/ollama_llm_bench/backend/benchmark_pipeline/tests/test_timeout_never_reaches_breaker.py`,
  `test_exhausted_timeout_records_zero_breaker_failures_in_every_state`.
- EC-PROV-3 — covered by STORY-102-AC-1: a provider that trips (or is probing) is never further
  affected by an unrelated per-task timeout, so its recovery path stays uncorrupted.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-102.
- [ ] EC-PROV-3 has a passing test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] `CHANGELOG.md` carries a `[Unreleased]` → `Fixed` entry citing
  `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-102.
- [ ] The module inventory is unchanged.

## Notes

**Spec-hygiene observations (record only; no spec edits) — the CB-14 residue for STORY-103 to
act on:**

- `08_CIRCUIT_BREAKER.md` §6.2's `should_skip` column still describes the state where "the first
  post-cooldown query returns `False`, admitting the one probe task" — stale; per ADR-0013 and
  STORY-101, `should_skip` always returns `True` while `PROBING`.
- §6.3's state-diagram note ("Exactly one task is admitted as the probe") is stale for the same
  reason.
- §6.5 (the cooldown/probing-transition walkthrough) still describes the probe-slot admission
  window this plan removed.
- §6.6 ("Probe behaviour") still describes the probe as "simply the next real benchmark task the
  pipeline routes to the provider" — the core stale section ADR-0013 supersedes in place.
- §10.2's worked example ("Task 41 runs against the provider as the probe and completes") still
  narrates a real-task probe.
- §10.3's worked example ("Task 41 ends `FAILED_TIMEOUT`... the breaker... re-trips") is the
  same stale narration for the failed-probe case.
- Test-case row CB-05 ("Advance the clock past `cooldown_seconds`, then query `should_skip`...
  the first query returns `False`") is stale.
- Test-case row CB-06 ("A second `should_skip` while the probe task is still in flight... only
  one task is admitted as the probe") is stale.
- Test-case row CB-14 ("A `FAILED_TIMEOUT` task — Counts as a provider-attributable failure
  toward the threshold") directly contradicts §6.4/§6.9 and `08-I_edge_cases.md`'s own
  `EC-PROV-3` description, and contradicts this story's own STORY-102-AC-1; it is the specific
  row that motivated this story's title.
