---
id: STORY-015
title: Provide the application-wide single-inference gate with lease ownership and watchdog
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store
  - 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#414-inferenceactivitystore
  - 08_Cross_Cutting/08-I_edge_cases.md#ec-run-14--watchdog-auto-release-of-the-inference-activity-gate
  - 10_Domain_and_Data/02_DTOS_AND_ENUMS.md#78-inferenceactivitycontext-and-inferenceactivitystate
modules:
  - backend/stores/inference_activity/
acceptance_criteria:
  - STORY-015-AC-1
  - STORY-015-AC-2
  - STORY-015-AC-3
  - STORY-015-AC-4
  - STORY-015-AC-5
  - STORY-015-AC-6
edge_cases:
  - EC-RUN-14
depends_on:
  - STORY-001
  - STORY-003
  - STORY-004
owner: coder
estimate: M
---

# STORY-015 — Provide the application-wide single-inference gate with lease ownership and watchdog

## Goal

Enforce the app-wide rule that at most one inference-using activity — a benchmark run, a judge
analysis, a provider test, or a readiness probe — is in flight at any moment. The store is the one
atomic gate every inference caller acquires for the full duration of its activity and releases
when done, so two inference activities can never overlap, a crashed non-pipeline acquirer cannot
lock the gate forever, and a late `finally` can never steal a successor's hold.

## In scope

- The `InferenceActivityStore` **method-only** Protocol: `try_acquire(activity, context) -> GateLease | None`, `release(lease)`, `state() -> InferenceActivityState`, `is_busy() -> bool` —
  no `psygnal.Signal` on the contract (D-R-06).
- The concrete store: one internal `threading.Lock` making `try_acquire` an atomic test-and-set
  and `state`/`is_busy` locked reads; a monotonically-increasing per-acquisition `lease_id`; and
  lease-based ownership so `release` frees the gate only when the passed lease is the current
  holder.
- The **per-activity watchdog** auto-release: `JUDGE_ANALYSIS` at 10 minutes, `PROVIDER_TEST` at
  60 seconds, `READINESS_PROBE` at 30 seconds, each measured from `started_at`; `BENCHMARK_RUN`
  has **no** watchdog. The watchdog arms with the `GateLease` it observed and releases by calling
  `release(that_lease)`, so a stale lease no-ops.
- The `_inference_activity_changed` event publication on every acquire and every release
  (including a watchdog auto-release), carrying the `InferenceActivityState`, on the Qt-free
  `EventBus`.
- The `make_inference_activity_store` factory on the module's `api.py`, guarded by `icontract` on
  programmer invariants only.

## Out of scope

- The Qt marshalling of `_inference_activity_changed` onto the GUI thread and the immediate-check
  `is_inference_busy()` gateway — owned by `adapters/qt_inference_activity_bridge/` in a later
  phase (`01_MODULE_INVENTORY.md` §5).
- The orphan-run sweep that reconciles a `BENCHMARK_RUN` left held by a dead process — owned by
  the persistence/startup path (EC-PERSIST-2), not this store; `BENCHMARK_RUN` deliberately has no
  watchdog here.
- The callers that acquire the gate (the pipeline, run-analysis service, provider-test runner,
  readiness service) — later phases; STORY-016 is the first consumer wired to it.
- The `InferenceActivity`, `InferenceActivityContext`, `InferenceActivityState`, and `GateLease`
  DTO definitions — owned by STORY-001; this story consumes them.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store` — the method-only
  Protocol, the single-`threading.Lock` thread-safety rule, the lease-ownership semantics of
  `release` (a superseded/foreign lease is a logged no-op; idempotent), and the never-raises rule.
- `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#414-inferenceactivitystore` — the store's
  method surface, the five `InferenceActivity` coarse states, and the acquire/release event
  publication.
- `08_Cross_Cutting/08-I_edge_cases.md#ec-run-14--watchdog-auto-release-of-the-inference-activity-gate`
  — the exact per-activity watchdog timeouts, the `BENCHMARK_RUN`-has-none rule, and the
  arm-with-observed-lease / release-by-lease / warning-log behaviour when a watchdog fires.
- `10_Domain_and_Data/02_DTOS_AND_ENUMS.md#78-inferenceactivitycontext-and-inferenceactivitystate`
  — the exact shape of `InferenceActivityContext`, `InferenceActivityState`, and `GateLease`
  (`lease_id` increases monotonically per acquisition), and the runtime-only never-persisted rule.

