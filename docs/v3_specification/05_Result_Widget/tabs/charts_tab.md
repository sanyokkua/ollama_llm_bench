# Result Widget — Charts Tab

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `05_Result_Widget/description.md`; `05_Result_Widget/tabs/summary_tab.md`; `05_Result_Widget/tabs/details_tab.md`; `05_Result_Widget/charts_gallery.html`; `05_Result_Widget/implementation_structure.md`; `08_Cross_Cutting/08-G_feature_flags.md`; `08_Cross_Cutting/08-H_app_modes.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `10_Domain_and_Data/05_EXPORT_FORMATS.md`; `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`; `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`

The Charts tab presents the run's data as visualisations — twelve chart kinds, each a focused answer to one analytical question. It shows one chart at a time, navigated with prev/next controls and a chart-kind dropdown. The visible chart set is mode-aware: a `SYNTHETIC` or `TASKS` run offers six charts; a `GRADED` run offers all twelve. The tab exposes global filter chips, per-chart options, detach-to-window, chart-click drill-down into the Details tab, and PNG/SVG export, and its view state persists per run.

---

## Table of Contents

1. Role and ownership
2. Layout
3. The twelve chart kinds
4. Mode-availability matrix (4.1 Shared meta line)
5. Global filter chips
6. Per-chart options (6.1 Low-sample rendering contract)
7. Prev/next navigation and the chart-kind dropdown
8. Chart-click drill-down
9. Detach to window
10. Live update
11. Empty states
12. Export
13. Persistence
14. Event-bus integration
15. Edge cases
16. Function inventory

---

## 1. Role and ownership

The Charts tab owns the visualised view of a single run. It is responsible for:

- Offering the mode-aware subset of the twelve chart kinds and rendering the one currently selected.
- Applying the five global filter chips and the active chart's per-chart options, then requesting a prepared dataset from the chart-aggregation service.
- Painting the prepared `ChartData` or `HeatmapData` on the chart canvas; the tab performs no aggregation arithmetic itself.
- Navigating prev/next within the mode-offered chart set.
- Drilling into the Details tab on a chart-element click.
- Detaching the current chart into an independent Modeless Dialog.
- Exporting the current chart as PNG or SVG.

The tab does not own run selection (the parent Result Widget does — see `05_Result_Widget/description.md`), the aggregated table (the Summary tab does — see `summary_tab.md`), or the per-result rows (the Details tab does — see `details_tab.md`). All numeric work is done by the chart-aggregation service on a background worker (`11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`); the tab only paints the finished structure.

## 2. Layout

```
+--------------------------------------------------------------------+
| [<] [3 / 12] [>]   [chart-kind dropdown v]        [Detach window]  |  <- primary toolbar
+--------------------------------------------------------------------+
| Filters: [Models v] [Status v] [Verdict v] [Category v] [Diff. v]  |  <- global filter chips
|          [Clear filters]                                           |
| <per-chart option controls>            Mode: GRADED  3 / 12  |  <- per-chart toolbar
+--------------------------------------------------------------------+
|                                                                    |
|                        <chart canvas>                             |
|                                                                    |
+--------------------------------------------------------------------+
| [Export PNG] [Export SVG]        [x] Save to app data folder       |  <- uniform footer
+--------------------------------------------------------------------+
```

The primary toolbar carries navigation and detach; the global filter chips and the per-chart option controls sit below it; the chart canvas fills the centre; the uniform footer carries the export controls. `05_Result_Widget/charts_gallery.html` is the visual source of truth for every chart kind and its filter-bar examples.

## 3. The twelve chart kinds

The chart kinds are the `ChartKind` enum (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` section 4.19). Each is computed by one named aggregator; the input fields, computation, and empty-state message of each are specified in `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md` section 7 and are not restated here.

