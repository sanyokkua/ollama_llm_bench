# New Benchmark — Mode: Graded Benchmark

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
`GRADED` (display name **Graded Benchmark**). It covers the visible sections, the
mandatory and optional inputs, the validation rules unique to this mode, the content of
the Run Summary Dialog, and the per-mode feature-flag overrides.

The **"Generate run analysis" toggle** (`feature.judge_run_analysis_enabled`) is
**visible and defaults ON in `GRADED`**. The user can turn it off when they only
want per-task grading verdicts and do not want to spend tokens on the narrative summary.

---

## Table of Contents

1. Mode summary
2. Visible sections
3. Mandatory vs optional inputs
4. Mode-specific validation
5. Run Summary Dialog content
6. Per-mode flag overrides
7. Judge: per-task validation vs run-level analysis

---

## 1. Mode summary

Graded Benchmark runs the complete five-phase batched evaluation pipeline against the user's
**real task files**. After initialisation and inference, the run grades each task and
produces a binary `PASS` / `FAIL` verdict per `(provider, model)` and task. It is the
canonical "how good is each model on my work?" mode.

## 2. Visible sections

| Section | State |
|---|---|
| Mode selector | Active |
| Judge | Visible; a judge model is required when either the per-task judge phase or the run-analysis toggle is on — both default ON in this mode, so the picker is required by default (see §7). The judge call's time budget is governed by the per-role adaptive-timeout ladder (role=JUDGE) — its bounds and exclusion threshold are configured in **Settings → General → Judge timeouts and embedding timeout** (`06_Settings_Dialog/description.md` §4.3a). A judge model that consistently times out at the maximum budget across the configured threshold is excluded for the remainder of the run; affected tasks settle to `FAILED_JUDGE_TIMEOUT` (see DD-34 and `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`). |
| Embedding status row | Visible; reports whether an enabled embedding provider and model exist. When ready it renders in `success.base` and reads, verbatim, `Embedding: {provider_display} · {embedding_model} — ready for keyword-semantic and cosine validation.` (canonical ready/warning states in `description.md` §4.5) |
| Test Models | Visible |
| Task Files | Visible, with drag-and-drop |
| Advanced Options | Visible |
| "Generate run analysis" toggle | Visible; default ON; the user can turn it off to skip the extra inference cost |
| Start button | Visible |

Hidden in this mode: the Performance Matrix (Input Sizes, Output Sizes, Repeats).

## 3. Mandatory vs optional inputs

| Input | Requirement |
|---|---|
| At least one selected `(provider, model)` pair | Mandatory |
| At least one task file added | Mandatory |
| Judge provider and judge model | Required if either the per-task judge phase is enabled or the run-analysis toggle is ON; both are ON by default in `GRADED`, so the judge picker is required by default — but if the user disables both, the judge picker may be left empty and the Start button accepts that configuration |
| Run-level judge analysis toggle | Visible; default ON; optional — see §7 |
| Enabled embedding provider and model | Mandatory when keyword-semantic or cosine validation is enabled in Settings; not required if both are disabled |
| Advanced Options overrides | Optional; pre-filled from global settings |

## 4. Mode-specific validation

| Condition | Severity | Message |
|---|---|---|
| No task file added | hard error | "Add at least one task file." |
| No enabled judge provider, while either the per-task judge phase or the run-analysis toggle is ON | hard error | "A judge model is required when the per-task judge phase or the run-analysis toggle is on. Add an enabled provider in Settings, or disable both toggles." |
| No embedding configured, and keyword-semantic or cosine validation enabled in Settings | hard error | "Graded Benchmark uses cosine similarity (phase 4). Configure an embedding model in Settings, or disable cosine validation." |
| Maximum timeout < Minimum timeout | hard error | "Maximum timeout must be greater than or equal to the minimum timeout." |
| A task file is malformed YAML | hard error (at add time) | "Could not parse '<file>'. Fix the file or remove it." |
| Duplicate `task_id` across loaded files | soft warning | "Duplicate task IDs found across task files — duplicates are graded once each but share an ID." |
| A selected model's provider does not advertise backend streaming | soft warning | "Backend streaming is not advertised for one or more selected models — TTFT may be unmeasurable for those rows." |

The shared "0 models selected" hard error from `description.md` §6 also applies. The
embedding and judge preconditions are verified by the Readiness Service.

## 5. Run Summary Dialog content

The Run Summary Dialog (`07_Common_Dialogs/run_summary_dialog.md`) shows, for this mode:

- **Mode:** Graded Benchmark
- **Models:** the list of selected `provider · model` pairs
- **Judge:** the judge `provider · model`
- **Embedding:** the configured embedding `provider · model`, or a warning if none is
  configured while it is required
- **Task files:** the count of files and the total task count
- **Grading phases active:** keyword, cosine, and judge validation, each marked active or
  inactive according to the effective Settings snapshot — every phase is individually
  toggleable in Settings
- **Run-level judge analysis:** the effective state of `feature.judge_run_analysis_enabled` for the run snapshot — default ON in this mode, but the user can disable it to skip the extra inference cost
- **Advanced overrides:** warmup, reasoning effort, max output tokens, temperature, and the adaptive-timeout
  values (minimum, maximum, retry count, exclusion threshold)
- **Estimated duration:** not estimated — model and judge throughput are unknown until
  measured; live elapsed time is shown on the Progress widget once the run starts
- **Warnings:** any soft-warning entries from the Run Validator

## 6. Per-mode flag overrides

| Flag | Behaviour in Graded Benchmark |
|---|---|
| `feature.judge_run_analysis_enabled` | Visible; **default ON** in this mode; optional — the user can turn it off to skip the extra inference cost when they only care about per-task verdicts. When ON the run produces a comparison narrative; when OFF, `BenchmarkRun.run_analysis` is left null and can be generated post-run via the Run Analysis tab (see D-037) |
| Keyword validation (phase 3) | Toggleable in Settings; default on. Captured into the run snapshot at start |
| Cosine validation (phase 4) | Toggleable in Settings; default on; suppressed automatically for code and reasoning task types. Captured into the run snapshot |
| Judge validation (phase 5) | Toggleable in Settings; default on. When disabled, the run grades with keyword plus cosine only. Captured into the run snapshot |

All other per-run-overridable settings follow the values set in Advanced Options and are
snapshotted at run start (`08_Cross_Cutting/08-G_feature_flags.md`).

## 7. Judge: per-task validation vs run-level analysis

Two distinct judge uses must not be confused:

- **Per-task judge validation (phase 5)** — a per-task grading stage that evaluates every
  task with a response and returns `PASS` / `FAIL` plus a one-sentence explanation; it
  produces no numeric score. It is **toggleable** in Settings (default on) and its
  effective value is captured into the run snapshot. A user who wants keyword plus cosine
  grading only can disable it.
- **Run-level judge analysis** — the narrative comparison report produced after the run
  finishes, ranking the models by speed and quality. It is **visible and optional in every
  mode**, defaulting **ON** in `GRADED` and **OFF** in `SYNTHETIC` and
  `TASKS`. The user can override the default in either direction.

**Judge provider/model: required if either the per-task judge phase is enabled or the
run-analysis toggle is ON; both are ON by default in `GRADED`, so the judge picker
is required by default — but if the user disables both, the judge picker may be left empty
and the Start button accepts that configuration.** When a judge is required and no enabled
judge provider exists, the Start button is disabled with an explanatory tooltip.
