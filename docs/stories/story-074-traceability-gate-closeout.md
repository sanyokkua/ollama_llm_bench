---
id: STORY-074
title: Add the missing edge-case tests for double-admission, first-use model-load failure, and the model-snapshot DB invariants
status: in-progress
spec_clauses:
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-RUN-1a
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-1a
  - 08_Cross_Cutting/08-I_edge_cases.md#EC-PERSIST-6
  - 14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#EC-PERSIST-6
  - 01_Main_Window/description.md#16-edge-cases
modules:
  - ui/new_benchmark/
  - ui/resume_benchmark/
  - backend/benchmark_pipeline/
  - backend/persistence/runs/
  - backend/persistence/results/
acceptance_criteria:
  - STORY-074-AC-1
  - STORY-074-AC-2
  - STORY-074-AC-3
  - STORY-074-AC-4
  - STORY-074-AC-5
edge_cases:
  - EC-RUN-1a
  - EC-PROV-1a
  - EC-PERSIST-6
depends_on:
  - STORY-055
  - STORY-057
owner: tester
estimate: L
---

# STORY-074 — Add the missing edge-case tests for double-admission, first-use model-load failure, and the model-snapshot DB invariants

## Goal

Close the three edge-case coverage gaps that keep the Phase 10 traceability gate from signing off.
Each names a real behaviour that already exists in the code but that no test proves: a rapid
double-admission of Start/Resume must be a complete no-op against the single-inference gate; a model
that passed readiness but cannot actually load must surface as a per-task failure at first use (the
warmup-off path); and the model-snapshot singletons plus the results-to-test-snapshot match must be
enforced by the database. This story adds the `Proves:`-linked tests that cover those behaviours and
names the three edge cases so they are claimed and proven, and records the residual read-only-spec
reconciliation the gate still needs.

## In scope

- A UI-level `pytest-qt` test proving double-admission is a no-op through the **New Benchmark**
  Start admission path (EC-RUN-1a).
- A UI-level `pytest-qt` test proving double-admission is a no-op through the **Resume** admission
  path, with the retry-row reset happening only after the gate is held and being idempotent
  (EC-RUN-1a).
- A pipeline test proving the warmup-off first-use model-load failure settles the row to a
  `FAILED_*` status and advances the run (EC-PROV-1a).
- A persistence/architecture test proving the second-`judge`/second-`embedding` run-model insert
  raises a UNIQUE violation via the partial indexes (EC-PERSIST-6).
- A persistence/architecture test proving every `benchmark_results` row's
  `(run_id, provider_id, model_name)` matches a `role='test'` snapshot row (SPEC-038) (EC-PERSIST-6).
- Naming EC-RUN-1a, EC-PROV-1a, and EC-PERSIST-6 in this story's `edge_cases:` so they are claimed.

## Out of scope

- Any further change to the vendored specification. The one-time mapping/catalog correction this
  story originally flagged as a spec-owner action was made on 2026-07-22 with the project owner's
  explicit sanction (see Notes) — no additional spec edit is in scope.
- The **warmup-on** variant of EC-PROV-1a (warmup at the model-switch boundary, warmup-timeout →
  circuit breaker) — the pipeline warmup implementation does not exist yet; only the
  `benchmark.warmup_enabled` settings toggle does (see Notes). This story tests the warmup-off path
  only.
- Implementing the admission gate, the pipeline failure classification, or the DB indexes — these
  already exist; this is a test-authoring closeout, not a feature build.

## Spec inputs

- `08_Cross_Cutting/08-I_edge_cases.md#EC-RUN-1a` — admission is gate-first and synchronous on the
  GUI thread (SPEC-036, DD-50): the first `try_acquire(BENCHMARK_RUN)` succeeds and proceeds; the
  second hits `None` and is a complete no-op — no second run, no second row reset, no second
  pipeline; for `resume`, the retry-row reset happens only after the gate is held and is idempotent.
- `08_Cross_Cutting/08-I_edge_cases.md#EC-PROV-1a` — an advertised model that cannot load surfaces
  at first use, not silently mid-run; with warmup off, the first task's inference produces the same
  `FAILED_*` outcome, and `READY` never meant loadable.
- `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md#EC-PERSIST-6` — the model-snapshot
  singletons are DB-enforced (a second `judge`/`embedding` run-model row raises a UNIQUE violation
  via `ux_run_models_one_judge` / `ux_run_models_one_embedding`), and every `benchmark_results` row
  matches a `role='test'` snapshot row (SPEC-038); tiers unit + architecture, tested in
  `backend/persistence/` and `tests/architecture/`.
- `01_Main_Window/description.md#16-edge-cases` — the Main Window edge-case table (cited for the
  EC-SET-4/EC-SET-1 label observation recorded in Notes).

## Design constraints

- The EC-RUN-1a tests are UI-level: they drive the New Benchmark and Resume admission paths and
  assert the no-op against the existing `InferenceActivityStore` gate; they do not touch the gate
  module's own code.
- The EC-PROV-1a test drives the pipeline with `benchmark.warmup_enabled` off and a fake
  `LLMClient` whose first call fails to load, asserting the row's terminal `FAILED_*` status and
  that the run advances.
- The EC-PERSIST-6 tests run against a real `tmp_path` SQLite database (never in-memory), matching
  the persistence modules' integration test convention.
- Each proving test declares `Proves: STORY-074-AC-N` on the first line of its docstring.
- No production-code change is expected; if a test surfaces a genuine defect, that defect is fixed
  under this story's `modules:` only, or escalated as its own story.

## Acceptance criteria

### STORY-074-AC-1

