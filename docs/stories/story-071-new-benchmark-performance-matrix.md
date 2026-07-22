---
id: STORY-071
title: Replace the New Benchmark performance-matrix stubs with real size and repeats controls and a live task-count estimate
status: done
spec_clauses:
  - 02_New_Benchmark_Widget/description.md#42-performance-matrix--synthetic-benchmark-only
  - 02_New_Benchmark_Widget/description.md#6-validation-rules
  - 02_New_Benchmark_Widget/description.md#12-section-visibility-decision-table
  - 02_New_Benchmark_Widget/mode_specifics/synthetic.md#2-visible-sections
  - 02_New_Benchmark_Widget/mode_specifics/synthetic.md#3-mandatory-vs-optional-inputs
  - 02_New_Benchmark_Widget/mode_specifics/synthetic.md#4-mode-specific-validation
  - 02_New_Benchmark_Widget/mode_specifics/synthetic.md#5-run-summary-dialog-content
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#23-size-definitions
modules:
  - ui/new_benchmark/
  - ui/common_dialogs/
acceptance_criteria:
  - STORY-071-AC-1
  - STORY-071-AC-2
  - STORY-071-AC-3
  - STORY-071-AC-4
  - STORY-071-AC-5
  - STORY-071-AC-6
depends_on:
  - STORY-054
  - STORY-055
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: M
---

# STORY-071 — Replace the New Benchmark performance-matrix stubs with real size and repeats controls and a live task-count estimate

## Goal

Make a Synthetic Benchmark actually configurable. The Performance Matrix — Input Sizes, Output
Sizes, and Repeats — currently renders as three bare placeholder labels, so a user cannot choose
which prompt sizes to measure, cannot set how many times each cell repeats, and never sees how
much work the run will do. This story replaces the placeholders with the real five-toggle Input
Sizes group, the real five-toggle Output Sizes group, the 1–20 Repeats stepper, the specified
XS+SM default selection, and a live estimated-task-count line that updates as the user changes the
matrix or the selected model count and that carries through to the Run Summary dialog's work count.

## In scope

- `_internal/performance_matrix.py`: the Input Sizes group (five toggles with the verbatim size
  captions), the Output Sizes group (five toggles with the verbatim size captions), and the
  Repeats number stepper (range 1–20, default 3), replacing the `stub_sections.py` placeholders
  for `ConfigSection.INPUT_SIZES`, `OUTPUT_SIZES`, and `REPEATS`.
- The XS+SM-checked default selection (MD/LG/XL unchecked) applied on every fresh construction in
  Synthetic Benchmark, not persisted across sessions.
- The live estimate line under the Repeats stepper computing
  `N_input_sizes × N_output_sizes × N_repeats × N_models` and appending
  `+ 1 run-analysis inference` when the Generate-run-analysis toggle is ON.
- Feeding the same task count into the `RunStartEvent.performance_config` so the Run Summary
  dialog's "Work to be done" line shows the matching `cells × repeats × models = N tasks`
  breakdown.
- The Synthetic-only hard-error validation "Select at least one input size and one output size."
- Removing the three placeholder sections from `stub_sections.py`.

## Out of scope

- The mode selector, section-visibility engine, selection store, test-model picker, and task-files
  section — delivered by STORY-054.
- The Judge section, Advanced Options, the Start button, and the Run Summary dialog itself —
  delivered by STORY-055; this story only supplies the synthetic work-count content the dialog
  renders.
- The `PerformanceTaskGenerator` backend expansion of the matrix into synthetic tasks — a
  `backend/performance_task_generator/` concern, already delivered; this widget produces only the
  count and the `PerformanceConfig`, never the tasks.
- Wiring the concrete `NewBenchmarkGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `02_New_Benchmark_Widget/description.md#42-performance-matrix--synthetic-benchmark-only` — the
  three Sections, the verbatim size captions, the Repeats range 1–20 default 3, the XS+SM default
  selection, and the `N_input × N_output × N_repeats × N_models` estimate formula plus the
  `+ 1 run-analysis inference` rule.
- `02_New_Benchmark_Widget/description.md#6-validation-rules` — the shared validation set,
  including the Synthetic hard error when no input×output combination is checked and the
  0-models-selected hard error that also gates Start.
