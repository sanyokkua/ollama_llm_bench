---
id: STORY-028
title: Grade a response through the sanity, keyword, cosine, and judge evaluators into one binary verdict
status: done
spec_clauses:
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#62-stage-1--sanity-pre-check
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#63-stage-2--keyword-phase
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#64-stage-3--cosine-phase
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#66-stage-5--verdict-combination
  - 11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#7-configuration
  - 08_Cross_Cutting/08-P_judge_protocol.md#4-the-judge-prompt
  - 08_Cross_Cutting/08-P_judge_protocol.md#6-the-expected-response-json-schema
  - 08_Cross_Cutting/08-P_judge_protocol.md#8-parsing-strategy
  - 08_Cross_Cutting/08-P_judge_protocol.md#9-malformed-response-handling-and-retry
modules:
  - backend/evaluation/
acceptance_criteria:
  - STORY-028-AC-1
  - STORY-028-AC-2
  - STORY-028-AC-3
  - STORY-028-AC-4
  - STORY-028-AC-5
  - STORY-028-AC-6
  - STORY-028-AC-7
depends_on:
  - STORY-001
  - STORY-017
  - STORY-027
owner: coder
estimate: L
---

# STORY-028 — Grade a response through the sanity, keyword, cosine, and judge evaluators into one binary verdict

## Goal

Give the benchmark pipeline the four evaluators that grade a single model response — the
deterministic sanity pre-check, the keyword check over exact/forbidden/semantic terms, the
cosine-phase verdict against `eval.cosine_threshold`, and the LLM judge — plus the combination
rule that folds the enabled phases' outcomes into one binary `PASS`/`FAIL` verdict and its
`resolution_layer`. Each evaluator is a pure service over its inputs: it computes verdict and
per-term/patch data and returns it; it does not persist, orchestrate batching, cancel, or emit
run-domain events.

## In scope

- The `SanityChecker` Protocol and its deterministic rules (§6.2): empty/whitespace-only, echo
  of the question, too-short below `eval.sanity_min_chars`, and a leading `eval.sanity_error_markers`
  line — producing `sanity_check_passed` and the "sanity failure is a final `FAIL` that skips the
  judge" signal (DD-62).
- The `KeywordEvaluator` Protocol (§6.3): exact-term (case-insensitive substring, optional
  word-boundary) with `EXACT_MISSING` terms, forbidden-term with `FORBIDDEN_FOUND` terms, and
  semantic-term scoring via the injected `EmbeddingService` (STORY-027) against
  `eval.keyword_semantic_pass_threshold` per term, combined into `keyword_verdict` plus the
  `BenchmarkResultTerm` rows.
- The `CosineEvaluator` Protocol (§6.4): delegate the Cosine Score and threshold to the
  `EmbeddingService`, apply the at-or-above rule to produce `cosine_verdict` and
  `cosine_similarity`, and honour the `cosine_enabled: false` / no-`golden_answer` skip
  (`None`/`None`).
- The `JudgeEvaluator` Protocol: assemble the anonymous per-task judge prompt (system + user
  messages, SPEC-018, DD-46), issue the judge chat call with temperature `0.0`,
  `eval.judge_max_completion_tokens`, and `response_format=JSON` when supported; parse the
  response strictly then leniently (§8); retry a malformed response up to
  `eval.judge_max_parse_retries` with the stricter prompt; record `judge_verdict` /
  `judge_reasoning` / timing / tokens, distinguishing transport failure, exhausted-parse-retries
  (`ERRORED`), and the budget-exhausted diagnostic (DD-67).
- The verdict-combination function (§6.6): the cascade over enabled phases with
  `eval.force_judge_on_prior_failure`, producing `verdict` and `resolution_layer`.
- The `make_*` factories on `api.py` guarded by `icontract` on programmer invariants only, and
  `backend/evaluation/testing.py`.

## Out of scope

- Batching each phase over the whole result set, phase ordering, the `AWAITING_*` status
  transitions, and writing `ResultPatch` rows to SQLite — owned by `backend/benchmark_pipeline/`
  in STORY-029/STORY-030; the evaluators return verdict/patch data, they do not persist.
- The role=JUDGE adaptive-timeout budget, per-task judge-timeout exhaustion
  (`FAILED_JUDGE_TIMEOUT`), and run-wide judge-model exclusion (`_judge_model_excluded`) — the
  timeout ladder and exclusion orchestration are owned by STORY-030; the `JudgeEvaluator` issues
  the call under a budget it is given and reports the outcome.
- The run-start embedding fail-fast probe and the `emit_progress_during(...)` live-progress
  helper (§6.9) — owned by the pipeline (STORY-029); the evaluators are Qt-free and emit no
  `_inference_progress`.
- The `ProviderContextLengthError` translation at the provider adapter boundary — already owned
  by the provider adapters (Phase 4/5); the `JudgeEvaluator` treats it as a permanent,
  non-retried error surfaced by the client.
