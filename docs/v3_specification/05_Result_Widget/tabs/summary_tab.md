# Result Widget — Summary Tab

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `05_Result_Widget/description.md`; `05_Result_Widget/tabs/details_tab.md`; `05_Result_Widget/tabs/charts_tab.md`; `08_Cross_Cutting/08-G_feature_flags.md`; `08_Cross_Cutting/08-H_app_modes.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`; `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`

The Summary tab presents per-model aggregated statistics for the selected run. It renders one row per composite model identity `(provider_id, model_name)`, computed by aggregating every `BenchmarkResult` of the run that belongs to that identity. Column visibility is mode-aware: a `SYNTHETIC` or `TASKS` run hides the grading columns because it produces no verdict and no Cosine Score. The tab supports filtering, per-column filtering, sorting, column-visibility control, column reordering, and export, and its view state persists per run.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Identity model
4. Column reference
5. Mode-aware column visibility
6. Filter bar (6.1 Per-column filter)
7. Column-visibility control and reordering
8. Sorting
9. Empty and partial states
10. Live update
11. Export
12. Persistence
13. Event-bus integration
14. Edge cases
15. Function inventory

---

## 1. Role and ownership

The Summary tab owns the aggregated, one-row-per-model view of a single run. It is responsible for:

- Grouping the run's `BenchmarkResult` rows by the composite key `(provider_id, model_name)` and presenting one aggregate row per group.
- Re-aggregating those rows whenever a filter narrows the set of contributing results.
- Applying mode-aware column visibility so grading columns never appear for a non-grading run.
- Exporting the currently filtered, visible, and sorted rows as CSV or Markdown.

The tab does not own run selection (the parent Result Widget does — see `05_Result_Widget/description.md`), the per-result drill-down (the Details tab does — see `details_tab.md`), or any chart computation (the Charts tab does — see `charts_tab.md`).

## 2. Layout

```
+--------------------------------------------------------------------+
| Filters: [Models N/M v] [Verdict v] [Difficulty v] [Category v]    |  <- filter bar
|          [Clear filters]                  [Columns N/M] [Detach]   |
+--------------------------------------------------------------------+
| Provider / Model | Tasks | Avg Time | Avg TTFT | Avg TPS | ...     |  <- summary table
| ---------------- + ----- + -------- + -------- + ------- + ------- |
| ... aggregate rows, one per (provider, model) ...                  |
+--------------------------------------------------------------------+
| [Export CSV] [Export Markdown]   [x] Save to app data folder       |  <- uniform footer
+--------------------------------------------------------------------+
```

The filter bar sits above the table; the table fills the centre; the uniform footer (shared by every Result Widget tab — see `05_Result_Widget/description.md`) carries the export controls.

## 3. Identity model