- `02_New_Benchmark_Widget/description.md#12-section-visibility-decision-table` — the Performance
  Matrix is Visible in `SYNTHETIC` and Hidden (removed from the layout) in `TASKS` and `GRADED`.
- `02_New_Benchmark_Widget/mode_specifics/synthetic.md#2-visible-sections` — the three matrix
  sections are visible only in this mode.
- `02_New_Benchmark_Widget/mode_specifics/synthetic.md#3-mandatory-vs-optional-inputs` — at least
  one input size and one output size are mandatory; both default to XS+SM; Repeats defaults to 3.
- `02_New_Benchmark_Widget/mode_specifics/synthetic.md#4-mode-specific-validation` — the
  Synthetic-only hard-error message and the estimate formula.
- `02_New_Benchmark_Widget/mode_specifics/synthetic.md#5-run-summary-dialog-content` — the
  `cells × repeats × models = N tasks` breakdown the Run Summary dialog shows for this mode.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b2-newbenchmarkgateway` — the gateway surface the
  widget reads the selected model count and settings through.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The three matrix controls are visible only when `mode == SYNTHETIC`; in `TASKS`/`GRADED` they are
  removed from the layout by the existing Mode Visibility Policy, never merely disabled (`08-L` §1).
- The estimate is a pure product of the current selection — number of checked input sizes, number
  of checked output sizes, the repeats value, and the selected `(provider, model)` count read from
  the selection store; the widget derives it locally and never re-derives it in the view from
  cell widgets.
- The performance-matrix selection is per-session in-memory state only; it is not persisted, and
  each fresh construction restores the XS+SM default rather than the last session's choice.
- The widget holds only its per-widget `NewBenchmarkGateway` and never a backend store/service
  Protocol directly (D-R-06).
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and at
  every user-triggered state transition.

## Acceptance criteria

### STORY-071-AC-1

On a fresh construction of the widget in Synthetic Benchmark, each size toggle has the specified
default checked state, and the Repeats stepper reads 3:

| Size | Input Sizes default | Output Sizes default |
| ---- | ------------------- | -------------------- |
| XS   | checked             | checked              |
| SM   | checked             | checked              |
| MD   | unchecked           | unchecked            |
| LG   | unchecked           | unchecked            |
| XL   | unchecked           | unchecked            |

### STORY-071-AC-2

For every combination of at least one checked input size, at least one checked output size, a
repeats value in 1–20, and a selected-model count ≥ 1, the displayed estimated task count equals
`N_input_sizes × N_output_sizes × N_repeats × N_models`.

### STORY-071-AC-3

Given a valid Synthetic configuration, when the Generate-run-analysis toggle is turned ON, then the
estimate line appends `+ 1 run-analysis inference`, and when it is turned OFF, then that suffix is
removed and the base task count is unchanged.

### STORY-071-AC-4

Given Synthetic Benchmark with no input size checked, or no output size checked, when the Run
Validator runs, then it returns a hard error with the message "Select at least one input size and
one output size." and the Start button is disabled.

### STORY-071-AC-5

Given a valid Synthetic configuration, when the user clicks Start Benchmark and the Run Summary
dialog is assembled, then the dialog's work-count breakdown is `cells × repeats × models = N tasks`
where `cells = N_input_sizes × N_output_sizes` and `N` equals the live estimate shown in the panel.

### STORY-071-AC-6

For each run mode, the three Performance Matrix sections have the specified layout presence:

| Mode      | Input Sizes | Output Sizes | Repeats |
| --------- | ----------- | ------------ | ------- |
| SYNTHETIC | visible     | visible      | visible |
| TASKS     | removed     | removed      | removed |
| GRADED    | removed     | removed      | removed |

## Test plan

- STORY-071-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/_internal/tests/test_performance_matrix.py`,
  `test_default_size_selection_and_repeats`.
- STORY-071-AC-2 — property (Hypothesis) unit, colocated
  `src/ollama_llm_bench/ui/new_benchmark/_internal/tests/test_performance_estimate.py`,
  `test_estimate_equals_product_of_counts`.
- STORY-071-AC-3 — unit (`pytest-qt`), same file,
  `test_run_analysis_toggle_appends_estimate_suffix`.
