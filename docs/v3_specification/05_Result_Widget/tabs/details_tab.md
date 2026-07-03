# Result Widget — Details Tab

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `05_Result_Widget/description.md`; `05_Result_Widget/tabs/summary_tab.md`; `05_Result_Widget/tabs/charts_tab.md`; `05_Result_Widget/implementation_structure.md`; `08_Cross_Cutting/08-G_feature_flags.md`; `08_Cross_Cutting/08-H_app_modes.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `10_Domain_and_Data/05_EXPORT_FORMATS.md`; `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`; `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`

The Details tab presents one row per `BenchmarkResult` of the selected run — the most granular view in the Result Widget. Every column maps directly to a field of the `BenchmarkResult` record. Selecting a row reveals that result's full long-form data — the prompts sent, the model response, the per-phase evaluation, the judge reasoning, the error, and the inference-attempt history — in the Task Detail Panel below the table. The tab supports filtering, per-column filtering, sorting, column-visibility control, column reordering, and export, and its view state persists per run.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Column reference
4. Mode-aware column visibility
5. Filter bar
6. Per-column filter
7. Column-visibility control and reordering
8. Sorting
9. Row selection and the Task Detail Panel
10. Chart-click drill-down
11. Verdict and status rendering
12. Empty and partial states
13. Live update
14. Export
15. Persistence
16. Event-bus integration
17. Edge cases
18. Function inventory

---

## 1. Role and ownership

The Details tab owns the per-result, one-row-per-`BenchmarkResult` view of a single run. It is responsible for:

- Rendering one table row per result row of the selected run.
- Filtering and per-column filtering the row set, and sorting it.
- Loading the Task Detail Panel for the selected row — the full prompts, response, per-phase evaluation, judge reasoning, error, and attempt history.
- Receiving a chart-click drill-down from the Charts tab and applying it as a filter.
- Exporting the currently filtered, visible-column, sorted rows as CSV or Markdown.

The tab does not own run selection (the parent Result Widget does — see `05_Result_Widget/description.md`), the aggregated per-model view (the Summary tab does — see `summary_tab.md`), or any chart computation (the Charts tab does — see `charts_tab.md`).

## 2. Layout

```
+--------------------------------------------------------------------+
| Filters: [Models N/M v] [Tasks K/T v] [Category v] [Status v]      |  <- filter bar
|          [Verdict v] [Layer v] [Difficulty v] [Clear filters]      |
|                                       [Columns N/M] [Detach]       |
+--------------------------------------------------------------------+
| Provider / Model | Task | Cat | Status | Time | TTFT | Tokens | ...|  <- results table
| ---------------- + ---- + --- + ------ + ---- + ---- + ------ + ---|
| ... one row per BenchmarkResult ...                                |
+--------------------------------------------------------------------+
| Task detail — <task_id> — <provider / model>                       |
|   meta - prompts - golden - response - per-phase - judge - error   |  <- Task Detail Panel
+--------------------------------------------------------------------+
| [Export CSV] [Export Markdown]   [x] Save to app data folder       |  <- uniform footer
+--------------------------------------------------------------------+
```

The filter bar sits above the table; the compact, horizontally scrollable table fills the upper centre; the Task Detail Panel occupies the lower region and grows as content requires; the uniform footer (shared by every Result Widget tab — see `05_Result_Widget/description.md`) carries the export controls. The mockup `05_Result_Widget/mockup.html` is the visual source of truth.

## 3. Column reference

Every column is one field of the `BenchmarkResult` record (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` section 6.10) or of its joined `BenchmarkTask`. Columns marked **Default `yes`** are visible when a run is opened for the first time; the rest are hidden until the user enables them through the column-visibility control (section 7). Column visibility is additionally constrained by run mode (section 4).