The Summary table groups by the composite key `(provider_id, model_name)` — the `ModelDescriptor` pair from `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §6.1. Two providers that expose a model of the same name produce **two distinct rows**; the rows are never merged. The displayed label is `<provider_name> / <model_name>` where `provider_name` is the SNAPSHOT name read from `BenchmarkResult.provider_name` (the value captured at task start; DD-33) — never the current name from the live catalog. This preserves historical fidelity: renaming a provider after the run completes does not retroactively relabel the Summary rows. The internal `provider_id` is the grouping key but is never displayed. The Details tab, every chart, and the run analysis use the same composite key and the same snapshot-name rendering rule, so a model selected on one tab refers to the same identity on every other.

## 4. Column reference

Every column is an aggregation over the `BenchmarkResult` rows of one `(provider_id, model_name)` group. Columns marked **Default `yes`** are visible when a run is opened for the first time; the rest are hidden until the user enables them through the column-visibility control (§7). Column visibility is additionally constrained by run mode (§5): a column hidden by mode is absent from the table and from the column-visibility control regardless of its default.

Status terms used below refer to `ResultStatus` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.3). *Completed* means `status == COMPLETED`. *Failed* means a terminal-failure status — `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, or `ERRORED`. *Incomplete* means a pipeline-position status — `PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, or `AWAITING_JUDGE_CHECK`.

| # | Column | Aggregation | Format | Default |
|---|---|---|---|:--:|
| 1 | Provider / Model | The composite key; the group label | text, monospace | yes |
| 2 | Tasks | Count of all result rows in the group | integer | yes |
| 3 | Completed | Count of rows with `status == COMPLETED` | integer | no |
| 4 | Failed | Count of rows in a terminal-failure status | integer | yes |
| 5 | Incomplete | Count of rows in a pipeline-position status | integer | no |
| 6 | Avg Time (s) | Mean of `total_time_ms / 1000` over completed rows | `12.34` | yes |
| 7 | Median Time (s) | Median of `total_time_ms / 1000` over completed rows | `11.20` | no |
| 8 | Avg TTFT (s) | Mean of `ttft_ms / 1000` over completed rows with a non-null `ttft_ms` | `1.23` | yes |
| 9 | Avg TPS | Mean of `tokens_per_second` over completed rows with a non-null value. Marked `≈` when any averaged row has `tokens_estimated` (no-usage backend; SPEC-047), and marked **⧉** when any averaged row has a reasoning block (`has_thinking_block`) — TPS then includes reasoning tokens and is not directly comparable across thinking/non-thinking models (MISS-08, SPEC-093). | `42.1` / `≈42.1` / `⧉42.1` | yes |
| 10 | Avg Tokens | Mean of `completion_tokens` over completed rows with a non-null value | integer | yes |
| 11 | Pass Rate | Fraction of completed rows with `verdict == PASS` | per `ui.score_display_format` | yes |
| 12 | Cosine Score | Mean of `cosine_similarity` over completed rows with a non-null Cosine Score | per `ui.score_display_format` | yes |
| 13 | Judge PASS | Count of rows whose `judge_verdict == PASS` | integer | no |
| 14 | Judge FAIL | Count of rows whose `judge_verdict == FAIL` | integer | no |
| 15 | Timeout failures | Count of rows with `status == FAILED_TIMEOUT` (test-role inference timeouts, Phase 2) | integer | no |
| 15a | Judge-timeout failures | Count of rows with `status == FAILED_JUDGE_TIMEOUT` (per-task judge call exhausted its budget, OR the judge model was excluded for the run — Phase 4). Offered only in `GRADED`. | integer | no |
| 16 | Provider failures | Count of rows with `status == FAILED_PROVIDER` | integer | no |
| 17 | Layer mix | Distribution of `resolution_layer` across the group's completed rows | mini stacked bar (keyword / cosine / judge / skip) | no |
| 18 | Avg attempts | Mean length of `attempts` per task in the group | `1.4` | no |

### 4.1 What the quality columns mean

- **Cosine Score (column 12)** is the mean `cosine_similarity` of the group. It is the **only numeric quality value** in the application — the cosine similarity of the model's response to the task's golden answer, on a `0.0`–`1.0` scale (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §3, `CosineScore`). **Partial-coverage flag (DD-63):** the cell additionally carries a `⚠` marker when this model's cosine coverage — `count(non-null cosine_similarity) / count(cosine-eligible completed rows)`, where cosine-eligible means the task had a golden answer and `cosine_enabled` — falls below `eval.min_cosine_coverage` (default 0.8) **while another model in the run meets it**. The tooltip reads `Graded on partial cosine coverage (N% of eligible tasks) — comparison with fully-covered models may be uneven.` This surfaces the bias from intermittent embedding failures (e.g. on one model's longer responses); the mean itself is unchanged.
- The **judge produces no numeric score**. The judge contributes only a binary `Verdict` (`PASS` / `FAIL`) plus a free-text reasoning comment. The judge's contribution to the Summary tab is therefore counted, not averaged: columns 13 and 14 count the judge's `PASS` and `FAIL` verdicts. There is no "average judge score" column because no such number exists.
- **Pass Rate (column 11)** is computed from the combined `BenchmarkResult.verdict`, the binary outcome decided by the highest enabled evaluation phase (`08_Cross_Cutting/08-G_feature_flags.md` §5). It is a rate over verdicts, not an average of a numeric score. **Sample size (SPEC-092):** every group row shows its `n` (the Tasks/Completed count), and when `n < eval.min_sample_size` (default 5) the Pass Rate (and the throughput aggregates) carry the same **low-sample marker** the charts use, so a tiny sample — e.g. a one-task model showing `100%`, or a `repeats=1` Synthetic throughput — is visibly tentative rather than presented like a large sample. No confidence interval is computed; `n` plus the marker is the honesty signal, and it is carried into the Summary export as well.

### 4.2 Counts that look similar but differ

- **Failed (column 4)** counts terminal-failure statuses — an *error* the pipeline classified as recoverable and retryable (`ResultStatus` retryable terminal states, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.3). A run that is resumed or retried resets these rows.
- **Timeout failures (15)** and **Provider failures (16)** split the Failed count into two specific causes, useful when diagnosing whether a model or a provider was the problem.
- A completed row with `verdict == FAIL` is **not** a failure — it is a graded result that did not pass. It counts toward *Completed*, not *Failed*. The two concepts — a run-time error versus a low-quality graded answer — are kept strictly separate, matching the `ResultStatus` / `Verdict` split in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.

### 4.3 Empty-aggregate rule

When a column's aggregation has no contributing rows — for example *Avg TTFT* for a group whose every completed row has a null `ttft_ms`, or *Cosine Score* for a group with no graded result — the cell renders an em dash (`—`), never `0` and never a blank. A `0` value is reserved for a genuine measured or counted zero.

## 5. Mode-aware column visibility

The grading columns are meaningful only when the run produces verdicts and Cosine Scores. The mode-visibility policy (`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`) decides, from `BenchmarkRun.run_mode`, which columns the table offers. A column hidden by mode is absent from the table **and** from the column-visibility control — the user cannot enable it for that run.

| Column | `SYNTHETIC` | `TASKS` | `GRADED` |
|---|:--:|:--:|:--:|
| Provider / Model, Tasks, Completed, Failed, Incomplete | offered | offered | offered |
| Avg Time, Median Time, Avg TTFT, Avg TPS, Avg Tokens | offered | offered | offered |
| Timeout failures, Provider failures, Avg attempts | offered | offered | offered |
| Pass Rate | hidden | hidden | offered |
| Cosine Score | hidden | hidden | offered |
| Judge PASS, Judge FAIL | hidden | hidden | offered |
| Layer mix | hidden | hidden | offered |

The grading columns (Pass Rate, Cosine Score, Judge PASS, Judge FAIL, Layer mix) are offered **only** for `GRADED`. A `SYNTHETIC` run runs synthetic tasks with no golden answer and never grades; a `TASKS` run runs real tasks but also never grades — Task Benchmark and Synthetic Benchmark both measure timing and throughput only, and the only difference between them is the prompt source. Neither produces the verdicts or Cosine Scores those columns summarise, so the policy never offers them. The table re-applies the policy immediately when the parent Result Widget switches the selected run, so the column set always matches the displayed run's mode.

## 6. Filter bar

The filter bar holds four multi-select filter chips and the Clear-filters control. Each chip opens a multi-select dropdown over the distinct values found in the current run's results. The chip label shows the active count against the total (`Models 3 / 5`); a chip whose selection excludes at least one value renders in the active style.

| Chip | Domain | Default |
|---|---|---|
| Models | Distinct `(provider_id, model_name)` of the run | all selected |
| Verdict | `PASS`, `FAIL`, *ungraded* (`verdict is None`) | all selected |
| Difficulty | `Difficulty` members — `easy`, `medium`, `hard` | all selected |
| Category | Distinct `BenchmarkTask.category` of the run | all selected |

The Verdict, Difficulty, and Category chips filter the **contributing result rows**, not whole model rows, so they **re-aggregate** the table. Hiding the `easy` difficulty, for example, recomputes every visible column from the `medium` and `hard` rows only — the Avg Time of a model then reflects only its medium and hard tasks. The Models chip removes whole model rows from the table.

The Verdict, Difficulty, and Category chips are offered in every mode; in `SYNTHETIC` and `TASKS` the Verdict chip's *ungraded* option matches every result because no result carries a verdict.

**Clear filters** resets every chip to "all selected" and every per-column filter (§6.1). It is enabled only while at least one chip or per-column filter is non-default.

### 6.1 Per-column filter

Right-clicking a column header opens the same multi-select dropdown, scoped to that column's distinct values across the run's contributing result rows. The per-column filter composes with the filter-bar chips: a row contributes to a model's aggregate only when it passes the filter-bar chips **and** every active per-column filter. As with the chips, a per-column filter that narrows a contributing-row column (for example Difficulty or Category) **re-aggregates** the table — the visible columns recompute from the surviving rows only. A column header with an active per-column filter shows a small filter glyph.

The per-column filter is the convenient way to narrow a low-cardinality column that also has a filter-bar chip, and the only way to narrow a contributing-row attribute that has no chip. The per-column filter set is part of the per-run view state (§12) and is cleared by **Clear filters**.

## 7. Column-visibility control and reordering

A `Columns` control on the right of the filter bar opens a popover listing every mode-offered column with a toggle. A column hidden by mode (§5) is absent from this popover. The control's label shows the visible-count fraction (`Columns 9 / 14`). In the fraction `N / M`, **`M` is the count of columns the current run mode offers** (§5) — the mode-offered subset, **not** the full master column list of §4 — and `N` is how many of those are currently visible. The denominator therefore changes with run mode: `GRADED` offers **14** columns (the count shown in the mockup), and the grading-only columns are absent from `M` in `SYNTHETIC` and `TASKS`. The popover footer carries `Reset` (restore the mode's default visibility) and `Done` (close — the primary action, placed right-most per the UI standardization rules).

Column headers support drag-to-reorder. The Provider / Model column is pinned as the first column and cannot be moved or hidden.

Column visibility and column order are part of the per-run view state (§12).

## 8. Sorting

- Clicking a column header sorts ascending; clicking again flips to descending; a third click clears the sort and restores the default order.
- Numeric columns sort numerically, never lexicographically. An em-dash (empty-aggregate) cell sorts as the lowest value, after the genuine zeros, so empty groups gather at the bottom of an ascending sort.
- The default sort is **Avg TPS, descending** — fastest model first.

The active sort is part of the per-run view state (§12).

## 9. Empty and partial states

| State | Condition | Rendering |
|---|---|---|
| No run selected | The Result Widget has no run selected | The tab shows `Select a run to view its summary.` |
| No results yet | The run has zero result rows | The table shows `This run has no results yet.` and the export buttons are disabled |
| No completed results | The run has rows but none has reached `COMPLETED` | Rows still render; the timing and grading aggregates show em dashes; the message strip reads `No completed results yet — aggregates will fill in as tasks finish.` |
| Filter excludes everything | An active filter leaves no contributing row | The table shows `No rows match the current filters.` with a `Clear filters` affordance |

A partial run (a run still in progress, or a stopped run) renders normally — the aggregates simply reflect whatever results exist so far.

## 10. Live update

While the selected run is the active run, per-task completion advances the run's results. The tab subscribes to the run-results-changed event on the event bus and re-aggregates on a **500 ms debounce** so a burst of completions causes one refresh, not many. Across a refresh the tab preserves the active sort, every filter selection, the column-visibility set, and the column order. A run that is not the active run never live-updates; its Summary tab is a static view of stored results.

## 11. Export

The uniform footer carries two export buttons. Both export the **currently filtered, currently visible-column, currently sorted** rows — the export mirrors exactly what the user sees.

- **Export CSV** writes the rows as CSV with the column headers in row 1.
- **Export Markdown** writes the same rows as a GitHub-flavoured Markdown table.

Both buttons are **disabled while any run is in a non-terminal state** — export is offered only when no run is executing, so a partially-written run cannot be exported mid-flight. The save behaviour (direct write to `<app_data>/exports/` versus a save picker) follows the `ui.export_save_directly` rule shared by every Result Widget tab (`08_Cross_Cutting/08-G_feature_flags.md` §7, `05_Result_Widget/description.md`). The filename is `<effective_run_name>_Summary.<csv|md>`; the column order and content of the export are fixed by `10_Domain_and_Data/05_EXPORT_FORMATS.md`.

## 12. Persistence

The Summary tab's view state — the filter-chip selection, the per-column filter set, the column-visibility set, and the column order, plus the active sort — is persisted **per run**, keyed by `run_id`, by the result-table persistence model in `08_Cross_Cutting/08-G_feature_flags.md` §10:

- A run opened for the first time uses the built-in default view state for the Summary table and the run's mode — all filters selected, no per-column filters, the mode's default column visibility, the default column order, and the default Avg-TPS-descending sort.
- A previously-opened run is restored to the exact view state the user last left it in.

The view state is not stored under a fixed `ui.*` key; it is stored against the run. No view state crosses between runs.

## 13. Event-bus integration

| Direction | Event | Purpose |
|---|---|---|
| Subscribes | run-results-changed (for the displayed run) | Triggers the debounced re-aggregation (§10) |
| Subscribes | selected-run-changed (from the parent Result Widget) | Re-loads the run, re-applies the mode column policy, restores the run's view state |
| Subscribes | run-status-changed | Enables or disables the export buttons as the run enters or leaves a non-terminal state |

The exact payload Structs are catalogued in the event-bus catalog; this tab consumes them and never emits run-mutating events — it is a read-only view.

## 14. Edge cases

| ID | Concern | Handling |
|---|---|---|
| SUM-EC-1 | A run with zero completed results | Rows render; aggregates show em dashes; the partial-state message appears (§9) |
| SUM-EC-2 | The same model name served by two providers | The composite key keeps the two rows distinct; they are never merged (§3) |
| SUM-EC-3 | A model whose every completed row has a null `ttft_ms` (transport without streaming) | The Avg TTFT cell shows an em dash, not `0` (§4.3) |
| SUM-EC-4 | A `GRADED` run whose judge phase was disabled in Settings | Judge PASS / Judge FAIL columns are still offered (mode is `GRADED`) but every cell is `0`; Pass Rate and Cosine Score still reflect the keyword and cosine phases |
| SUM-EC-5 | A filter selection that excludes every contributing row | The table shows the no-rows-match state with a Clear-filters affordance (§9) |
| SUM-EC-6 | A direct-write export fails (disk full, permission denied) | An error dialog reports the failure; the table state is unchanged |
| SUM-EC-7 | A burst of task completions during a live run | The 500 ms debounce coalesces them into one re-aggregation; sort and filters are preserved (§10) |
| SUM-EC-8 | The run is switched while a sort and filters are active | The new run's own stored view state is restored; it does not inherit the previous run's state (§12) |

## 15. Function inventory

| Function | Primitive | Enabled when |
|---|---|---|
| Filter — Models / Verdict / Difficulty / Category | Multi-select filter chip | Always; selection persists per run |
| Per-column filter | Right-click a column header | Always; persists per run |
| Clear filters | Button | At least one chip or per-column filter is non-default |
| Open the column-visibility control | Button opening a popover | Always; selection persists per run |
| Toggle a column | Toggle inside the popover | Always for any mode-offered column |
| Reset column visibility | Button in the popover footer | Always |
| Reorder columns | Drag a column header | Always except the pinned Provider / Model column |
| Sort by a column | Click a column header | Always; sort persists per run |
| Detach the tab into a window | Button | Always (a detached view is read-only-safe during a run) |
| Export CSV | Button in the footer | No run is in a non-terminal state |
| Export Markdown | Button in the footer | No run is in a non-terminal state |
| Toggle save-directly / Open Exports Folder | Toggle plus button in the footer | Always; shared across every Result Widget tab |
