---
id: STORY-016
title: Aggregate provider and embedding health into one application-readiness snapshot
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#62-the-probe-of-one-provider
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#63-the-embedding-model-probe
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#64-probe_all--probing-every-provider-concurrently
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#65-aggregation-into-the-overall-verdict
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#66-coalescing-overlapping-probe-requests
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#7-configuration
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#9-threading-and-concurrency
  - 08_Cross_Cutting/08-I_edge_cases.md#ec-run-13--readiness-probe-requested-mid-benchmark
modules:
  - backend/readiness/
acceptance_criteria:
  - STORY-016-AC-1
  - STORY-016-AC-2
  - STORY-016-AC-3
  - STORY-016-AC-4
  - STORY-016-AC-5
  - STORY-016-AC-6
  - STORY-016-AC-7
  - STORY-016-AC-8
edge_cases:
  - EC-RUN-13
depends_on:
  - STORY-001
  - STORY-003
  - STORY-004
  - STORY-006
  - STORY-014
  - STORY-015
owner: coder
estimate: L
---

# STORY-016 — Aggregate provider and embedding health into one application-readiness snapshot

## Goal

Before a run starts, answer the narrow question "is each enabled provider reachable, and is the
embedding model reachable?" by probing every enabled provider and the embedding selection and
folding the results into one `AppReadinessSnapshot` of `READY`, `DEGRADED`, `NOT_READY`, or
`CHECKING`. The snapshot drives the status-bar health dot and the New Benchmark start gating; the
service never raises, never runs an automatic billable `embed()` call, and never overlaps a
benchmark run.

## In scope

- The `ReadinessService` Protocol and its concrete implementation: `snapshot()` (fast-synchronous
  cached read, `CHECKING` before the first probe), `probe(provider_id)` (blocking leaf unit), and
  `probe_all()` (blocking, dispatcher-orchestrated).
- **One-provider probe** — a registry lookup then `LLMClient.probe_health()`, with the
  no-client (`ConfigurationError`) case collapsed to a `MISSING_ENV`-style
  `ProviderHealth(reachable=False, …)` with no network call; every outcome returned as a
  `ProviderHealth`, never as an exception.
- **Handshake-only embedding probe (DD-48)** — verifies a selection exists, its provider is
  reachable in this batch, the client has an embedding surface, and (where discovery is supported)
  the selected model is listed; it never calls `embed()`.
- **`probe_all` orchestration on the dispatcher thread (DD-38/DD-40)** — the reachability
  handshakes fan out concurrently to the shared `TaskRunner` and the dispatcher joins their
  `Future`s (leaf probes never submit-and-wait); the single embedding probe runs once, serially,
  after the fan-out.
- **Aggregation (§6.5)** — a provider counts as healthy when `reachable`, regardless of
  `discovery_supported` or `model_count`; the four-state fold into `overall`.
- **Coalescing (§6.6)** — a `probe_all` issued while a batch is in flight waits on the shared
  `Future` and returns the same snapshot; exactly one batch runs and one event is emitted.
- **Single-inference gate integration** — `probe_all`/`probe` acquire
  `InferenceActivity.READINESS_PROBE` before any network call and release it in `finally`; a
  refused acquire (gate held by another activity) defers the request rather than queuing it
  (EC-RUN-13).
- The `_app_readiness_changed` event, emitted only when the recomputed snapshot differs from the
  cached one, coalesced at the bus to at most twice per second.
- The probe timeout and staleness settings read via `SettingsService`
  (`provider.probe_timeout_ms`, `readiness.snapshot_staleness_ms`); the `make_readiness_service`
  factory on `api.py`, guarded by `icontract` on programmer invariants only.

## Out of scope

- The New Benchmark widget's per-mode start-gating logic and the status-bar dot rendering — later
  UI phases; this story supplies the snapshot they gate on, not the gating.
- The provider registry, its `LLMClient` construction, and `probe_health` itself — owned by the
  provider-registry / provider-adapter stories; this story consumes their Protocols.
- The user-initiated embedding test and the run-start fail-fast `embed()` probe that catch a
  listed-but-cannot-embed endpoint — owned by the Settings dialog and the benchmark pipeline
  respectively (`06_EMBEDDING_SERVICE.md`, `04_EVALUATION_PIPELINE.md`).
