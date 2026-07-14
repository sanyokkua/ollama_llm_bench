---
id: STORY-033
title: Compute the twelve chart aggregators with the five-filter pipeline and guards
status: ready
spec_clauses:
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#62-step-2--apply-the-global-filters
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#63-step-3--apply-the-per-chart-status-precondition
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#65-step-5--group-and-aggregate
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#65a-minimum-sample-size-guard-d-r-04-miss-02
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#66-outlier-handling
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#67-empty-state-resolution
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#7-per-chart-catalog
  - 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#12-test-cases
modules:
  - backend/charts/
acceptance_criteria:
  - STORY-033-AC-1
  - STORY-033-AC-2
  - STORY-033-AC-3
  - STORY-033-AC-4
  - STORY-033-AC-5
  - STORY-033-AC-6
  - STORY-033-AC-7
  - STORY-033-AC-8
  - STORY-033-AC-9
edge_cases:
  - EC-RES-1
  - EC-RES-4
depends_on:
  - STORY-001
  - STORY-004
owner: coder
estimate: L
---

# STORY-033 — Compute the twelve chart aggregators with the five-filter pipeline and guards

## Goal

Give the Result widget its chart backend: one pure, Qt-free aggregator per `ChartKind` that
turns a run's `BenchmarkResult` snapshot into a plot-ready `ChartData` or `HeatmapData`
structure. Every aggregator runs the shared pipeline — mode gate, the five global filters, the
per-chart status pre-filter, per-chart options, stable grouping and summary — and applies the
minimum-sample-size guard, IQR outlier handling, the Pareto frontier, and the kind-specific
empty-state message, so the UI only paints a finished structure and never performs aggregation
arithmetic.

## In scope

- `backend/charts/`: the `ChartAggregator` Protocol, `make_chart_aggregator` factory, and a
  `backend/charts/testing.py` fake.
- All twelve `ChartKind` aggregators of §7 (six offered in every mode; six grading-only).
- The shared pipeline: the grading-chart mode gate, the five global filters (Models, Status,
  Verdict, Category, Difficulty), the per-chart `COMPLETED`-status pre-filter, per-chart options,
  and stable group ordering by `(provider_id, model_name)`.
- The minimum-sample-size low-sample flag (`eval.min_sample_size`, default 5), the IQR × 1.5
  outlier rule, the Pareto frontier for `SPEED_VS_QUALITY_SCATTER`, and per-kind empty-state
  structures with their fixed messages.

## Out of scope

- Rendering `ChartData`/`HeatmapData` to a Qt canvas and the PNG/SVG chart export bytes — owned
  by `ui/results/` and its OS-adapter export path in a later phase; this story emits descriptive
  data only, with no Qt objects and no theme-resolved colours.
- The chart chooser, per-chart option controls, and the 500 ms live-refresh debounce — owned by
  `ui/results/`.
- Defining `ChartData`, `HeatmapData`, `ChartFilters`, `ChartSeries`, and `ChartKind` — consumed
  from `backend/domain/` (STORY-001); this story computes them, it does not define them.

## Spec inputs

- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#62-step-2--apply-the-global-filters` — the
  five global filters, their domains, the keep-a-row predicate, and the "all"-means-no-constraint
  default.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#63-step-3--apply-the-per-chart-status-precondition` —
  which chart kinds keep only `COMPLETED` rows versus every surviving row.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#65-step-5--group-and-aggregate` — the
  grouping keys and the stable `(provider_id, model_name)` ordering.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#65a-minimum-sample-size-guard-d-r-04-miss-02` —
  the per-group `n` and the `low_sample` flag below `eval.min_sample_size`.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#66-outlier-handling` — the IQR × 1.5 rule
  and the box-plot exception.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#67-empty-state-resolution` — when a
  structure is the kind-specific empty state with its message.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#7-per-chart-catalog` — the exact
  computation, options, mode availability, and empty-state message of all twelve kinds.
- `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md#12-test-cases` — CA-1..CA-30, including the
  per-kind fixture cases.

## Design constraints

- `backend/charts/` is Qt-free and asyncio-free; it imports only `backend/domain` and
  `backend/infra` (`01_MODULE_INVENTORY.md` §4.5). No PySide6.
- Every aggregator is a pure function of `(chart_kind, run_mode, results, tasks, filters)` with
  no I/O and no shared mutable state; the output is deterministic and the input `results`/`tasks`
  snapshots are not mutated.
- The service never raises to the UI: an aggregator that cannot produce a chart returns the
  kind-specific empty-state structure; an out-of-domain per-chart option is replaced by its
  default and logged at warning level.
- A grading chart requested in `SYNTHETIC`/`TASKS` mode returns the empty-state structure with
  `"This chart is available only for graded runs."` (defence in depth).
- `icontract` on any `api.py` symbol guards programmer invariants only.

## Acceptance criteria

### STORY-033-AC-1

For each of the twelve `ChartKind` values, computing the aggregator over its representative
fixture produces a structure whose series/labels match the §7 catalog's computation for that
kind — asserted by a fixture-based snapshot test, one per chart kind (twelve total).

### STORY-033-AC-2