Given no inference activity is in flight, when two New Benchmark Start admissions fire before the
first has flipped the gate state, then the first acquires `BENCHMARK_RUN` and proceeds and the
second is a complete no-op — no second run record, no second result-row reset, and no second
pipeline is started.

### STORY-074-AC-2

Given no inference activity is in flight, when two Resume admissions race (a double-click, or the
Resume-Summary Confirm racing another resume path), then the first acquires the gate and proceeds
and the second is a complete no-op, and the retry-row reset is performed only after the gate is held
and is idempotent across the two calls.

### STORY-074-AC-3

Given `benchmark.warmup_enabled` is off and a selected model that passed readiness cannot load at
run time, when the first task's inference is attempted, then that result row settles to a `FAILED_*`
status carrying the load-failure error and the pipeline advances to the next task without aborting
the run.

### STORY-074-AC-4

Given a run with a model snapshot, when a second `judge` row (or a second `embedding` row) is
inserted for the same run, then the database raises a UNIQUE violation via the partial index
(`ux_run_models_one_judge` / `ux_run_models_one_embedding`).

### STORY-074-AC-5

For every persisted `benchmark_results` row, its `(run_id, provider_id, model_name)` triple matches
a `role='test'` model-snapshot row for that run (SPEC-038) — no results row can exist without a
corresponding test-role snapshot row.

## Test plan

- STORY-074-AC-1 — unit (`pytest-qt`, fake gateway + real `InferenceActivityStore`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_start_admission.py`,
  `test_double_start_admission_is_a_noop`. Covers EC-RUN-1a.
- STORY-074-AC-2 — unit (`pytest-qt`, fake gateway + real `InferenceActivityStore`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_resume_admission.py`,
  `test_double_resume_admission_is_a_noop_and_reset_is_idempotent`. Covers EC-RUN-1a.
- STORY-074-AC-3 — integration, `tests/integration/test_first_use_model_load_failure.py`,
  `test_warmup_off_first_use_load_failure_marks_failed_and_advances`. Covers EC-PROV-1a.
- STORY-074-AC-4 — integration (`tmp_path` DB), colocated
  `src/ollama_llm_bench/backend/persistence/runs/tests/test_model_snapshot_singletons.py`,
  `test_second_judge_or_embedding_row_raises_unique_violation`. Covers EC-PERSIST-6.
- STORY-074-AC-5 — architecture, `tests/architecture/test_results_reference_test_snapshot.py`,
  `test_every_result_matches_a_test_role_snapshot_row`. Covers EC-PERSIST-6.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-074.
- [ ] EC-RUN-1a, EC-PROV-1a, and EC-PERSIST-6 each have a passing proving test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] `just trace` regenerates the record and the three edge cases resolve to their proving tests
  (no orphan test for STORY-074).
- [ ] The module inventory is unchanged.
- [ ] `just trace-check` passes with zero failures — the mapping/catalog correction landed on
  2026-07-22 (see Notes), so once this story's proving tests exist no structural failure remains.

## Notes

**The original three trace-check failures were mapping/catalog structural mismatches, not test
gaps — resolved by a sanctioned spec correction on 2026-07-22.**
`scripts/validate_traceability.py::check_edge_cases_covered` computed them purely from the catalog
files versus `06_EDGE_CASE_TO_TEST_MAPPING.md`: (1) "edge-case mapping cites EC-PERSIST-6, defined
in no catalog (dangling row)"; (2) "EC-RUN-1a is defined in a catalog but has no row in the
mapping"; (3) "EC-PROV-1a ... has no row in the mapping". No test or story metadata could clear
them. On 2026-07-22 the project owner explicitly sanctioned a one-time correction to the vendored
specification's own traceability tables (the sole exception ever made to the read-only-spec rule,
recorded here so it is not a silent edit): an `EC-RUN-1a` row and an `EC-PROV-1a` row were added to
`14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` §4/§6, restating their `08-I` catalog
entries verbatim in intent; and an `EC-PERSIST-6` catalog entry was added to
`08_Cross_Cutting/08-I_edge_cases.md` §9, restating its pre-existing mapping row against
`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §5.7/§6 and `12_Quality_and_NFRs/06_DATA_INTEGRITY.md`
(SPEC-038). No behavioural clause was touched — the correction reconciled the spec's internal
bookkeeping with itself. **This story delivers the behaviour tests (the genuinely missing half —
"zero citing tests"); with the rows now present, the only remaining failures are the transient
"named by a story but has no proving test" lines that this story's own tests clear.**

**EC-PROV-1a warmup variant is a separate backend gap.** `benchmark.warmup_enabled` exists only as a
settings toggle; the pipeline has no warmup implementation (no warmup call at the model-switch
boundary, no warmup-timeout → circuit-breaker path). This story tests only the warmup-off path.
Building the warmup pipeline and its EC-PROV-1a/EC-PROV-3 warmup-timeout behaviour is out of scope
and should be its own `backend/benchmark_pipeline/` story.

**Spec-hygiene observations (record only; no spec edits):**

- `01_Main_Window/description.md#16-edge-cases` cites `EC-SET-4` for "Settings open attempted
  mid-run", but the catalog (`08-I_edge_cases.md` §4) defines that behaviour as `EC-SET-1`;
  `EC-SET-4` is actually "Reset to Defaults during unsaved edits". The Main Window table mislabels
  the id.
- The Task Editor spec still names a `ValidationCascade` Protocol, though the settled design (per
  STORY-069) uses `TaskFileValidator` directly and no `ValidationCascade` Protocol exists.
- The Main Window factory's additive `theme_manager` / `platform_kind` parameters are documented
  only in a module docstring, with no story or ADR recording the additive deviation.
