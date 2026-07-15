---
id: STORY-035
title: Generate the consolidated mode-aware run-analysis narrative
status: done
spec_clauses:
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#61-applicability-gate
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#61a-acquire-the-single-inference-gate
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#62-aggregate-the-run
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#63-build-the-prompt
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#64-call-the-model-and-post-process
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#65-regeneration-behaviour
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#8-error-handling
  - 11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#11-test-cases
modules:
  - backend/run_analysis/
acceptance_criteria:
  - STORY-035-AC-1
  - STORY-035-AC-2
  - STORY-035-AC-3
  - STORY-035-AC-4
  - STORY-035-AC-5
  - STORY-035-AC-6
  - STORY-035-AC-7
  - STORY-035-AC-8
depends_on:
  - STORY-001
  - STORY-015
  - STORY-017
  - STORY-022
owner: coder
estimate: L
---

# STORY-035 — Generate the consolidated mode-aware run-analysis narrative

## Goal

Give a finished run its single consolidated prose narrative: a service that loads the run's data,
builds a bounded mode-aware digest, calls a user-chosen `(provider, model)` analysis model exactly
once through its own `RUN_ANALYSIS` adaptive-timeout bucket, and returns a `RunAnalysisResult`
whose outcome is exactly one of `GENERATED`, `SKIPPED`, or `FAILED`. The service acquires the
application-wide single-inference gate on the user-initiated path, emits live progress events
while the call is in flight, and never fails the run when analysis fails.

## In scope

- `backend/run_analysis/`: the `RunAnalysisService` Protocol, `make_run_analysis_service`
  factory, and a `backend/run_analysis/testing.py` fake.
- The applicability gate (snapshot `feature.judge_run_analysis_enabled` for the automatic path;
  always-proceed for the user-initiated path; `SKIPPED` on zero terminal results).
- The single-inference-gate discipline: skip `try_acquire` when invoked inside the pipeline
  (which already holds `BENCHMARK_RUN`); `try_acquire(JUDGE_ANALYSIS, ctx)` on the user-initiated
  path and release in `finally`; return `FAILED` with the busy message when the gate is held.
- The bounded deterministic digest aggregation, the mode-aware prompt framing (`GRADED`/`TASKS`/
  `SYNTHETIC`), the single model call over the `RUN_ANALYSIS` adaptive-timeout bucket, the
  `_inference_progress` emission at ≥ 1 Hz, and the regeneration behaviour that preserves prior
  analysis on failure.

## Out of scope

- Persisting the narrative into `BenchmarkRun.run_analysis` via a `RunStatusPatch` and updating
  the judge-provider snapshot — the caller's step; this service returns the body and persists
  nothing.
- The Generate Analysis dialog, its provider/model dropdowns, its live progress line, and the
  Run Analysis tab's Generate/Regenerate affordance — owned by `ui/common_dialogs/` and
  `ui/results/` in a later phase.
- The run-analysis Markdown export wrapper (metadata header block) — owned by `ui/results/` per
  `10_Domain_and_Data/05_EXPORT_FORMATS.md` §10; this service returns the body text only.
- The `AdaptiveTimeoutService`, `InferenceActivityStore`, and `LLMClient` implementations
  themselves — consumed as Protocols from STORY-022, STORY-015, and STORY-017.

## Spec inputs

- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#61-applicability-gate` — the
  snapshot-flag / user-initiated / zero-terminal-results branching to `SKIPPED`.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#61a-acquire-the-single-inference-gate` —
  the in-pipeline skip-acquire rule and the user-initiated `try_acquire(JUDGE_ANALYSIS, ctx)` /
  release-in-`finally` rule.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#62-aggregate-the-run` — the bounded,
  deterministic run/per-model/per-category/notable-results digest.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#63-build-the-prompt` — the
  system-message contract and the per-mode framing line.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#64-call-the-model-and-post-process` —
  the `RUN_ANALYSIS` adaptive-timeout bucket (independent of the per-task `JUDGE` bucket, DD-65),
  the escalation loop, the ≥ 1 Hz `_inference_progress` emission, and the exhaustion outcome.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#65-regeneration-behaviour` — the
  is-regeneration inference and the failed-regeneration-preserves-prior rule.
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#8-error-handling` — the per-condition
  outcome mapping (unreachable, timeout retry, exhaustion, empty text, gate busy).
- `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md#11-test-cases` — RA-01..RA-25, in
  particular RA-22/RA-24/RA-25 for the `RUN_ANALYSIS` bucket independence.

## Design constraints

- `backend/run_analysis/` is Qt-free and asyncio-free; it imports only `backend/domain`, the
  `LLMClient` Protocol, the `InferenceActivityStore` Protocol, and the `AdaptiveTimeoutService`
  Protocol (`01_MODULE_INVENTORY.md` §4.5). No PySide6, no concrete provider adapter.
- `generate` is **blocking** — invoked on a `TaskRunner`/`QThreadPool` worker thread, never on the
  GUI thread (D-R-01). It never completes via a queued Qt signal.
- The analysis model is called **at most once** per invocation (beyond the LLM client's own
  attempt policy); the service persists nothing and is non-fatal on failure — a failed analysis
  never fails the run.