Given a working result set, applying each of the five global filters (Models, Status, Verdict,
Category, Difficulty) keeps exactly the rows whose value is in the selected set, and a filter
whose selection is "all" (empty) keeps every row, per this table:

| Filter     | Selection                       | Row kept when                                  |
| ---------- | ------------------------------- | ---------------------------------------------- |
| Models     | one `(provider_id, model_name)` | row's model pair is the selected one           |
| Status     | one `ResultStatus`              | row's `status` is the selected one             |
| Verdict    | `PASS`                          | row's `verdict == PASS`                        |
| Verdict    | *ungraded*                      | row's `verdict is None`                        |
| Category   | one category                    | joined task's `category` is the selected one   |
| Difficulty | one `Difficulty`                | joined task's `difficulty` is the selected one |
| any        | all / empty                     | always kept                                    |

### STORY-033-AC-3

Given a timing/token chart kind (1, 2, 3, 8, 12) and a mix of `COMPLETED` and non-`COMPLETED`
rows, when the aggregator runs, then only `COMPLETED` rows contribute to the summary; and given a
status-count chart (kind 4), every surviving row contributes.

### STORY-033-AC-4

Given an aggregated per-model group whose completed-row count `n` is below `eval.min_sample_size`,
when the aggregator produces the group, then the group carries its `n` and is flagged
`low_sample`, and a group at or above the threshold is not flagged.

### STORY-033-AC-5

Given a chart kind offering an outlier toggle and a group containing a value beyond
`Q1 − 1.5·IQR` or `Q3 + 1.5·IQR`, when the toggle drops outliers, then that value is excluded
from the group's summary statistic; and the box-plot kind (12) never drops outliers — it emits
them in a separate list.

### STORY-033-AC-6

Given a grading chart kind requested for a `TASKS` or `SYNTHETIC` run, when the aggregator runs,
then it returns the empty-state structure with the message `"This chart is available only for graded runs."` and performs no further work.

### STORY-033-AC-7

Given `SPEED_VS_QUALITY_SCATTER` over three or more models, when the aggregator runs, then the
auxiliary Pareto-frontier list contains exactly the models not dominated on both axes, sorted by
ascending x; and with fewer than two models carrying a completed verdict it returns the
two-models empty-state message.

### STORY-033-AC-8

Given a filter set under which no row survives, or a chart whose required field is `None` on
every surviving row, when the aggregator runs, then it returns the kind-specific empty-state
structure with that kind's message and raises no exception.

### STORY-033-AC-9

For every aggregator, running it twice over the same inputs produces identical structures with
group order stable by `(provider_id, model_name)`, and the input `results` and `tasks` tuples are
unchanged after aggregation.

## Test plan

- STORY-033-AC-1 — unit (fixture-based snapshot, one per chart kind — twelve tests), colocated
  `src/ollama_llm_bench/backend/charts/tests/test_chart_snapshots.py`,
  `test_<chart_kind>_matches_fixture` (twelve functions). Covers CA-1, CA-4, CA-6, CA-9, CA-12,
  CA-14, CA-16, CA-17, CA-20, CA-23.
- STORY-033-AC-2 — unit (table-driven over the five filters), colocated
  `src/ollama_llm_bench/backend/charts/tests/test_global_filters.py`,
  `test_each_global_filter_keeps_matching_rows`. Covers CA-25, CA-26.
- STORY-033-AC-3 — unit (table-driven over completed/non-completed mixes), colocated
  `src/ollama_llm_bench/backend/charts/tests/test_status_prefilter.py`,
  `test_status_prefilter_per_chart_kind`. Covers CA-6.
- STORY-033-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/charts/tests/test_min_sample_size.py`,
  `test_low_sample_group_is_flagged`.
- STORY-033-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/charts/tests/test_outlier_handling.py`,
  `test_iqr_outlier_dropped_when_toggle_on_box_plot_keeps`. Covers CA-5, CA-24.
- STORY-033-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/charts/tests/test_mode_gate.py`,
  `test_grading_chart_in_non_graded_mode_is_empty_state`. Covers CA-8; covers EC-RES-4 via the
  theme-independent structure.
- STORY-033-AC-7 — unit, colocated
  `src/ollama_llm_bench/backend/charts/tests/test_pareto_frontier.py`,
  `test_speed_vs_quality_pareto_frontier`. Covers CA-21, CA-22.
- STORY-033-AC-8 — unit (table-driven over empty-state triggers), colocated
  `src/ollama_llm_bench/backend/charts/tests/test_empty_state.py`,
  `test_empty_state_message_per_kind`. Covers CA-2, CA-11, CA-28, CA-29; covers EC-RES-1.
- STORY-033-AC-9 — unit + property, colocated
  `src/ollama_llm_bench/backend/charts/tests/test_determinism.py`,
  `test_aggregation_is_deterministic_and_snapshot_immutable`. Covers CA-27, CA-30.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-033.
- [ ] Each of the twelve chart kinds has a passing fixture-based snapshot test (STORY-033-AC-1).
- [ ] EC-RES-1 and EC-RES-4 have passing tests.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/charts/`.
- [ ] An architecture test confirms `backend/charts/` imports no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-033.
- [ ] The module inventory is unchanged.
