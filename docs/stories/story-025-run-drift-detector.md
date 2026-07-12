---
id: STORY-025
title: Detect environment-availability drift between a run snapshot and the live configuration
status: ready
spec_clauses:
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#3-outputs
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#61-check-1--provider-drift
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#62-check-2--test-model-drift
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#63-check-3--judge-model-drift
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#64-check-4--embedding-drift
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#65-assembly-and-ordering
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#8-error-handling
  - 11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#9-threading-and-concurrency
modules:
  - backend/run_drift/
acceptance_criteria:
  - STORY-025-AC-1
  - STORY-025-AC-2
  - STORY-025-AC-3
  - STORY-025-AC-4
  - STORY-025-AC-5
  - STORY-025-AC-6
depends_on:
  - STORY-001
  - STORY-016
owner: coder
estimate: M
---

# STORY-025 — Detect environment-availability drift between a run snapshot and the live configuration

## Goal

Before a stopped or failed run is resumed, answer the narrow question "is the run's frozen
configuration still satisfiable by the current environment?" — is each snapshot provider still
present, enabled, reachable, and env-var-resolvable; is each frozen test/judge/embedding model
still advertised — and return an ordered list of `DriftWarning` items the Resume Summary dialog
surfaces so the user can fix the environment, resume anyway, or cancel. The detector is strictly
read-only: it never modifies the run, the snapshot, the catalogs, or live settings, and it never
decides whether the resume proceeds; it reports availability drift only, never mere settings
differences (DD-57).

## In scope

- The `RunDriftDetector` Protocol and its concrete implementation (`make_run_drift_detector`),
  producing an ordered `tuple[DriftWarning, ...]` from a `BenchmarkRun` plus the already-gathered
  live provider catalog, live model catalog, process-environment view, and `AppReadinessSnapshot`.
- The `DriftWarning` struct and the `DriftKind` / `DriftSeverity` enums of §3, owned by this
  module — the spec states they are runtime DTOs produced fresh per resume and are **not**
  members of the persisted-enum catalog, so this module defines them.
- The four checks in order (§6): Check 1 provider drift (`PROVIDER_REMOVED` /
  `PROVIDER_NOW_DISABLED` / `PROVIDER_NOW_UNREACHABLE` / `PROVIDER_ENV_VAR_MISSING`, all
  `BLOCKING`); Check 2 test-model drift (`MODEL_NO_LONGER_AVAILABLE`, `BLOCKING`, skipped when the
  provider is already `BLOCKING`-warned); Check 3 judge-model drift (`JUDGE_MODEL_UNAVAILABLE`,
  `BLOCKING`, only when `eval.phase_judge_enabled` or `feature.judge_run_analysis_enabled` is
  true in the snapshot); Check 4 embedding drift (`EMBEDDING_NOW_UNREACHABLE` /
  `EMBEDDING_MODEL_UNAVAILABLE`, `BLOCKING`, only when the snapshot's `eval.phase_cosine_enabled`
  is true).
- The env-var check that resolves the frozen `api_key_raw` **name** against the process
  environment and tests set-and-non-empty only — never reading, logging, or returning the value.
- The `pending_results_affected` count per warning and the §6.5 ordering: `BLOCKING` before
  `WARNING`, then by `provider_id` (nulls last) then `model_name` (nulls last).
- The §8 downgrades: an incomplete run snapshot yields one `BLOCKING` `PROVIDER_REMOVED` with the
  incomplete-snapshot detail; an absent readiness snapshot downgrades reachability warnings to
  `WARNING` rather than falsely blocking; the detector never raises to the Resume use case.

## Out of scope

- The Resume Summary dialog surfacing (§6.6): the grouped severity panel, the "Resume anyway"
  confirmation gate, "Fix in Settings", and nesting model warnings under provider warnings — owned
  by `ui/resume_benchmark/`. See the note below on wiring that widget's dependency to this
  detector.
- Refreshing the readiness snapshot and gathering the live provider/model catalogs before
  invocation — the Resume use case's precondition step, owned by `backend/benchmark_pipeline/`;
  this story consumes those already-gathered inputs.
- The readiness probe that produces `AppReadinessSnapshot` / `ProviderHealth` — owned by
  STORY-016; this story consumes those DTOs.
- Any settings-difference detection — deliberately absent (DD-57); the run resumes on its frozen
  snapshot, so a live settings change is not drift.

## Spec inputs

- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#3-outputs` — the `DriftWarning` struct,
  the `DriftKind` / `DriftSeverity` enums, the "not persisted-catalog members" statement, and the
  ordering rule.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#61-check-1--provider-drift` — the four
  provider live-state conditions, their `DriftKind`/severity, and the env-var name-only check.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#62-check-2--test-model-drift` — the
  advertisement-only check and the skip-under-provider-block rule.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#63-check-3--judge-model-drift` — the
  judge-needed gate and the resolve-against-Check-1 rule.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#64-check-4--embedding-drift` — the
  cosine-needed gate and the frozen-pair-only check.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#65-assembly-and-ordering` — the sort and
  the empty-tuple-means-satisfiable postcondition, and the no-settings-difference rule.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#8-error-handling` — the incomplete-snapshot
  and stale-readiness downgrades and the never-raises rule.