- STORY-071-AC-4 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_synthetic_validation.py`,
  `test_missing_input_or_output_size_disables_start`.
- STORY-071-AC-5 — unit (`pytest-qt`, fake `NewBenchmarkGateway`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_synthetic_run_summary.py`,
  `test_run_summary_work_count_matches_live_estimate`.
- STORY-071-AC-6 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_section_visibility.py`,
  `test_performance_matrix_visibility_per_mode`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-071.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the empty (no size checked)
  and populated matrix states.
- [ ] An architecture test confirms the controller holds only its `NewBenchmarkGateway` (plus the
  Event Bus), that the module references no `setStyleSheet`, embeds no colour literal, and
  imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/new_benchmark/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-071.
- [ ] The module inventory is unchanged.
- [ ] The `stub_sections.py` placeholders for `INPUT_SIZES`, `OUTPUT_SIZES`, and `REPEATS` are
  removed, and no remaining placeholder label references a "future story".
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records.

## Notes

- The stub docstring in `_internal/stub_sections.py` deferred these three sections to a
  "not-yet-drafted future story" that was never written; this story is that story. Removing the
  three placeholders may leave `stub_sections.py` covering only sections that are still legitimately
  stubbed — leave those untouched.
- **Size-toggle → token-target mapping.** The UI-facing size keys `XS`/`SM`/`MD`/`LG`/`XL` map
  one-to-one onto the `PerformanceTaskGenerator`'s fixed synthetic-size token-count buckets
  `64`/`256`/`1024`/`4096`/`16384` tokens respectively, per
  `docs/v3_specification/11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#2.3`. The
  `~5 tok`-style figures shown in each toggle's caption are display copy only (a human-readable
  approximation for the user) and are never used as the actual generator target; the widget reads
  and writes only the `XS`..`XL` keys, never a raw token count.
- **Where the Synthetic missing-sizes hard error lives.** The "Select at least one input size and
  one output size." hard-error rule (AC-4) is implemented widget-locally, as a decorator over the
  injected `RunValidator` in `ui/new_benchmark/_internal/synthetic_validation.py` — there is no
  concrete backend `RunValidator` yet. This is a deliberate, temporary placement: a future story
  that builds the concrete backend `RunValidator` must subsume this rule into that backend
  implementation rather than duplicate it, and should remove (or reduce to a thin pass-through)
  this widget-local decorator once the backend rule exists.
- **Follow-up recommendation: the bucket table is duplicated, not shared.** The size-bucket token
  targets `64`/`256`/`1024`/`4096`/`16384` are hardcoded twice — once in
  `ui/new_benchmark/_internal/performance_matrix.py` (this story) and once in the backend
  `PerformanceTaskGenerator`'s private `_internal/size_buckets.py` — because the UI is not allowed
  to reach into another module's `_internal/` package (an `import-linter` contract forbids it),
  so it cannot simply import the generator's copy. A future story should expose the bucket table
  on the generator module's public surface (`api.py` or `models.py`) and change this widget to
  consume it from there instead of holding its own copy. Until that happens, the two tables can
  silently drift apart: if someone changes one without the other, the UI would let a user pick a
  size the generator no longer recognizes, and the generator would crash (or reject the request)
  instead of the UI simply not offering that choice.
- **Spec observation: the two spec files describing the Synthetic work count disagree on
  wording/order, and this story follows the one it cites.** `common_dialogs/run_summary_dialog.md`
  §6.1 writes the Synthetic work count as "models × matrix_cells × repeats", while
  `mode_specifics/synthetic.md` §5 — the clause this story actually cites and implements — writes
  it as "cells × repeats × models = N tasks". The two documents describe the same number in a
  different order; this story's implementation and its Run Summary dialog output follow the
  wording of §5, the clause in this story's `spec_clauses` list, not the other document's phrasing.
  This is noted here as an observation only; no spec file has been edited. Separately, §4.2's
  parenthetical remark that the estimated-task-count line "opens non-zero" cannot be literally
  true the instant the New Benchmark widget is freshly opened with zero models selected yet — at
  that exact moment the line correctly reads "Estimated tasks: 0" until the user picks a model.
  The correct reading of that remark is "the performance matrix itself opens pre-populated with
  its XS+SM/repeats-3 defaults", not "the task count is non-zero before any model is chosen."