Status terms refer to `ResultStatus` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` section 4.3); verdict terms refer to `Verdict` (section 4.4); the resolution layer refers to `ResolutionLayer` (section 4.5).

| # | Column | Source field | Format | Default |
|---|---|---|---|:--:|
| 1 | Provider / Model | `provider_name` + `model_name` — displayed; the composite key for grouping is `(provider_id, model_name)` but the cell renders the SNAPSHOT `provider_name` from `BenchmarkResult.provider_name` (DD-33) so historical fidelity is preserved across a later provider rename. The internal `provider_id` is never displayed. | text, monospace | yes |
| 2 | Task | `task_id` | text, monospace | yes |
| 3 | Category | joined `BenchmarkTask.category` | text | yes |
| 4 | Sub-category | joined `BenchmarkTask.sub_category` | text | no |
| 5 | Difficulty | joined `BenchmarkTask.difficulty` | badge — easy / medium / hard | no |
| 6 | Category | joined `BenchmarkTask.category` | text | no |
| 7 | Status | `status` | badge | yes |
| 8 | Time (ms) | `total_time_ms` | integer | yes |
| 9 | TTFT (ms) | `ttft_ms` | integer | yes |
| 10 | Prompt tokens | `prompt_tokens` | integer | no |
| 11 | Tokens | `completion_tokens` | integer | yes |
| 12 | TPS | `tokens_per_second` | `42.10`, or `≈42.10` when `tokens_estimated` (SPEC-047) | yes |
| 13 | Sanity check | `sanity_check_passed` | badge — ok / failed / — | no |
| 14 | Keyword | `keyword_verdict` | badge — pass / fail / — | no |
| 15 | Cosine Score | `cosine_similarity` | per `ui.score_display_format` | yes |
| 16 | Cosine verdict | `cosine_verdict` | badge — pass / fail / — | no |
| 17 | Judge | `judge_verdict` | badge — pass / fail / — | no |
| 18 | Layer | `resolution_layer` | badge — keyword / cosine / judge / skip | yes |
| 19 | Verdict | `verdict` | badge — pass / fail / — | yes |
| 20 | Reason | `judge_reasoning` (clipped to one line; full text in the detail panel) | text | no |
| 21 | Error | `error_message` (clipped to one line; full text in the detail panel) | text | no |
| 22 | Attempts | length of `attempts` | integer | no |
| 23 | Started at | `started_at` | timestamp | no |
| 24 | Finished at | `finished_at` | timestamp | no |

### 3.1 What the quality columns mean

- **Cosine Score (column 15)** is `cosine_similarity` — the cosine similarity of the model's response to the task's golden answer, on a `0.0`–`1.0` scale (`CosineScore`). It is the **only numeric quality value** in the application.
- **Judge (column 17)** is `judge_verdict` — the judge phase's binary `PASS` / `FAIL` outcome. The judge produces **no numeric score**; it contributes a binary verdict plus the free-text `judge_reasoning`. There is no judge-score column because no such number exists.
- **Verdict (column 19)** is the combined `BenchmarkResult.verdict`, the binary outcome decided by the highest enabled evaluation phase. **Layer (column 18)** records which phase decided it (`KEYWORD`, `COSINE`, `JUDGE`, or `SKIP`).
- Columns 14, 16, and 17 — Keyword, Cosine verdict, Judge — are each phase's **own** binary verdict; the combined Verdict (19) may differ from any single one because it is decided by the highest enabled phase.

### 3.2 Empty-cell rule

A cell whose source field is `None` — `ttft_ms` on a transport without streaming, `cosine_similarity` on a result that ran no cosine check, `judge_reasoning` on a result the judge never evaluated — renders an em dash (`—`), never `0` and never a blank. A `0` is reserved for a genuine measured or counted zero. A failed result (a terminal-failure status) renders the metric columns it never reached as em dashes.

## 4. Mode-aware column visibility

The grading columns are meaningful only when the run produces verdicts and Cosine Scores. The mode-visibility policy (`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`) decides, from `BenchmarkRun.run_mode`, which columns the table offers. A column hidden by mode is absent from the table **and** from the column-visibility control — the user cannot enable it for that run.

| Column group | `SYNTHETIC` | `TASKS` | `GRADED` |
|---|:--:|:--:|:--:|
| Provider / Model, Task, Category, Sub-category, Difficulty, Type | offered | offered | offered |
| Status, Time, TTFT, Prompt tokens, Tokens, TPS, Attempts | offered | offered | offered |
| Started at, Finished at, Error | offered | offered | offered |
| Sanity check, Keyword, Cosine Score, Cosine verdict | hidden | hidden | offered |
| Judge, Layer, Verdict, Reason | hidden | hidden | offered |

A `SYNTHETIC` run runs synthetic tasks with no golden answer and never grades; a `TASKS` run runs real tasks but also never grades — Task Benchmark and Synthetic Benchmark both measure timing and throughput only, and the only difference between them is the prompt source. Neither produces the verdicts, Cosine Scores, or judge reasoning the grading columns display, so the policy never offers them. The table re-applies the policy immediately when the parent Result Widget switches the selected run, so the column set always matches the displayed run's mode.

## 5. Filter bar

The filter bar holds seven multi-select filter chips and the Clear-filters control. Each chip opens a multi-select dropdown over the distinct values found in the current run's results. The chip label shows the active count against the total (`Models 3 / 5`); a chip whose selection excludes at least one value renders in the active style.

| Chip | Domain | Default | Notes |
|---|---|---|---|
| Models | distinct `(provider_id, model_name)` of the run | all selected | Toggling a model off hides every row for that model. |
| Tasks | distinct `task_id` of the run | all selected | Selects which tasks are shown. |
| Category | distinct `BenchmarkTask.category` of the run | all selected | Filters on task category. |
| Status | `ResultStatus` members present in the run | all selected | Multi-select over the eleven statuses (`PENDING`, `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`, `COMPLETED`, `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`). |
| Verdict | `PASS`, `FAIL`, *ungraded* (`verdict is None`) | all selected | Multi-select. |
| Layer | `ResolutionLayer` members — keyword / cosine / judge / skip | all selected | Multi-select. |
| Difficulty | `Difficulty` members — easy / medium / hard | all selected | Multi-select. |

A row is shown only when it passes every chip. Unlike the Summary tab, the Details tab does not re-aggregate — each chip simply includes or excludes whole result rows. The Category, Status, Difficulty, and Tasks chips are offered in every mode. The **Verdict and Layer chips are offered only in `GRADED`**, the only mode that produces verdicts and resolution layers; they are not shown in `TASKS` or `SYNTHETIC`, where every result is ungraded (`verdict is None`, `resolution_layer is None`).

**Clear filters** resets every chip and every per-column filter (section 6) to "all selected". It is enabled only while at least one filter is non-default.

## 6. Per-column filter

Right-clicking a column header opens the same multi-select dropdown, scoped to that column's distinct values in the current run. The per-column filter composes with the filter-bar chips: a row is shown only when it passes the filter-bar chips **and** every active per-column filter. The per-column filter is the convenient way to narrow a low-cardinality column — `Status`, `Layer`, `Difficulty` — that also has a filter-bar chip, and the only way to narrow a column that has no chip — for example `Type` or `Sub-category`.

A column header with an active per-column filter shows a small filter glyph. The per-column filter set is part of the per-run view state (section 15) and is cleared by **Clear filters**.

## 7. Column-visibility control and reordering

A `Columns` control on the right of the filter bar opens a popover listing every mode-offered column with a toggle. A column hidden by mode (section 4) is absent from this popover. The control's label shows the visible-count fraction (`Columns 11 / 24`). In the fraction `N / M`, **`M` is the count of columns the current run mode offers** (section 4) — the mode-offered subset, **not** a fixed number — and `N` is how many of those are currently visible. `GRADED` offers all **24** columns of the §3 master list (the count shown in the mockup); `SYNTHETIC` and `TASKS` drop the grading columns from `M`, so the denominator is smaller in those modes. The popover footer carries `Reset` (restore the mode's default visibility) and `Done` (close — the primary action, placed right-most per the UI standardization rules).

Column headers support drag-to-reorder. The `Provider / Model` column is pinned as the first column and cannot be moved or hidden. Column visibility and column order are part of the per-run view state (section 15).

## 8. Sorting

- Clicking a column header sorts ascending; clicking again flips to descending; a third click clears the sort and restores the default order.
- Numeric columns sort numerically, never lexicographically. An em-dash (empty) cell sorts as the lowest value, after the genuine zeros.
- Timestamp columns sort chronologically.
- The default sort is **Time (ms), descending** — the slowest results first, so outliers are immediately visible.

The active sort is part of the per-run view state (section 15).

## 9. Row selection and the Task Detail Panel

Selecting a single table row loads the **Task Detail Panel** below the table. The panel is a vertically scrollable region; it updates instantly on row selection, and if its height makes the tab body scrollable the table area shrinks accordingly. Multi-select for a bulk export is performed by ticking each row's selection checkbox in the row header; ticking multiple checkboxes does not change the panel — it scopes the bulk export to the ticked rows (section 14).

The Task Detail Panel is a **complete, structured dump of everything the application recorded for the selected result** — both the frozen task definition (every field of the `BenchmarkTask` as it was saved, i.e. the YAML task's fields) **and** every field of the `BenchmarkResult` row and its child rows (`benchmark_result_terms`, `benchmark_result_attempts`). Nothing recorded for the result is hidden from this panel; it is the authoritative single-record inspector. It renders, in this order:

1. **Identity & meta key/value grid** — the target identity `provider_name` and `model_name`, the run mode; the task identity and definition fields `task_id`, category and sub-category, difficulty, `cosine_enabled`; the timing metrics `total_time_ms`, `ttft_ms`, `tokens_per_second`; the token metrics `prompt_tokens` and `completion_tokens`; the outcome fields `status`, the combined `verdict`, the `resolution_layer`, the `cosine_similarity` Cosine Score; the attempt count; and the `started_at` / `finished_at` timestamps. Every value is labelled; a value that is `None`/absent renders as an em dash so the field is still visible.
2. **Prompts sent to the model** — the verbatim prompt text in a monospace block. When the request carried both a `system_prompt_sent` and a `user_prompt_sent`, both are shown as separate labelled blocks; when only one is present, only that block appears.
3. **Golden answer** — the task's reference answer (`BenchmarkTask.golden_answer`) in a monospace block; absent for a `SYNTHETIC` synthetic task, which carries no golden answer.
4. **Model response** — the `sanitized_response` (reasoning blocks stripped) in full, in a monospace block. When `has_thinking_block` is true the panel notes that a reasoning block was present and stripped and offers an expander to reveal the **raw response** (`raw_response`, including the reasoning block) so the complete recorded output is available, not just the graded text.
5. **Per-phase evaluation** — one row per evaluation phase that ran: the sanity check, the keyword phase, the cosine phase, and the judge phase. Each row shows the phase's outcome, its measurement (the per-term keyword tallies from `terms`, the `cosine_similarity` against its scope band, the judge's binary verdict), and a one-line description of how the outcome was reached.
6. **Judge reasoning** — the full `judge_reasoning` text — the judge's binary verdict together with its free-text explanation — or "(none)" when the judge phase did not run. The judge never returns a numeric score.
7. **Error** — the full `error_message`, or "(none)" when the result carries no error.
8. **Attempts** — the per-attempt history from `attempts`: each `BenchmarkResultAttempt` shows its 1-based index, its timeout budget, its duration, its outcome (`SUCCESS` / `TIMEOUT` / `ERROR`), and, for a failed attempt, its `error_kind` and `error_message`.

Sections 3–6 render empty or "(none)" for a run mode that performs no grading — a `SYNTHETIC` or `TASKS` run has no golden answer, no per-phase grading rows, and no judge reasoning. The panel can be detached into its own window through the toolbar's `Detach window` action (see `description.md` section 8).

## 10. Chart-click drill-down

The Charts tab supports drill-down: clicking a chart element switches the Result Widget to the Details tab and applies a filter that narrows the table to the rows behind that element (see `charts_tab.md`). The applied filter is one of:

- A **single-model** filter — the Models chip narrowed to one `(provider_id, model_name)` — when a per-model bar or scatter point is clicked.
- A **model-and-status** or **model-and-verdict** filter — when a stacked-bar segment is clicked.
- A **single-result** filter — the Tasks chip narrowed to one `task_id` and the Models chip to one model — when a scatter point or a box-plot outlier marker is clicked, with that one result's row pre-selected so its Task Detail Panel is already open.

A drill-down filter is applied on top of the run's current view state and is written back as the run's view state, so leaving and returning to the Details tab keeps the drilled-in view. **Clear filters** restores the table to "all selected".

## 11. Verdict and status rendering

Status and verdict cells render as badges in the semantic colour roles from `08_Cross_Cutting/08-D_color_palette_and_typography.md`:

| Value | Colour role |
|---|---|
| `verdict` / `keyword_verdict` / `cosine_verdict` / `judge_verdict` = `PASS` | success |
| `verdict` / `keyword_verdict` / `cosine_verdict` / `judge_verdict` = `FAIL` | error |
| `verdict` is `None` (ungraded — pending or never graded) | em dash, mute |
| `status` = `COMPLETED` | success |
| `status` in the terminal-failure set (`FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`) | error |
| `status` in the pipeline-position set (`PENDING`, `RUNNING_INFERENCE`, `AWAITING_*`) | info |

A `FAILED_JUDGE_TIMEOUT` row renders the Status badge in the error role with the label `FAILED_JUDGE_TIMEOUT`; the Verdict cell renders an em dash (the verdict is `None` for this status). The Task Detail Panel's per-phase evaluation section shows the keyword and cosine phases' own outcomes verbatim, and shows the judge phase row as **"Judge: did not complete — adaptive budget exhausted"** (when the per-task call exhausted) or **"Judge: skipped — judge model excluded for the rest of the run"** (when the judge model was excluded after the consecutive-max threshold, distinguished by inspecting `error_message`). The `error_kind` cell shows `JUDGE_TIMEOUT` (see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.16). See DD-34 in `08_Cross_Cutting/08-F_spec_issues_log.md` for the full per-role adaptive-timeout model.
| `resolution_layer` = `KEYWORD` / `COSINE` / `JUDGE` | info |
| `resolution_layer` = `SKIP` | mute |

A completed result with `verdict == FAIL` is a graded result that did not pass; it is **not** a failure — its `status` is `COMPLETED` (success role) while its `verdict` badge is `FAIL` (error role). The two concepts — a run-time error versus a low-quality graded answer — are kept strictly separate, matching the `ResultStatus` / `Verdict` split in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` section 4.