- Run-level narrative analysis (`RunAnalysisService`) — a separate, already-implemented concern
  (`backend/run_analysis/`); this story touches none of it.

## Spec inputs

- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#62-stage-1--sanity-pre-check` — the four
  deterministic sanity rules and the judge-skip on sanity failure (DD-62).
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#63-stage-2--keyword-phase` — exact /
  forbidden / semantic term handling, the `BenchmarkResultTerm` kinds, and the per-term semantic
  threshold rule.
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#64-stage-3--cosine-phase` — the
  cosine-verdict rule, the `cosine_enabled` / no-`golden_answer` skip, and the fixed embedding
  budget.
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#66-stage-5--verdict-combination` — the
  deterministic-hard-failure short-circuit, the force-judge cascade, and the `resolution_layer`
  assignment.
- `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md#7-configuration` — the phase toggles,
  thresholds, `eval.force_judge_on_prior_failure`, and the sanity keys with their defaults.
- `08_Cross_Cutting/08-P_judge_protocol.md#4-the-judge-prompt` — the universal system message,
  the user-message template and placeholder omission rules, and the SPEC-018 anonymity guarantee.
- `08_Cross_Cutting/08-P_judge_protocol.md#6-the-expected-response-json-schema` — the two-field
  schema, verdict normalisation, missing-`reasoning` default, and the no-numeric-score rule.
- `08_Cross_Cutting/08-P_judge_protocol.md#8-parsing-strategy` — the strict JSON then lenient
  fence-strip / first-`{`-to-last-`}` / key-adjacent-token extraction steps.
- `08_Cross_Cutting/08-P_judge_protocol.md#9-malformed-response-handling-and-retry` — the
  stricter retry prompt, `eval.judge_max_parse_retries`, the exhausted → `ERRORED` outcome, and
  the DD-67 budget-exhausted diagnostic.

## Design constraints

- `backend/evaluation/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`BenchmarkResult`, `BenchmarkResultTerm`, `BenchmarkTask`, `ResultTermKind`, `Verdict`,
  `ChatRequest`, `ChatMessage`, `ChatRole`, `CosineScore`, `BenchmarkRunSettingEntry`, …),
  `backend/embedding` (`EmbeddingService`), `backend/infra`, the `LLMClient` Protocol, and
  `backend/events` only where an evaluator carries data structs (no run-domain emission). No
  PySide6 (`01_MODULE_INVENTORY.md` §4.4).
- Each evaluator is pure over its inputs: it takes the result/task/snapshot and returns
  verdict/term/patch data. It performs no SQLite write, holds no `ResultsStore`, does not touch
  the `CancellationToken`, and does not batch across results.
- **Judge determinism (gap resolution / known limitation).** Temperature `0.0` minimises
  verdict variance but does **not** guarantee bit-reproducibility (SPEC-019); no `seed` is sent.
  Tests must assert prompt shape, parsing, and the deterministic combination logic — never that
  two live judge calls return identical text.
- The judge always grades `sanitized_response` (reasoning stripped), never `raw_response`, and
  the assembled prompt carries no provider name and no test-model name (SPEC-018).
- `eval.keyword_semantic_pass_threshold` is applied **per semantic term** (each must clear it),
  never as a mean; it is a distinct key from `eval.cosine_threshold` (verified present in
  `#7-configuration`).
- `icontract` on each `api.py` factory guards programmer invariants only — never a judge
  response, user text, or snapshot value; a malformed judge response is data handled via the
  parse/retry path, not a contract violation.

## Acceptance criteria

### STORY-028-AC-1

The sanity pre-check outcome for a `sanitized_response` against a task is determined per this
table:

| Response condition                                                           | `sanity_check_passed` |
| ---------------------------------------------------------------------------- | --------------------- |
| empty or whitespace-only                                                     | `False`               |
| case-insensitive echo of the task `question` (per the §6.2 length rule)      | `False`               |
| shorter than `eval.sanity_min_chars` characters (non-`SYNTHETIC`)            | `False`               |
| a trimmed, upper-cased line begins with an `eval.sanity_error_markers` entry | `False`               |
| a plausible, non-echo response at or above the minimum length                | `True`                |

### STORY-028-AC-2

The keyword outcome for a task's `required_terms` against a response is determined per this
table, and each contributing term is recorded as a `BenchmarkResultTerm` of the matching kind:

| Term condition                                                                  | `keyword_verdict` | Recorded term kind       |
| ------------------------------------------------------------------------------- | ----------------- | ------------------------ |
| a declared `exact` term absent from the response                                | `FAIL`            | `EXACT_MISSING`          |
| a declared `forbidden` term present in the response                             | `FAIL`            | `FORBIDDEN_FOUND`        |
| a declared `semantic` term below `eval.keyword_semantic_pass_threshold`         | `FAIL`            | `SEMANTIC`               |
| all exact present, no forbidden present, every semantic term at/above threshold | `PASS`            | `SEMANTIC` (each scored) |
| no `required_terms` declared                                                    | `PASS`            | none                     |

### STORY-028-AC-3

