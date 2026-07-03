# New Benchmark — Mode: Synthetic Benchmark

**Status:** Draft
**Owner:** coder, tester
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:**
`02_New_Benchmark_Widget/description.md`,
`07_Common_Dialogs/run_summary_dialog.md`,
`08_Cross_Cutting/08-G_feature_flags.md`,
`08_Cross_Cutting/08-H_app_modes.md`,
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`,
`11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md`

This document specifies how the New Benchmark widget behaves when the selected run mode is
`SYNTHETIC` (display name **Synthetic Benchmark**). It covers the visible sections,
the mandatory and optional inputs, the validation rules unique to this mode, the content
of the Run Summary Dialog, and the per-mode feature-flag overrides.

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

Synthetic Benchmark measures raw inference throughput per model — time to first token
(TTFT), tokens per second, and total time — on **synthetic** prompts of controlled sizes.
No real task files are used; the Performance Task Generator produces synthetic prompts
from the selected input and output sizes. The mode answers "how fast is this model on this
machine, across a spread of prompt sizes?" and performs no grading.

## 2. Visible sections

| Section | State |
|---|---|
| Mode selector | Active |
| Performance Matrix — Input Sizes | Visible |
| Performance Matrix — Output Sizes | Visible |
| Performance Matrix — Repeats | Visible |
| Judge | Visible, override-only (analysis toggle shown, default OFF) |
| Test Models | Visible |
| Advanced Options | Visible |
| Start button | Visible |

Hidden in this mode: Task Files, the Embedding status row.

## 3. Mandatory vs optional inputs

| Input | Requirement |
|---|---|
| At least one selected `(provider, model)` pair | Mandatory |
| At least one Input Size Toggle on | Mandatory; **defaults to XS + SM checked** (MD/LG/XL off) on a fresh open |
| At least one Output Size Toggle on | Mandatory; **defaults to XS + SM checked** (MD/LG/XL off) on a fresh open |
| Repeats (1..20) | Mandatory; defaults to 3 |
| Judge analysis toggle | Optional; default OFF |
| Judge provider / model | Optional; required only if the judge analysis toggle is ON |
| Advanced Options overrides | Optional; pre-filled from global settings |

## 4. Mode-specific validation

| Condition | Severity | Message |
|---|---|---|
| No input size or no output size selected | hard error | "Select at least one input size and one output size." |
| Judge analysis toggle ON and no enabled judge provider | hard error | "Judge analysis is enabled but no provider is available. Add an enabled provider in Settings, or turn the toggle off." |
| Maximum timeout < Minimum timeout | hard error | "Maximum timeout must be greater than or equal to the minimum timeout." |
| A selected model's provider does not advertise backend streaming | soft warning | "Backend streaming is not advertised for one or more selected models — TTFT may be unmeasurable for those rows." |

The shared "0 models selected" hard error from `description.md` §6 also applies.

The estimated task count shown under the Repeats stepper is computed by the Performance
Task Generator formula:

```text
estimated_tasks = N_input_sizes × N_output_sizes × N_repeats × N_models
```

The generator builds **one deterministic prompt per `(input, output)` cell** — there is no
prompt-template axis (`11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md` §6.1).
When the **Generate run analysis** toggle is ON, the estimate line appends
`+ 1 run-analysis inference` (one extra LLM call after the run; no result row).

## 5. Run Summary Dialog content

The Run Summary Dialog (`07_Common_Dialogs/run_summary_dialog.md`) shows, for this mode:

- **Mode:** Synthetic Benchmark
- **Models:** the list of selected `provider · model` pairs
- **Performance matrix:** the selected input sizes, output sizes, repeat count, and the
  resulting `cells × repeats × models = N tasks` breakdown
- **Judge analysis:** ON or OFF; when ON, the judge `provider · model`
- **Advanced overrides:** warmup, reasoning effort, max output tokens, temperature, and the adaptive-timeout
  values (minimum, maximum, retry count, exclusion threshold)
- **Estimated duration:** not estimated — a meaningful estimate would require prior
  throughput measurements for these models on this machine; live elapsed time is shown on
  the Progress widget once the run starts
- **Warnings:** any soft-warning entries from the Run Validator

## 6. Per-mode flag overrides

| Flag | Behaviour in Synthetic Benchmark |
|---|---|
| `feature.judge_run_analysis_enabled` | The run-level analysis toggle defaults OFF and is shown and toggleable; its value is captured into the run settings snapshot, not persisted |
| Grading flags (keyword, cosine, judge validation) | Not applicable — Synthetic Benchmark produces no per-task grading; `final_verdict`, `cosine_similarity`, and all per-phase verdicts remain null |

All other per-run-overridable settings follow the values set in Advanced Options and are
snapshotted at run start (`08_Cross_Cutting/08-G_feature_flags.md`).