## 12. Empty and partial states

| State | Condition | Rendering |
|---|---|---|
| No run selected | the Result Widget has no run selected | the tab shows `Select a run to view its results.` |
| No results yet | the run has zero result rows | the table shows `Detailed results will appear here once tasks complete.`; the Task Detail Panel shows `Select a row to inspect it.`; the export buttons are disabled until no run is in progress |
| Filter excludes everything | an active filter or per-column filter leaves no row | the table shows `No rows match the current filters.` with a `Clear filters` affordance |
| No row selected | rows exist but none is selected | the table renders; the Task Detail Panel shows `Select a row to inspect it.` |

A partial run — still in progress, or stopped — renders normally; rows appear as the pipeline produces them, and a row's metric columns fill in as it advances through the phases.

## 13. Live update

While the selected run is the active run, per-task completion advances the run's results. The tab subscribes to `_detailed_data_changed` on the event bus and re-renders on a **250 ms debounce** so a burst of completions causes one repaint, not many (EC-PERF-3). Across a repaint the tab preserves the active sort, every filter and per-column filter, the column-visibility set, the column order, and the selected row — selection is matched by `result_id`, so the Task Detail Panel stays on the same result. A run that is not the active run never live-updates; its Details tab is a static view of stored results.

## 14. Export

The uniform footer carries `Export CSV` and `Export Markdown`. Both export the **currently filtered, currently visible-column, currently sorted** rows — the export mirrors exactly what the user sees. When more than one row is selected, the export is narrowed to the selected rows only.