## Design constraints

- `backend/stores/inference_activity/` is Qt-free and asyncio-free; it imports only
  `backend/infra` (`Clock` for the watchdog), `backend/domain`, `backend/events`, and `msgspec`
  (`01_MODULE_INVENTORY.md` §4.2). No PySide6, no `psygnal.Signal` on the Protocol.
- All four methods are safe to call from any thread; the one internal `threading.Lock` is the sole
  synchronisation, making the gate one of exactly two cross-thread locked objects in the app.
- The store never raises to its caller: a failed acquire returns `None`, a stale/foreign release
  is a logged no-op, `state`/`is_busy` always return.
- Ownership is the `GateLease`, not the `InferenceActivity` enum — a release carrying a superseded
  lease can never free a successor's hold.
- `icontract` on the `api.py` factory guards programmer invariants only — never the gate's runtime
  data (a failed acquire is data, not a contract violation).

## Acceptance criteria

### STORY-015-AC-1

Given the gate is `IDLE`, when `try_acquire(activity, context)` is called, then it returns a
`GateLease` whose `activity` matches, `state().current` becomes that activity with the passed
context, `is_busy()` is `True`, and exactly one `_inference_activity_changed` event is emitted.

### STORY-015-AC-2

For any number of threads calling `try_acquire` concurrently against an initially `IDLE` gate,
exactly one call returns a `GateLease` and every other call returns `None` — the gate is mutually
exclusive under concurrency and is never held by two activities at once.

### STORY-015-AC-3

Given a lease is the current holder, when `release(lease)` is called, then the gate returns to
`IDLE`, `is_busy()` is `False`, one `_inference_activity_changed` event is emitted, and a second
`release(lease)` with the same (now superseded) lease is a no-op that emits no further event.

### STORY-015-AC-4

Given activity A holds the gate under lease L1 and is released, and activity B then acquires it
under lease L2, when a late `release(L1)` arrives, then it is a logged no-op and B's hold under L2
is preserved (a superseded lease never frees a successor's hold).

### STORY-015-AC-5

For each non-pipeline activity, when it holds the gate longer than its watchdog timeout without
releasing, the watchdog auto-releases it by calling `release` with the lease it observed when
arming, per this table:

| Activity          | Watchdog timeout | Auto-released |
| ----------------- | ---------------- | ------------- |
| `BENCHMARK_RUN`   | none             | never         |
| `JUDGE_ANALYSIS`  | 10 minutes       | yes           |
| `PROVIDER_TEST`   | 60 seconds       | yes           |
| `READINESS_PROBE` | 30 seconds       | yes           |

On a fired watchdog the gate transitions to `IDLE`, a `_inference_activity_changed` event is
emitted, and a warning is logged naming the abandoned activity and its `started_at`.

### STORY-015-AC-6

Given a watchdog has auto-released an abandoned activity's lease, when the abandoned holder's own
late `release(lease)` runs afterwards, then it is a no-op, and a fresh `try_acquire` issued after
the watchdog fired succeeds normally.

## Test plan

- STORY-015-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/stores/inference_activity/tests/test_gate.py`,
  `test_acquire_holds_gate_and_emits_activity_changed`.
- STORY-015-AC-2 — concurrency unit (many threads racing `try_acquire`), same file,
  `test_gate_is_mutually_exclusive_under_concurrent_acquire`. This is the Phase-level
  gate-exclusivity concurrency test.
- STORY-015-AC-3 — unit, same file, `test_release_frees_gate_and_is_idempotent`.
- STORY-015-AC-4 — unit, same file,
  `test_superseded_lease_release_never_frees_successor_hold`.
- STORY-015-AC-5 — unit (table-driven over the four activities, injected `Clock`), colocated
  `src/ollama_llm_bench/backend/stores/inference_activity/tests/test_watchdog.py`,
  `test_watchdog_auto_release_per_activity`. Covers EC-RUN-14.
- STORY-015-AC-6 — unit, same file,
  `test_late_release_after_watchdog_noops_and_reacquire_succeeds`. Covers EC-RUN-14.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-015.
- [ ] EC-RUN-14 has a passing test.
- [ ] A concurrency test proves the gate is exclusive under concurrent `try_acquire` calls
  (STORY-015-AC-2).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for
  `backend/stores/inference_activity/`.
- [ ] An architecture test confirms the Protocol carries no `psygnal.Signal` and the module
  imports no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
  </content>