| # | `ChartKind` | Chart type | Question it answers |
|---|---|---|---|
| 1 | `AVG_TTFT_PER_MODEL` | bar | How responsive is each model — time to the first token? |
| 2 | `AVG_TPS_PER_MODEL` | bar | Which model emits tokens fastest once generation starts? |
| 3 | `AVG_TIME_PER_MODEL` | bar | End to end, how long does each model take per task? |
| 4 | `SUCCESS_FAILED_INCOMPLETE_STACKED` | stacked bar | How many tasks did each model succeed, fail, or leave incomplete? |
| 5 | `PASS_RATE_BY_MODEL` | bar | Which model produces a passing answer most often? |
| 6 | `AVG_COSINE_BY_MODEL` | bar | What is each model's average quality, by the Cosine Score? |
| 7 | `VERDICT_COUNTS_STACKED` | stacked bar | How many of each verdict outcome did each model produce? |
| 8 | `TIME_VS_TOKENS_SCATTER` | scatter | Does duration grow with output size? |
| 9 | `HEATMAP_TASK_BY_MODEL` | grid | Which specific tasks does each model fail on? |
| 10 | `PER_CATEGORY_BAR` | grouped bar | Which task categories does each model excel at or struggle with? |
| 11 | `SPEED_VS_QUALITY_SCATTER` | scatter | Which models sit on the speed/quality Pareto frontier? |
| 12 | `TOKENS_PER_TASK_BOX` | box plot | How variable is each model's output length? |

Chart 6 aggregates `cosine_similarity` — the Cosine Score — because it is the only numeric quality metric; the judge produces no numeric score, so there is no judge-score chart. Charts 4 and 7 are stacked bars with an interactive legend: clicking a legend swatch hides that series and the chart re-scales.

## 4. Mode-availability matrix

The mode-visibility policy (`11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md`) decides which chart kinds a run offers, from `BenchmarkRun.run_mode`. A chart hidden by mode never appears in the chart-kind dropdown and is never reached by prev/next navigation. **Offered-but-empty charts (SPEC-119):** a chart that the mode offers but that currently has **no data** (e.g. the cosine charts when the cosine phase did not run) is still listed in the chart-kind dropdown — with a muted **"(no data)"** suffix — but **prev/next skips it** so repeated next-clicks never strand the user on a run of consecutive empty charts; the user can still jump to it directly from the dropdown (where it shows its empty-state message). If *every* offered chart is empty, prev/next is disabled and the tab shows its overall empty state.

| # | `ChartKind` | `SYNTHETIC` | `TASKS` | `GRADED` |
|---|---|:--:|:--:|:--:|
| 1 | `AVG_TTFT_PER_MODEL` | offered | offered | offered |
| 2 | `AVG_TPS_PER_MODEL` | offered | offered | offered |
| 3 | `AVG_TIME_PER_MODEL` | offered | offered | offered |
| 4 | `SUCCESS_FAILED_INCOMPLETE_STACKED` | offered | offered | offered |
| 5 | `PASS_RATE_BY_MODEL` | hidden | hidden | offered |
| 6 | `AVG_COSINE_BY_MODEL` | hidden | hidden | offered |
| 7 | `VERDICT_COUNTS_STACKED` | hidden | hidden | offered |
| 8 | `TIME_VS_TOKENS_SCATTER` | offered | offered | offered |
| 9 | `HEATMAP_TASK_BY_MODEL` | hidden | hidden | offered |
| 10 | `PER_CATEGORY_BAR` | hidden | hidden | offered |
| 11 | `SPEED_VS_QUALITY_SCATTER` | hidden | hidden | offered |
| 12 | `TOKENS_PER_TASK_BOX` | offered | offered | offered |

| Mode | Charts offered | Charts hidden |
|---|---|---|
| `SYNTHETIC` | 1, 2, 3, 4, 8, 12 — six | 5, 6, 7, 9, 10, 11 |
| `TASKS` | 1, 2, 3, 4, 8, 12 — six | 5, 6, 7, 9, 10, 11 |
| `GRADED` | all twelve | none |