Given a task with a `golden_answer` and `cosine_enabled = true`, the cosine evaluator sets
`cosine_verdict = PASS` when the Cosine Score is at or above `eval.cosine_threshold` and `FAIL`
below it, always storing the numeric `cosine_similarity`; given a task with `cosine_enabled = false`
or no `golden_answer`, the evaluator performs no cosine computation and leaves both
`cosine_similarity` and `cosine_verdict` `None`.

### STORY-028-AC-4

For every run whose judge is also one of its test models, the assembled judge prompt — both the
system message and the user message — contains no provider identifier and no test-model name,
carries the `sanitized_response` (never `raw_response`), and omits each absent optional field
per the §4.2 placeholder rules (e.g. a `None` `golden_answer` renders `REFERENCE ("GOLDEN") ANSWER: (none provided)`).

### STORY-028-AC-5

The judge response parser resolves each body per this table, issuing the stricter retry only
when both parse steps fail:

| Judge response body                                               | Parse outcome                                            |
| ----------------------------------------------------------------- | -------------------------------------------------------- |
| clean `{"verdict":"PASS","reasoning":"…"}`                        | strict parse → `PASS`, no retry                          |
| lower-case `"pass"` verdict                                       | normalised → `PASS`                                      |
| valid `verdict`, missing `reasoning`                              | accepted; reasoning `"(no reasoning provided by judge)"` |
| object wrapped in ```` ```json ```` fences with surrounding prose | lenient parse → verdict, no retry                        |
| a `PASS`/`FAIL` token adjacent to the `verdict` key amid prose    | lenient parse → verdict                                  |
| prose containing neither token, or both with no key association   | malformed → stricter retry                               |
| extra fields (e.g. a `score`) present                             | accepted; extra fields ignored, no numeric value stored  |

### STORY-028-AC-6

Given `eval.judge_max_parse_retries = R`, when every one of the `R + 1` attempts returns a
malformed response, then the judge evaluator reports the result as `ERRORED` with
`judge_verdict = None`, a diagnostic `judge_reasoning`, and `error_kind = OTHER` (retryable);
when the malformed responses were truncated at the `eval.judge_max_completion_tokens` cap, the
reported diagnostic is the budget-exhausted message (DD-67) rather than a bare parse failure.

### STORY-028-AC-7

The combined `verdict` and `resolution_layer` for a graded result are determined per this table
over the enabled phases:

| Enabled phases                         | Force-judge | Combined `verdict` source                                                                      | `resolution_layer`             |
| -------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------- | ------------------------------ |
| sanity fails (any config)              | any         | `FAIL` (judge not called)                                                                      | `KEYWORD`                      |
| keyword only                           | n/a         | `keyword_verdict`                                                                              | `KEYWORD`                      |
| keyword + cosine                       | n/a         | keyword `FAIL` short-circuits; else `cosine_verdict`; else `keyword_verdict` if cosine skipped | `KEYWORD` or `COSINE`          |
| keyword + cosine + judge               | off         | deterministic hard `FAIL` stands; else `judge_verdict`                                         | `KEYWORD` / `COSINE` / `JUDGE` |
| keyword + cosine + judge               | on          | `judge_verdict` decides even over a prior keyword/cosine `FAIL`                                | `JUDGE`                        |
| judge enabled, judge transport failure | any         | falls back to `cosine_verdict` else `keyword_verdict`                                          | `COSINE` / `KEYWORD`           |

## Test plan

- STORY-028-AC-1 — unit (table-driven over the five sanity conditions), colocated
  `src/ollama_llm_bench/backend/evaluation/tests/test_sanity.py`,
  `test_sanity_rules_flag_the_expected_responses`.
- STORY-028-AC-2 — unit (table-driven over the term conditions), colocated
  `src/ollama_llm_bench/backend/evaluation/tests/test_keyword.py`,
  `test_keyword_verdict_and_result_terms`.
- STORY-028-AC-3 — unit, colocated
  `src/ollama_llm_bench/backend/evaluation/tests/test_cosine_phase.py`,
  `test_cosine_verdict_threshold_and_skip`.
- STORY-028-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/evaluation/tests/test_judge_prompt.py`,
  `test_judge_prompt_is_anonymous_and_omits_absent_fields`. Covers the SPEC-018 anonymity check.
- STORY-028-AC-5 — unit (table-driven over the parse cases), colocated
  `src/ollama_llm_bench/backend/evaluation/tests/test_judge_parsing.py`,
  `test_judge_response_parser_strict_then_lenient`.
- STORY-028-AC-6 — unit, same file,
  `test_exhausted_parse_retries_error_and_budget_exhausted_diagnostic`.
- STORY-028-AC-7 — unit (table-driven over the combination cases), colocated
  `src/ollama_llm_bench/backend/evaluation/tests/test_combination.py`,
  `test_verdict_combination_cascade`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-028.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/evaluation/`.
- [x] An architecture test confirms `backend/evaluation/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-028.
- [x] The module inventory is unchanged.