- `11_Services_and_Algorithms/11_RUN_DRIFT_DETECTOR.md#9-threading-and-concurrency` — the
  synchronous, pure, read-only, idempotent contract.

## Design constraints

- `backend/run_drift/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`BenchmarkRun`, `ProviderConfig`, `AppReadinessSnapshot`, `ProviderHealth`, `ModelRole`, …)
  (`01_MODULE_INVENTORY.md` §4.4). No PySide6. No network I/O — it operates over already-gathered
  data.
- `DriftWarning` is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)`; `DriftKind` and
  `DriftSeverity` are `StrEnum`s owned by this module and not added to the persisted-enum catalog.
- The detector is pure with respect to application state: it makes no change to the run, snapshot,
  catalogs, or settings, and is idempotent — the same inputs always yield the same ordered tuple.
- The detector never raises to its caller; every un-evaluable dimension downgrades to a `WARNING`
  (§8).
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-025-AC-1

Given a run whose frozen snapshot is fully satisfied by the current environment in every checked
dimension, when the detector runs, then it returns an empty tuple.

### STORY-025-AC-2

Each provider live-state condition maps to the `DriftWarning` per this table (all `BLOCKING`),
and the `PROVIDER_ENV_VAR_MISSING` case never reads the resolved secret value into the warning:

| Provider live state                                                             | `DriftKind`                |
| ------------------------------------------------------------------------------- | -------------------------- |
| No live provider with that `provider_id`                                        | `PROVIDER_REMOVED`         |
| Live provider present but `enabled == False`                                    | `PROVIDER_NOW_DISABLED`    |
| Enabled but `ProviderHealth.reachable == False`                                 | `PROVIDER_NOW_UNREACHABLE` |
| Enabled and reachable but frozen `api_key_raw` names an env var now unset/empty | `PROVIDER_ENV_VAR_MISSING` |

### STORY-025-AC-3

Given a `TEST`-role model absent from its provider's live catalog, when that provider is not
itself `BLOCKING`-warned, then one `MODEL_NO_LONGER_AVAILABLE` (`BLOCKING`) is emitted with the
count of that target's retryable results; when the provider is already `BLOCKING`-warned, then no
separate model warning is emitted and the results are attributed to the provider warning.

### STORY-025-AC-4

The judge check runs only when the snapshot needs the judge, and the embedding check only when the
snapshot runs cosine, per this table:

| Snapshot flags                                                          | Judge check                            | Embedding check                |
| ----------------------------------------------------------------------- | -------------------------------------- | ------------------------------ |
| `eval.phase_judge_enabled` or `feature.judge_run_analysis_enabled` true | runs                                   | —                              |
| both judge flags false                                                  | skipped (no `JUDGE_MODEL_UNAVAILABLE`) | —                              |
| `eval.phase_cosine_enabled` true                                        | —                                      | runs                           |
| `eval.phase_cosine_enabled` false                                       | —                                      | skipped (no embedding warning) |

### STORY-025-AC-5

Given a live embedding selection that differs from the run's frozen `EMBEDDING`-role pair while
the frozen pair itself is still available and reachable, when the cosine phase is enabled, then no
embedding warning is emitted — the resumed cosine phase uses the frozen pair, so a live-selection
change is not drift (DD-57); and given a snapshot key that differs from the current default or
user-saved value, no warning of any kind is emitted.

### STORY-025-AC-6

Given a mix of `BLOCKING` and `WARNING` items, when the detector assembles its result, then the
tuple is ordered `BLOCKING` before `WARNING` and, within each severity, by `provider_id`
(nulls last) then `model_name` (nulls last); and given an absent readiness snapshot, reachability
warnings are emitted as `WARNING` rather than `BLOCKING` and the detector does not raise.

## Test plan

- STORY-025-AC-1 — unit, colocated `src/ollama_llm_bench/backend/run_drift/tests/test_no_drift.py`,
  `test_satisfiable_environment_returns_empty_tuple`. Covers T-1.
- STORY-025-AC-2 — unit (table-driven over the four provider conditions), colocated
  `src/ollama_llm_bench/backend/run_drift/tests/test_provider_drift.py`,
  `test_provider_condition_maps_to_drift_kind`. Covers T-2/T-3/T-4/T-5.
- STORY-025-AC-3 — unit, colocated
  `src/ollama_llm_bench/backend/run_drift/tests/test_model_drift.py`,
  `test_test_model_drift_and_skip_under_provider_block`. Covers T-6/T-7.
- STORY-025-AC-4 — unit (table-driven over the judge/cosine gate flags), colocated
  `src/ollama_llm_bench/backend/run_drift/tests/test_gated_checks.py`,
  `test_judge_and_embedding_checks_respect_snapshot_flags`. Covers T-8/T-9/T-10/T-12/T-13.
- STORY-025-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/run_drift/tests/test_not_drift.py`,
  `test_live_selection_and_settings_differences_are_not_drift`. Covers T-11/T-14.
- STORY-025-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/run_drift/tests/test_ordering_and_downgrade.py`,
  `test_ordering_is_stable_and_stale_readiness_downgrades_to_warning`. Covers T-15/T-16.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-025.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/run_drift/`.
- [ ] An architecture test confirms `backend/run_drift/` imports no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-025.
- [ ] The module inventory is unchanged.