The six grading charts (5, 6, 7, 9, 10, 11) require a verdict or a Cosine Score, neither of which a `SYNTHETIC` or `TASKS` run produces. The mode badge in the per-chart toolbar shows the visible-count fraction (`Mode: GRADED  3 / 12`).

### 4.1 Shared meta line

The per-chart toolbar's right-aligned meta strip is a single read-only summary line composed of dot-separated tokens — for example `Aggregation: mean · Mode: GRADED · 2 / 12` (the mockup's canonical form). Its tokens are:

- **`Aggregation: <stat>`** — the central statistic the active chart's aggregator is currently applying to each model group, echoing the active per-chart aggregation option (`mean` or `median` for chart 2; `mean` for the other averaged bar charts). It is informational: it surfaces, in the shared strip, the aggregation the bars represent (results are summarised as the mean — or median — per model group), so the user reading a bar height knows which central statistic it is. The token mirrors the chart's own aggregation control (§6) rather than being an independent setting.
- **`Mode: <run_mode>`** — the run's mode, as the mode badge above.
- **`N / M`** — the chart position within the mode-offered set, the same fraction the prev/next index label shows (§7).

The meta line is presentation only; changing the chart's aggregation option (§6) updates the `Aggregation:` token in step. A chart kind whose aggregator applies no central-statistic choice still reports the statistic its bars represent (`mean` for the fixed-mean bar charts).

## 5. Global filter chips

The global filter chips are multi-select dropdown chips, identical in domain to the Details tab's chips (see `details_tab.md` section 5). They narrow the working result set the active chart's aggregator sees; the aggregator re-computes on the narrowed set (`13_CHART_AGGREGATORS.md` section 6.2). The **Verdict chip is offered only in `GRADED`**, the only mode that produces verdicts; in `TASKS` and `SYNTHETIC` it is hidden because every result is ungraded.

| Chip | Domain | Default | Modes |
|---|---|---|---|
| Models | distinct `(provider_id, model_name)` of the run; each chip's user-visible label renders the SNAPSHOT `provider_name` from the underlying `BenchmarkResult` rows (DD-33) so historical fidelity is preserved across a later provider rename | all selected | all |
| Status | `ResultStatus` members present in the run | all selected | all |
| Verdict | `PASS`, `FAIL`, *ungraded* (`verdict is None`) | all selected | `GRADED` only |
| Category | distinct `BenchmarkTask.category` of the run | all selected | all |
| Difficulty | `Difficulty` members — easy / medium / hard | all selected | all |

**Clear filters** resets every chip to "all selected" and resets the per-chart options of the active chart to their defaults. It is enabled only while at least one chip or per-chart option is non-default. The global filter selection is part of the per-run, per-chart-kind view state (section 13): each chart kind remembers its own filter selection.

## 6. Per-chart options

Each chart kind offers its own option controls in the per-chart toolbar, below the global chips. The options for every chart kind are defined in `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md` section 7; this is the user-facing summary.

| # | `ChartKind` | Per-chart options |
|---|---|---|
| 1 | `AVG_TTFT_PER_MODEL` | unit selector (`ms` / `seconds`); outlier toggle (IQR x 1.5) |
| 2 | `AVG_TPS_PER_MODEL` | aggregation switch (`mean` / `median`) |
| 3 | `AVG_TIME_PER_MODEL` | outlier toggle (IQR x 1.5); Y-axis scale (`linear` / `log`) |
| 4 | `SUCCESS_FAILED_INCOMPLETE_STACKED` | interactive legend — hide a series segment |
| 5 | `PASS_RATE_BY_MODEL` | *Count ungraded as not-pass* toggle (default on) |
| 6 | `AVG_COSINE_BY_MODEL` | *Fold ungraded in as 0.0* toggle (default off) |
| 7 | `VERDICT_COUNTS_STACKED` | interactive legend — hide a verdict segment |
| 8 | `TIME_VS_TOKENS_SCATTER` | X-axis scale and Y-axis scale (`linear` / `log`) |
| 9 | `HEATMAP_TASK_BY_MODEL` | Tasks filter; *Cell value* switch (`verdict` / `cosine`); *Group rows by category* toggle |
| 10 | `PER_CATEGORY_BAR` | metric switch (*Pass rate* / *Avg Cosine Score* / *Avg time* / *Avg TPS*); Categories filter |
| 11 | `SPEED_VS_QUALITY_SCATTER` | Y-axis metric switch (*Pass rate* / *Avg Cosine Score*) |
| 12 | `TOKENS_PER_TASK_BOX` | *Show outliers* toggle |