- **Export CSV** writes the rows as CSV with the column headers in row 1.
- **Export Markdown** writes the same rows as a GitHub-flavoured Markdown table.

Both buttons are **disabled while any run is in a non-terminal state** (see `description.md` section 7). The save behaviour — direct write to `<app_data>/exports/` versus a save picker — follows the `ui.export_save_directly` rule shared by every Result Widget tab. The serialised document, its column order, and its escaping are fixed by `10_Domain_and_Data/05_EXPORT_FORMATS.md`; the payload is produced by the table serialisation service (`11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`). The filename is `<effective_run_name>_Details.<csv|md>`.

## 15. Persistence

The Details tab's view state — the filter-chip selection, the per-column filter set, the column-visibility set, the column order, and the active sort — is persisted **per run**, keyed by `run_id`, by the result-table persistence model in `08_Cross_Cutting/08-G_feature_flags.md` section 10:

- A run opened for the first time uses the built-in default view state for the Details table and the run's mode — all filters selected, no per-column filters, the mode's default column visibility, the default column order, and the default Time-descending sort.
- A previously-opened run is restored to the exact view state the user last left it in, including a drill-down filter applied from the Charts tab.

The view state is stored against the run, not under a fixed `ui.*` key; no view state crosses between runs. The selected row and the Task Detail Panel scroll position are session state, not persisted across an application restart.