- The `TaskRunner`/dispatcher primitives and the single-inference gate store — owned by STORY-006
  and STORY-015; this story orchestrates over them.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service` — the three method
  signatures, their threading kinds, and the never-raises rule.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#62-the-probe-of-one-provider` — the registry
  lookup, the no-client `MISSING_ENV` case, and the condition→`ProviderTestStatus` mapping.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#63-the-embedding-model-probe` — the
  handshake-only algorithm and the exact conditions under which `embedding_reachable` is `True`.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#64-probe_all--probing-every-provider-concurrently`
  — the dispatcher-orchestrated fan-out/join and the single serial embedding probe.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#65-aggregation-into-the-overall-verdict` — the
  `reachable`-means-healthy rule and the four-state fold.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#66-coalescing-overlapping-probe-requests` — the
  in-flight-shared-`Future` coalescing and its "collapses concurrent, not sequential" boundary.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#7-configuration` — the `provider.probe_timeout_ms`
  and `readiness.snapshot_staleness_ms` keys and the event-driven (never polled) rule.
- `11_Services_and_Algorithms/09_READINESS_PROBE.md#9-threading-and-concurrency` — the
  thread-affinity contract and the `READINESS_PROBE` gate acquire/release with deferral on refusal.
- `08_Cross_Cutting/08-I_edge_cases.md#ec-run-13--readiness-probe-requested-mid-benchmark` — the
  defer-not-queue behaviour when `BENCHMARK_RUN` holds the gate.

## Design constraints

- `backend/readiness/` is Qt-free and asyncio-free; it imports only `backend/provider_registry`,
  `backend/embedding`, `backend/settings`, `backend/stores/inference_activity`, `backend/events`,
  `backend/infra`, and `backend/domain` Protocols (`01_MODULE_INVENTORY.md` §4.2). No PySide6.
- `probe` is a leaf unit that never submits work to the `TaskRunner` and never blocks on a
  `Future`; only the dispatcher thread joins the fan-out `Future`s in `probe_all`.
- The automatic path never issues model compute: no `embed()` and no `chat` call is made across
  `snapshot`/`probe`/`probe_all` (DD-48).
- The service never raises; every failure — unreachable provider, unresolved key, missing
  embedding selection, a `PersistenceError` from `resolve_embedding_selection()` — is collapsed to
  readiness data.
- The service mutates no persistent state; `ProviderHealth` and `AppReadinessSnapshot` are never
  written to the database.
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-016-AC-1

Given no probe has completed, when `snapshot()` is called, then it returns an
`AppReadinessSnapshot` whose `overall` is `CHECKING`, synchronously and without probing.

### STORY-016-AC-2

The `overall` `ReadinessState` that `probe_all` computes is determined by the provider and
embedding results per this table:

| Enabled providers | Reachable providers | Embedding reachable | `overall`   |
| ----------------- | ------------------- | ------------------- | ----------- |
| 0                 | 0                   | (any)               | `NOT_READY` |
| N (>0)            | 0                   | (any)               | `NOT_READY` |
| N (>0)            | N (all)             | `True`              | `READY`     |
| N (>0)            | N (all)             | `False`             | `DEGRADED`  |
| N (>0)            | 1..N-1 (some)       | (any)               | `DEGRADED`  |

### STORY-016-AC-3

Each provider condition maps to the `ProviderHealth` / healthy-count contribution per this table,
and a provider counts as healthy whenever `reachable` is `True` regardless of `discovery_supported`
or `model_count`:

| Provider condition                                   | `reachable` | `discovery_supported` | `model_count` | Counts healthy |
| ---------------------------------------------------- | :---------: | :-------------------: | :-----------: | :------------: |
| Reachable, discovery supported, ≥1 model             |    True     |         True          |      >0       |      yes       |
| Reachable, discovery not supported (Anthropic-style) |    True     |         False         |     None      |      yes       |
| Reachable, discovery supported, 0 models             |    True     |         True          |       0       |      yes       |
| Reachable, discovery supported, listing call failed  |    True     |         True          |     None      |      yes       |
| Unreachable (refused / auth / deadline)              |    False    |         (any)         |     None      |       no       |
| Enabled but api-key env-var name unresolved          |    False    |         False         |     None      |       no       |

### STORY-016-AC-4

For the automatic readiness check across `snapshot`, `probe`, and `probe_all` at startup and on
registry reload, the `LLMClient` is never asked to `embed()` or `chat` — a spy asserts zero such
calls — and a selected embedding model that is listed but cannot embed still passes the automatic
handshake check (DD-48).

### STORY-016-AC-5

Given a second `probe_all()` is issued while the first batch is still in flight, when both
complete, then only one provider-probe batch ran, both callers receive the same
`AppReadinessSnapshot`, and exactly one `_app_readiness_changed` event is emitted.

### STORY-016-AC-6