The default state of every outlier toggle is the `ui.charts_outlier_default` setting. The hidden-series set of charts 4 and 7 persists per chart kind. Every per-chart option is part of the per-run, per-chart-kind view state (section 13).

### 6.1 Low-sample rendering contract

Every aggregated group the chart service returns carries its **sample size `n`** — the count of completed rows that contributed to the group's summary — and a `low_sample` flag, set when `n` is below `eval.min_sample_size` (default `5`); the aggregator computes both per `13_CHART_AGGREGATORS.md` section 6.5a. The Charts tab uses these to mark under-sampled groups so a 2-task model never looks as authoritative as a 100-task model:

- A per-model aggregate (charts 1, 2, 3, 5, 6, 11) and each per-`(category, model)` aggregate (chart 10) whose `low_sample` flag is set renders its bar (or its scatter point, for chart 11) with a **hatch / cross-hatch fill** instead of a solid fill, and carries an **`n=N` annotation** — `N` being the group's sample size — beside or above the element.
- A well-sampled group renders with the normal solid fill and no `n=N` annotation.
- The low-sample group is **still drawn** — the flag never drops the group from the chart; it only marks it low-confidence. The hatch and the `n=N` text use the `mute` tone so the under-sampling reads as a caveat, not an error.

This is the UI surface of the minimum-sample-size guard in `13_CHART_AGGREGATORS.md` section 6.5a; the threshold is the `eval.min_sample_size` setting (default `5`, see `08_Cross_Cutting/08-G_feature_flags.md`). The Run Analysis Service reads the same flag and excludes (or explicitly hedges) low-sample groups in its authoritative claims (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`). `05_Result_Widget/charts_gallery.html` shows a canonical hatched/`n=N` example bar.

## 7. Prev/next navigation and the chart-kind dropdown

The primary toolbar carries the navigation controls:

- The `<` and `>` arrow buttons step to the previous and next mode-offered chart; an `N / M` index label between them shows the position within the mode-offered set.
- The chart-kind dropdown lists every mode-offered chart kind by name and jumps directly to the chosen one.
- Navigation is mouse-only — the toolbar arrow buttons and the chart-kind dropdown are the sole controls; there are no keyboard bindings.

Navigation cycles only the mode-offered subset — six charts for `SYNTHETIC` and `TASKS`, twelve for `GRADED` — and does **not** wrap: `<` is disabled on the first chart and `>` on the last. The currently shown chart kind persists per run as `ui.charts_last_kind` style state in the per-run view-state store (section 13).

## 8. Chart-click drill-down

Clicking an element of a chart drills into the Details tab. The Result Widget switches to the Details tab and applies a filter that narrows the Details table to the rows behind the clicked element (see `details_tab.md` section 10):

| Clicked element | Drill-down filter applied to the Details tab |
|---|---|
| a per-model bar (charts 1, 2, 3, 5, 6) | the Models chip narrowed to that one `(provider_id, model_name)` |
| a stacked-bar segment (chart 4) | the Models chip narrowed to that model and the Status chip to that segment's status group |
| a stacked-bar segment (chart 7) | the Models chip narrowed to that model and the Verdict chip to that segment's verdict |
| a scatter point (chart 8) | the Tasks and Models chips narrowed to that point's single `result_id`, with that row pre-selected |
| a heatmap cell (chart 9) | the Tasks and Models chips narrowed to that cell's `(task_id, model)` pair |
| a grouped sub-bar (chart 10) | the Models and Category chips narrowed to that sub-bar's `(model, category)` pair |
| a scatter point (chart 11) | the Models chip narrowed to that point's one model |
| an outlier marker (chart 12) | the Tasks and Models chips narrowed to that marker's single `result_id`, with that row pre-selected |

A point or cell with no underlying completed result is not clickable. The scatter and box-plot point-to-`result_id` back-references are carried on the prepared `ChartData` by the aggregator (`13_CHART_AGGREGATORS.md` section 3).

## 9. Detach to window

The primary toolbar's `Detach window` button opens the current chart in its own Modeless Dialog so the user can place it alongside the main window or another detached chart.

- The detached window has its own primary toolbar (prev/next, chart-kind dropdown), its own global filter chips and per-chart options, and its own uniform footer with `Export PNG` and `Export SVG`.
- At open time the detached window's filter and option state is forked from the parent tab's current state; thereafter the two are independent — changing a filter in the detached window does not change the parent and is not written to the per-run view-state store.
- The save-destination toggle is the shared `ui.export_save_directly` value, identical to every other footer.
- More than one detached chart window may be open at once — for example two charts side by side, each on a different kind.
- A detached chart window subscribes to `_chart_data_changed` for the displayed run, owner-bound to itself; closing the window auto-cancels the subscription. It stays open through a workspace switch (EC-WS-1).
- Export and the view-only-during-run rule inside a detached window behave exactly as in the main footer (section 12).

## 10. Live update

While the selected run is the active run, the tab subscribes to `_chart_data_changed` on the event bus and re-requests the active chart's dataset on a **250 ms debounce** (EC-PERF-3). The chart-aggregation service re-computes from the refreshed cached result snapshot; a re-computation supersedes any in-flight one for the same chart kind. Across a repaint the tab preserves the active chart kind, the global filter selection, the per-chart options, and any hidden legend series. A run that is not the active run never live-updates; its Charts tab is a static view.

## 11. Empty states

When the active chart has no usable data, the chart canvas shows an explicit, kind-specific message in `mute` tone — never blank axes and never an empty grid. The message is the `empty_state_message` carried on the prepared structure by the aggregator; the exact text per chart kind is in `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md` section 7.

| Trigger | Rendering |
|---|---|
| No run selected | the tab shows `Select a run to view its charts.` |
| No chart in the mode-offered set has data | the canvas shows `Charts require at least one completed task.` |
| The active chart has no usable data — every relevant field is null, or the filters exclude every row | the canvas shows the chart's own `empty_state_message`, for example `No time-to-first-token data — provider streaming is required for this metric.` |
| A grading chart requested in a non-`GRADED` mode | defence in depth — the canvas shows `This chart is available only for graded runs.`; the chooser already prevents this |

When a chart shows its empty state, the prev/next controls and the chart-kind dropdown stay enabled so the user can move to a chart that does have data. The export buttons stay enabled when no run is in progress; exporting an empty chart produces an image of the empty-state message.

## 12. Export

The uniform footer carries `Export PNG` and `Export SVG`. Both export the **single chart currently shown** — including its title, axes, legend, and labels — exactly as the canvas renders it, with the active global filters and per-chart options applied.

- The chart is rendered off-screen at a fixed `2400 x 1600` resolution; the background and palette are taken from the active dark or light theme, not the OS palette (EC-RES-4).
- The filename is `<effective_run_name>_Chart_<chart-slug>.<png|svg>`, where the slug is the `ChartKind` value; the full filename and collision rules are in `10_Domain_and_Data/05_EXPORT_FORMATS.md`.
- A detached chart window's export produces the identical image for whichever chart it displays.

Both buttons are **disabled while any run is in a non-terminal state** (see `description.md` section 7), regardless of which run is displayed; while disabled they carry the tooltip "Disabled — a benchmark is in progress." The save behaviour — direct write to `<app_data>/exports/` versus a save picker — follows the shared `ui.export_save_directly` rule.

## 13. Persistence

The Charts tab's view state is persisted **per run**, keyed by `run_id`, by the result-table persistence model in `08_Cross_Cutting/08-G_feature_flags.md` section 10. The per-run state carries, **per chart kind**:

- the global filter-chip selection,
- the per-chart options,
- the hidden legend series (charts 4 and 7);

and, once per run:

- the last-opened chart kind,
- the outlier-exclusion toggle state seeded from `ui.charts_outlier_default`.

- A run opened for the first time uses the built-in default Charts view state for the run's mode — all filters selected, the default per-chart options, no hidden series, and the first mode-offered chart as the last-opened kind.
- A previously-opened run is restored to the exact Charts view state the user last left it in.

The view state is stored against the run; no view state crosses between runs. A detached chart window's forked state is session state and is not persisted (section 9).

## 14. Event-bus integration

All subscriptions are owner-bound to the tab; the bus auto-cancels them on destruction. A detached chart window subscribes with itself as owner.

| Direction | Signal | Handler effect |
|---|---|---|
| Subscribes | `_chart_data_changed` (for the displayed run) | re-request the active chart's dataset; debounced repaint (section 10) |
| Subscribes | `_run_id_changed` (from the parent Result Widget) | reload the run, re-apply the mode chart policy, restore the run's Charts view state |
| Subscribes | `_run_started`, `_run_finished`, `_run_stopped`, `_run_failed` | enable or disable the export buttons as runs enter or leave a non-terminal state |

The tab emits no run-mutating event — it is a read-only view. A chart-click drill-down (section 8) is delivered to the Details tab as an in-process request through the parent controller, not as an event-bus signal.

## 15. Edge cases

| ID | Concern | Handling |
|---|---|---|
| EC-RUN-3 | the selected run failed | each mode-offered chart renders its partial data; a chart with no data shows its empty state |
| EC-RES-1 | a run with zero completed results | every chart shows its kind-specific empty state; the export buttons stay enabled once no run is in progress |
| EC-RES-2 | the same model name served by two providers | the composite `(provider_id, model_name)` keeps the two model series and bars distinct |
| EC-RES-4 | a chart exported under the dark theme | the PNG and SVG background and palette match the active theme, not the OS palette |
| EC-RES-5 | a direct-write export fails | an error modal reports the failure; the chart and its view state are unchanged |
| EC-RES-6 | a run name that sanitises to an empty string | the export filename falls back to `Run_<run_id>_Chart_<chart-slug>.<png|svg>` |
| EC-WS-1 | a workspace switch while a detached chart window is open | the detached window stays open independently of the workspace switch |
| EC-PERF-3 | a high rate of task completions during a live run | the 250 ms debounce coalesces the repaints; the active chart kind and view state are preserved |
| CH-EC-1 | a chart with no data while other charts have data | the empty chart shows its message; prev/next stays enabled so the user can move to a populated chart |

## 16. Function inventory

| Function | Primitive | Enabled when |
|---|---|---|
| Previous / next chart | buttons and keys | within the mode-offered set; does not wrap |
| Pick a chart kind | dropdown | always; among the mode-offered set |
| Filter — Models / Status / Verdict / Category / Difficulty | multi-select filter chip | always; persists per run, per chart kind |
| Clear filters | button | a chip or a per-chart option is non-default |
| Change a per-chart option | varies per chart — toggle, switch, sub-filter | per the active chart kind; persists per run, per chart kind |
| Hide / show a legend series | click a legend swatch | charts 4 and 7 only; persists per run, per chart kind |
| Drill into the Details tab | click a chart element | always for an element with an underlying result |
| Detach the chart into a window | button | always — a detached chart is read-only-safe during a run |
| Export PNG | button in the footer | no run is in a non-terminal state |
| Export SVG | button in the footer | no run is in a non-terminal state |
| Toggle save-directly / Open Exports Folder | toggle plus button in the footer | always; shared across every Result Widget tab |