## 16. Event-bus integration

All subscriptions are owner-bound to the tab; the bus auto-cancels them on destruction. A detached Details window subscribes with itself as owner.

| Direction | Signal | Handler effect |
|---|---|---|
| Subscribes | `_detailed_data_changed` (for the displayed run) | refresh the row cache; debounced re-render (section 13) |
| Subscribes | `_run_id_changed` (from the parent Result Widget) | reload the run, re-apply the mode column policy, restore the run's view state, clear the selection |
| Subscribes | `_run_started`, `_run_finished`, `_run_stopped`, `_run_failed` | enable or disable the export buttons as runs enter or leave a non-terminal state |

The tab emits no run-mutating event — it is a read-only view. The chart-click drill-down (section 10) arrives as an in-process request from the Charts tab through the parent controller, not as an event-bus signal.

## 17. Edge cases

| ID | Concern | Handling |
|---|---|---|
| EC-RUN-3 | the selected run failed | the partial rows render cleanly; the metric columns a result never reached show em dashes; the Task Detail Panel shows whatever phase data exists |
| EC-RES-1 | a run with zero completed results | the table shows its empty state; an export when no run is in progress produces a header-only file |
| EC-RES-2 | the same model name served by two providers | the composite `(provider_id, model_name)` keeps the rows distinct; the Models chip lists them separately |
| EC-RES-5 | a direct-write export fails | an error modal reports the failure; the table state and the selection are unchanged |
| EC-RES-6 | a run name that sanitises to an empty string | the export filename falls back to `Run_<run_id>_Details.<csv|md>` |
| EC-PERF-3 | a high rate of task completions during a live run | the 250 ms debounce coalesces the repaints; sort, filters, and the selected row are preserved |
| DT-EC-1 | a result with `ttft_ms` null because its transport does not stream | the TTFT cell shows an em dash, not `0` (section 3.2) |
| DT-EC-2 | a chart-click drill-down arrives while a manual filter is already active | the drill-down filter replaces the conflicting chips and is written back as the run's view state (section 10) |

## 18. Function inventory

| Function | Primitive | Enabled when |
|---|---|---|
| Filter — Models / Tasks / Category / Status / Verdict / Layer / Difficulty | multi-select filter chip | always; selection persists per run |
| Per-column filter | right-click a column header | always; persists per run |
| Clear filters | button | at least one filter or per-column filter is non-default |
| Open the column-visibility control | button opening a popover | always; selection persists per run |
| Toggle a column | toggle inside the popover | always for any mode-offered column |
| Reset column visibility | button in the popover footer | always |
| Reorder columns | drag a column header | always except the pinned Provider / Model column |
| Sort by a column | click a column header | always; sort persists per run |
| Select a row | click a row | always; loads the Task Detail Panel |
| Multi-select rows | tick each row's selection checkbox in the row header | always; scopes a bulk export |
| Receive a chart-click drill-down | implicit, from the Charts tab | always; applies and persists a filter |
| Detach the tab into a window | button | always — a detached view is read-only-safe during a run |
| Export CSV | button in the footer | no run is in a non-terminal state |
| Export Markdown | button in the footer | no run is in a non-terminal state |
| Toggle save-directly / Open Exports Folder | toggle plus button in the footer | always; shared across every Result Widget tab |