Given a recomputed snapshot equal to the cached one, when `probe_all` finishes, then no
`_app_readiness_changed` event is emitted; given a recomputed snapshot that differs, exactly one
event is emitted.

### STORY-016-AC-7

Given the single-inference gate is held by `BENCHMARK_RUN`, when a readiness probe is requested,
then `try_acquire(READINESS_PROBE, …)` returns `None`, no network probe is issued, the request is
recorded as deferred (not queued), and it is re-attempted once the gate is `IDLE`.

### STORY-016-AC-8

Within one `probe_all` batch, the per-provider reachability handshakes run concurrently on
`TaskRunner` workers while the single embedding probe runs exactly once after the fan-out, no leaf
probe submits work to the pool or blocks on a `Future`, and the batch completes without deadlock
even with the pool saturated.

## Test plan

- STORY-016-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_snapshot.py`,
  `test_snapshot_is_checking_before_first_probe`. Covers RP-01.
- STORY-016-AC-2 — unit (table-driven over the aggregation combinations), colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_aggregation.py`,
  `test_overall_state_folds_provider_and_embedding_results`. This is the Phase-level
  ProviderTestStatus × overall-status table-driven test.
- STORY-016-AC-3 — unit (table-driven over the per-provider conditions), same file,
  `test_provider_condition_maps_to_health_and_healthy_count`.
- STORY-016-AC-4 — unit (spy on the `LLMClient` fake), colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_embedding_probe.py`,
  `test_automatic_check_never_issues_model_compute`. Covers RP-13.
- STORY-016-AC-5 — unit (concurrent `probe_all` callers), colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_coalescing.py`,
  `test_overlapping_probe_all_calls_coalesce_to_one_batch`. Covers RP-10.
- STORY-016-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_events.py`,
  `test_event_emitted_only_on_snapshot_change`. Covers RP-11.
- STORY-016-AC-7 — unit (gate pre-held by a fake), colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_gate_deferral.py`,
  `test_probe_deferred_when_gate_held_by_benchmark_run`. Covers EC-RUN-13.
- STORY-016-AC-8 — unit (dispatcher-thread orchestration with a saturated pool fake), colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_orchestration.py`,
  `test_probe_all_fans_out_concurrently_and_never_deadlocks`. Covers RP-18/RP-19.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-016.
- [x] EC-RUN-13 has a passing test.
- [x] A table-driven test covers every provider-condition and every aggregation combination from
  `09_READINESS_PROBE.md` §6.5 (STORY-016-AC-2, STORY-016-AC-3).
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/readiness/`.
- [x] An architecture test confirms `backend/readiness/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-016.
- [x] The module inventory is unchanged.

## Notes

- `just trace-check` still fails on the same three pre-existing, STORY-016-unrelated gaps
  already documented by STORY-003/STORY-005/STORY-010/STORY-013/STORY-014's own Notes sections
  (`EC-PERSIST-6` dangling row; `EC-PROV-1a`/`EC-RUN-1a` uncovered) — confirmed present before
  this story's work began (`git stash` + re-run reproduced the identical three failures). These
  trace to a permanent cross-reference gap between the read-only vendored `08-I_edge_cases.md`
  catalog and `06_EDGE_CASE_TO_TEST_MAPPING.md` (neither file may be edited in place per
  `repository-documentation.md`). STORY-016 itself has zero orphan clauses/ACs/tests — all 8
  ACs and EC-RUN-13 show non-empty `tests:` lists in `traceability.yaml`.
- During test-writing, a real implementation bug was found and fixed: `_probe_one` only caught
  `ConfigurationError`, so an arbitrary exception from a collaborator's `probe_health()` could
  propagate out of `probe()`/`probe_all()`, violating the "never raises" guarantee
  (STORY-016-AC-7's spirit and `09_READINESS_PROBE.md` §5). Fixed by collapsing any exception
  from `probe_health()` into an `UNREACHABLE`-shaped `ProviderHealth`, logged via `structlog`,
  mirroring the existing timeout-collapse pattern in `_await_health_result`.
- `backend/provider_registry/` and `backend/embedding/` are still stub packages with no story
  built yet, so `backend/readiness/protocols.py` declares narrow, readiness-local collaborator
  Protocols (`ReadinessLLMClient`, `ReadinessProviderRegistry`, `ReadinessEmbeddingSelector`,
  `ReadinessEmbeddingSelection`) rather than importing from those modules, following the same
  precedent as `backend/infra/protocols.py`'s `PlatformDetector`. When those modules' stories
  land, their concrete types will satisfy these Protocols structurally with no code change here;
  only `compose.py` will need updating to wire the real instances in.
  </content>
