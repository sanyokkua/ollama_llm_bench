# Judge Protocol — Rubric Reference

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-P_judge_protocol.md`, `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `05_Result_Widget/tabs/run_analysis_tab.md`

This document is a short pointer file. The complete, authoritative contract for the LLM-as-judge evaluation layer — when the judge phase runs, the prompt structure, the system and user message templates, the universal system message (DD-46), the response JSON schema, sampling and token budget, the two-step parsing strategy, malformed-response retry, how the judge outcome is recorded on `BenchmarkResult`, and how the judge verdict combines into the final binary verdict — lives in **`08_Cross_Cutting/08-P_judge_protocol.md`**. Implementers and testers must treat that document as the single source of truth for the judge protocol; this file does not restate the prompt template or the JSON schema.

## Table of Contents

1. Summary
2. Authoritative reference

---

## Summary

The judge is an LLM acting as an impartial evaluator of another model's response — the third and final grading phase of a graded benchmark run, after the keyword and cosine phases. When the judge phase is enabled it evaluates every result that has a response, not only undecided ones. It returns exactly two outputs per task: a binary `verdict` (`PASS` or `FAIL`) and a short free-text `reasoning` string. It produces **no numeric score** — the only numeric quality value in the application is the Cosine Score from the cosine phase. The judge model is called with temperature `0.0` to minimise verdict variance (not a bit-reproducibility guarantee — `08-P` §7). The judge prompt is **one universal template** (DD-46): the judge's expertise is steered by the task's `category` / `sub_category`, and the decisive instructions are the task-authored pass/fail criteria — no per-task-type rubric exists. The separate run-level narrative analysis is a different feature and is specified in `05_Result_Widget/tabs/run_analysis_tab.md`.

**Adaptive timeout (DD-34, refined by DD-65).** The two judge-model call paths consult the Adaptive Timeout Service on **separate** buckets: the per-task judge call in the Phase 4 evaluation pipeline uses `role = AdaptiveTimeoutRole.JUDGE`, while the user-initiated run-analysis generation call in the `RunAnalysisService` uses `role = AdaptiveTimeoutRole.RUN_ANALYSIS`. The two buckets are independent — each keeps its own last-known-good and its own in-run consecutive-timeout counter — so the longer analysis prompt escalates its full ladder instead of inheriting a per-task judge LKG already promoted to the ceiling. Both buckets are parameterised by the same `eval.judge_timeout_*` keys (as separate instances). The ladder is parameterised by `eval.judge_timeout_min_seconds`, `eval.judge_timeout_max_seconds`, `eval.judge_timeout_escalation_steps`, and `eval.judge_timeout_consecutive_threshold`. On per-task exhaustion the result settles to `ResultStatus.FAILED_JUDGE_TIMEOUT`; on run-wide exclusion the pipeline emits `_judge_model_excluded` and every remaining task's judge phase is skipped. On analysis exhaustion the `RunAnalysisService` returns `RunAnalysisResult.outcome = FAILED, reason = "judge_timeout_exhausted"`. See `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md` §1.1 and §6.5 for the algorithm and `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.5 for the pipeline integration.

## Authoritative reference

For every detail of the judge protocol see:

- **`08_Cross_Cutting/08-P_judge_protocol.md`** — the complete judge contract: the universal prompt templates, JSON schema, parsing, retry, context-overflow handling (DD-46), outcome recording, and final-verdict combination.
- **`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md`** — how the judge phase sits within the five-stage evaluation pipeline and how `judge_verdict` feeds the verdict-combination step.
- **`05_Result_Widget/tabs/run_analysis_tab.md`** — the run-level judge analysis, which is governed separately and is not part of the per-task judge protocol.