- The `RUN_ANALYSIS` adaptive-timeout bucket is a separate instance from the per-task `JUDGE`
  bucket (DD-65): it keeps its own last-known-good and its own in-run consecutive-timeout counter
  and does not inherit a maxed per-task judge LKG. **This wiring is the highest-risk part of the
  story and must be reviewed against RA-22/RA-24/RA-25 before implementation is considered done.**
- The gate is released in `finally` only on the path that acquired it; the pipeline path never
  releases because it never acquired. The narrative body is returned verbatim (trimmed only) — no
  redaction (`08_REDACTION_PATTERNS.md` §1).
- `icontract` on any `api.py` symbol guards programmer invariants only.

## Acceptance criteria

### STORY-035-AC-1

`generate` returns a `RunAnalysisResult` whose `outcome` is exactly one of `GENERATED`,
`SKIPPED`, or `FAILED`, with `run_analysis_markdown` non-empty and `error_message` `None` on
`GENERATED`, and `run_analysis_markdown` `None` on `SKIPPED`/`FAILED`.

### STORY-035-AC-2

The applicability gate resolves to `SKIPPED` or proceeds per this table:

| Condition                                                 | Path        | Outcome                  |
| --------------------------------------------------------- | ----------- | ------------------------ |
| snapshot `judge_run_analysis_enabled == true`, automatic  | in-pipeline | proceeds                 |
| snapshot `judge_run_analysis_enabled == false`, automatic | in-pipeline | `SKIPPED`, no model call |
| user-initiated, any snapshot value, any mode              | on-demand   | proceeds                 |
| zero results in a terminal status                         | either      | `SKIPPED`, no model call |

### STORY-035-AC-3

Given the service is invoked on the user-initiated path while another activity holds the
single-inference gate, when `try_acquire(JUDGE_ANALYSIS, ctx)` returns `None`, then `generate`
returns `FAILED` with the in-flight-inference message and never calls the LLM client.

### STORY-035-AC-4

Given the service is invoked inside the pipeline (which already holds `BENCHMARK_RUN`), when
`generate` runs, then it skips its own `try_acquire` and does not release the gate; and on the
user-initiated path it acquires `JUDGE_ANALYSIS` and releases it in `finally`.

### STORY-035-AC-5

The analysis call consults `AdaptiveTimeoutService.next_budget(provider_id, model_name, role=RUN_ANALYSIS, attempt_index=i)` and records outcomes with `role=RUN_ANALYSIS`, and this
bucket is independent of the per-task `JUDGE` bucket — a run that drove the per-task `JUDGE` LKG
to its ceiling does not change the `RUN_ANALYSIS` bucket's LKG or in-run counter (DD-65).

### STORY-035-AC-6

Given a run in `GRADED`, `TASKS`, and `SYNTHETIC` mode respectively, when `generate` builds the
prompt, then each mode produces a distinct framing line (quality outcomes; throughput/latency;
size-grid scaling), and the analysis model is invoked exactly once per `generate` call.

### STORY-035-AC-7

Given a regeneration whose model call fails, when `generate` returns `FAILED`, then the service
reports the failure without producing a body and the caller-facing contract leaves any prior
`run_analysis` unchanged; and given the `RUN_ANALYSIS` escalation ladder is exhausted, `outcome`
is `FAILED` with `error_message` containing `judge_timeout_exhausted` and no `_judge_model_excluded`
event is emitted.

### STORY-035-AC-8

While the model call is in flight, `_inference_progress` events fire at ≥ 1 Hz with
`context=RUN_ANALYSIS`, the run's `run_id`, `result_id=None`, `task_id=None`, and the chosen
`(provider_id, model_name)`; emission stops when the call ends and no progress event fires
afterwards.

## Test plan

- STORY-035-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_outcome_invariants.py`,
  `test_result_field_invariants_per_outcome`. Covers RA-17.
- STORY-035-AC-2 — unit (table-driven over the gate branches), colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_applicability_gate.py`,
  `test_applicability_gate_branches`. Covers RA-01, RA-01b, RA-02, RA-04, RA-05.
- STORY-035-AC-3 — unit (against the `InferenceActivityStore` fake), colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_gate_busy.py`,
  `test_gate_busy_returns_failed_without_model_call`. Covers RA-20.
- STORY-035-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_gate_acquire_release.py`,
  `test_in_pipeline_skips_acquire_user_path_releases`. Covers RA-19.
- STORY-035-AC-5 — unit (against the `AdaptiveTimeoutService` fake, asserting role and bucket
  independence), colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_run_analysis_bucket.py`,
  `test_run_analysis_bucket_is_independent_of_judge`. Covers RA-22, RA-24, RA-25.
- STORY-035-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_prompt_framing.py`,
  `test_mode_aware_framing_and_single_call`. Covers RA-03, RA-09, RA-12.
- STORY-035-AC-7 — unit, colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_failure_handling.py`,
  `test_regeneration_failure_and_exhaustion_outcome`. Covers RA-06, RA-07, RA-08, RA-10, RA-23.
- STORY-035-AC-8 — unit (against a fake progress-emitting client), colocated
  `src/ollama_llm_bench/backend/run_analysis/tests/test_progress_emission.py`,
  `test_inference_progress_emitted_during_call`. Covers RA-21.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-035.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/run_analysis/`.
- [x] An architecture test confirms the module imports no Qt and no `asyncio`.
- [x] The `RUN_ANALYSIS` adaptive-timeout bucket wiring is reviewed against RA-22/RA-24/RA-25.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-035.
- [x] The module inventory is unchanged.
