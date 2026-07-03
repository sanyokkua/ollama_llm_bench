# New Benchmark — Mode: Task Benchmark

**Status:** Draft
**Owner:** coder, tester
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:**
`02_New_Benchmark_Widget/description.md`,
`07_Common_Dialogs/run_summary_dialog.md`,
`08_Cross_Cutting/08-G_feature_flags.md`,
`08_Cross_Cutting/08-H_app_modes.md`,
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`

This document specifies how the New Benchmark widget behaves when the selected run mode is
`TASKS` (display name **Task Benchmark**). It covers the visible sections, the mandatory and
optional inputs, the validation rules unique to this mode, the content of the Run Summary
Dialog, and the per-mode feature-flag overrides.

---

## Table of Contents

1. Mode summary
2. Visible sections
3. Mandatory vs optional inputs
4. Mode-specific validation
5. Run Summary Dialog content
6. Per-mode flag overrides

---

## 1. Mode summary

Task Benchmark runs the user's **real task files**. It performs **no grading at all** — only
timing and throughput, exactly as in Synthetic Benchmark. The only difference between
Task Benchmark and Synthetic Benchmark is the prompt source: Task Benchmark uses the user's task files,
Synthetic Benchmark uses synthetic prompts generated from the input/output size matrix.
The mode answers "how fast do my models handle my workload?" The Task File Loader parses
each task file into `BenchmarkTask` records; each task paired with each selected model
produces one `BenchmarkResult` row. Grading-only fields on each `BenchmarkResult`
(`verdict`, the per-phase verdicts, `cosine_similarity`, `resolution_layer`, etc.) stay
null for every Task Benchmark result.

## 2. Visible sections

| Section | State |
|---|---|
| Mode selector | Active |
| Judge | Visible, override-only (analysis toggle shown, default OFF) |
| Test Models | Visible |
| Task Files | Visible, with drag-and-drop |
| Advanced Options | Visible |
| Start button | Visible |

Hidden in this mode: the Performance Matrix (Input Sizes, Output Sizes, Repeats), the
Embedding status row.

## 3. Mandatory vs optional inputs

| Input | Requirement |
|---|---|
| At least one selected `(provider, model)` pair | Mandatory |
| At least one task file added | Mandatory |
| Judge analysis toggle | Optional; default OFF |
| Judge provider / model | Optional; required only if the judge analysis toggle is ON |
| Advanced Options overrides | Optional; pre-filled from global settings |

## 4. Mode-specific validation

| Condition | Severity | Message |
|---|---|---|
| No task file added | hard error | "Add at least one task file." |
| Judge analysis toggle ON and no enabled judge provider | hard error | "Judge analysis is enabled but no provider is available. Add an enabled provider in Settings, or turn the toggle off." |
| Maximum timeout < Minimum timeout | hard error | "Maximum timeout must be greater than or equal to the minimum timeout." |
| A task file is malformed YAML | hard error (at add time) | "Could not parse '<file>'. Fix the file or remove it." |
| Duplicate `task_id` across loaded files | soft warning | "Duplicate task IDs found across task files — duplicates are run once each but share an ID." |
| A selected model's provider does not advertise backend streaming | soft warning | "Backend streaming is not advertised for one or more selected models — TTFT may be unmeasurable for those rows." |

The shared "0 models selected" hard error from `description.md` §6 also applies.

## 5. Run Summary Dialog content

The Run Summary Dialog (`07_Common_Dialogs/run_summary_dialog.md`) shows, for this mode:

- **Mode:** Task Benchmark
- **Models:** the list of selected `provider · model` pairs
- **Task files:** the count of files and the total task count, counted by parsing the
  files via the Task File Loader
- **Judge analysis:** ON or OFF; when ON, the judge `provider · model`
- **Grading:** not applicable. Task Benchmark never runs the grading phases — they belong only to Graded Benchmark.
- **Advanced overrides:** warmup, reasoning effort, max output tokens, temperature, and the adaptive-timeout
  values (minimum, maximum, retry count, exclusion threshold)
- **Estimated duration:** not estimated — model throughput is unknown until measured; live
  elapsed time is shown on the Progress widget once the run starts
- **Warnings:** any soft-warning entries from the Run Validator

## 6. Per-mode flag overrides

| Flag | Behaviour in Task Benchmark |
|---|---|
| `feature.judge_run_analysis_enabled` | The run-level analysis toggle defaults OFF and is shown and toggleable; its value is captured into the run settings snapshot, not persisted |
| `eval.phase_keyword_enabled`, `eval.phase_cosine_enabled`, `eval.phase_judge_enabled`, `eval.force_judge_on_prior_failure` | Ignored. Task Benchmark never runs any grading phase — these flags apply only in Graded Benchmark. `verdict`, the per-phase verdicts, `cosine_similarity`, and `resolution_layer` stay null on every Task Benchmark result. |

All other per-run-overridable settings follow the values set in Advanced Options and are
snapshotted at run start (`08_Cross_Cutting/08-G_feature_flags.md`).
