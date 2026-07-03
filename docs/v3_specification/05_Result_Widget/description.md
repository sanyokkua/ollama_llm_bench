# Result Widget — Description

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `state_machine.md`, `flow_diagram.md`, `implementation_structure.md`, `mockup.html`; `tabs/summary_tab.md`; `tabs/details_tab.md`; `tabs/charts_tab.md`; `tabs/run_analysis_tab.md`; `07_Common_Dialogs/generate_analysis_dialog.md`; `01_Main_Window/description.md`; `03_Resume_Benchmark_Widget/description.md`; `04_Progress_Widget/description.md`; `08_Cross_Cutting/08-E_interfaces_contracts.md`; `08_Cross_Cutting/08-G_feature_flags.md`; `08_Cross_Cutting/08-H_app_modes.md`; `08_Cross_Cutting/08-I_edge_cases.md`; `08_Cross_Cutting/08-J_event_bus_catalog.md`; `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`; `10_Domain_and_Data/05_EXPORT_FORMATS.md`; `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`

The Result Widget is the right panel of the Benchmark workspace and the view-only display of one selected benchmark run. It renders a header with a single run-selector dropdown, a four-tab strip — Summary, Details, Charts, Run Analysis — and a uniform footer carrying the export buttons appropriate to the active tab plus a shared save-destination control. The widget updates live while a run is in progress and is otherwise view-only; it never starts, renames, deletes, or resumes a run. While any run is in a non-terminal state every destructive or generative action — every file export and the run-analysis regeneration — is disabled across all four tabs and all detached windows.

---

## Table of Contents

1. Role and ownership
2. Layout
3. Header — run-selector dropdown
4. Tab strip and the four tabs
5. Footer — uniform contract
6. Run-selection logic
7. View-only-during-run rule
8. Detached windows
9. Per-run table and chart view state
10. Empty states per tab
11. Persistence
12. Event-bus integration
13. Service dependencies
14. Edge cases
15. Function inventory

---

## 1. Role and ownership

The Result Widget owns the presentation of one benchmark run at a time across four tabs. It is responsible for:

- Holding the run-selector dropdown and the currently selected run id.
- Hosting the four tab views and giving them a shared parent controller for run selection and the per-run filter and view-state store.
- Rendering the uniform footer: the per-tab export buttons, the shared save-destination toggle, and the `Open Exports Folder` action.
- Updating the displayed run live while it is the active run, and rendering any past run's persisted data on demand.
- Disabling every export and regeneration action while any run is non-terminal.

The widget is **not** responsible for:

- Starting a run. The New Benchmark Widget owns run creation; see `02_New_Benchmark_Widget/description.md`.
- Renaming, deleting, retrying, or cloning a run. Those actions live in the Resume Benchmark Widget context menu; see `03_Resume_Benchmark_Widget/description.md`. Renaming the active run lives on the Progress Widget header; see `04_Progress_Widget/description.md`.
- The internal behaviour of the four tabs. Each tab's columns, filters, charts, and drill-downs are specified in its own file under `tabs/` and are cross-referenced, not restated, here.
- Driving the pipeline or aggregating data. The benchmark pipeline and the chart and table aggregators run on background workers and report through the typed event bus.

The widget never blocks the UI thread. Every live update arrives through an event-bus signal delivered on the UI thread.

## 2. Layout

The widget is a single vertical column: header, tab strip, tab body, footer. The mockup `mockup.html` is the visual source of truth.

```
+------------------------------------------------------------+
| Run dropdown                                          v    |
+------------------------------------------------------------+
| Summary | Details | Charts | Run Analysis  <- tab strip  |
+------------------------------------------------------------+
| (per-tab toolbar — content-specific, owned by the tab)     |
| Tab body                                                   |
|                                                            |
+------------------------------------------------------------+
| [ per-tab export buttons ]                                 |
|                  [x] Save to app data folder      |
|                            [Open Exports Folder]               |
+------------------------------------------------------------+
```

Layout rules:

- The header is one row holding only the run-selector dropdown.
- The tab strip is one row of four tabs; the active tab is marked by the primary underline.
- The tab body fills the remaining vertical space and grows with the window. Each tab owns its own optional toolbar inside the body.
- The footer is one fixed-height row, identical in layout on every tab; only the export-button cluster changes.
- All spacing, radius, colour, and typography tokens come from `08_Cross_Cutting/08-D_color_palette_and_typography.md`. The widget embeds no literal hex values.

## 3. Header — run-selector dropdown

The header holds a single Dropdown and nothing else — no buttons, no menus.

- The Dropdown is populated with every run from the Data Store, newest first. Each item shows the run's effective name.
- Selecting an item sets the selected run id, refreshes all four tab caches, and announces the change (see §6).
- The Dropdown auto-selects a newly started run on its first appearance, then respects a later manual selection (see §6).
- The Dropdown stays enabled at all times, including while a run is in progress, so the user may inspect any past run or observe the active run live.

To act on the selected run — rename, delete, retry, clone — the user switches to the Resume Benchmark tab and uses that widget's row context menu. The Result Widget exposes no run-management action.

## 4. Tab strip and the four tabs

The tab strip holds four tabs. Each tab is a separate sub-module with its own toolbar and body; this widget hosts them and gives them a shared parent controller (see `implementation_structure.md`).

| Tab | Content kind | Specification file |
|---|---|---|
| Summary | Aggregated per-`(provider, model)` statistics table | `tabs/summary_tab.md` |
| Details | One row per benchmark result; filterable; drill-down panel | `tabs/details_tab.md` |
| Charts | One chart at a time from the mode-aware chart set; prev/next navigation | `tabs/charts_tab.md` |
| Run Analysis | The consolidated run-level narrative analysis text | `tabs/run_analysis_tab.md` |

The default selected tab is Summary. The selected tab is persisted in `ui.last_result_tab` (see `08_Cross_Cutting/08-G_feature_flags.md` §7) and restored when the widget next opens. Switching tabs is always allowed, including while a run is in progress.

The consolidated run-level narrative is a single field — `BenchmarkRun.run_analysis` — produced for every run mode. The Run Analysis tab presents that one field; there is no separate performance-analysis surface. See `tabs/run_analysis_tab.md`.

**Status badge for `FAILED_JUDGE_TIMEOUT` (DD-34).** The Summary and Details tabs render the new terminal status `FAILED_JUDGE_TIMEOUT` with the same error-tone status badge used for the other `FAILED_*` statuses (`tabs/summary_tab.md` §4.2 / 4.3, `tabs/details_tab.md` §11). The Result Widget exposes no per-row Retry action of its own; the user reaches the Retry Selection dialog (`07_Common_Dialogs/retry_selection_dialog.md`) from the Resume Benchmark widget's run-row context menu. That dialog **treats `FAILED_JUDGE_TIMEOUT` identically to the other retryable terminal states** (`FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `ERRORED`) — pre-selected on open, available under the `Only failed` filter, and on confirmation reset to `PENDING` so the row re-runs end-to-end (re-inference + re-grade — the original attempt's inference text and timings are NOT preserved).

## 5. Footer — uniform contract

Every tab shows the same footer row layout so the user's mental model does not shift when switching tabs. The footer has a left cluster of export buttons and a right cluster of the shared save-destination control.

```
+----------------------------------------------------------------+
| [ per-tab export buttons ]                                     |
|                  [x] Save to app data folder          |
|                            [Open Exports Folder]                   |
+----------------------------------------------------------------+
```

### 5.1 Per-tab export-button cluster

The left cluster's buttons depend on the **kind of content** in the active tab, never on the tab name. The rule is one export button per supported file format for the data shown. The full format contract is in `10_Domain_and_Data/05_EXPORT_FORMATS.md`.

| Active tab | Content kind | Footer export buttons |
|---|---|---|
| Summary | table | `Export CSV`, `Export Markdown` |
| Details | table | `Export CSV`, `Export Markdown` |
| Charts | image | `Export PNG`, `Export SVG` |
| Run Analysis | text | `Export Markdown` |

Actions that are not file exports — Copy to clipboard, Regenerate analysis, Clear filters, Detach window, prev/next chart — live in their tab's own toolbar, never in the footer. The footer is reserved for "save to disk".

### 5.2 Save-destination toggle and Open Exports Folder

The right cluster is identical on every tab: a Toggle labelled `Save to app data folder`, bound to the `ui.export_save_directly` setting (see `08_Cross_Cutting/08-G_feature_flags.md` §7), and an `Open Exports Folder` Button shown only when the toggle is on. The toggle value is shared — flipping it on any tab or detached window updates every other footer through the `_app_settings_changed` event.

When the toggle is **on**:

- The `Open Exports Folder` Button is visible immediately to the right of the toggle.
- Every Export click writes directly to the Exports Folder `<app-data>/exports/` using the canonical filename and the numeric-suffix collision rule from `10_Domain_and_Data/05_EXPORT_FORMATS.md` §2. No picker appears. A confirmation toast names the written path.
- `Open Exports Folder` reveals the Exports Folder through the OS Adapter's `open_in_file_manager` call.

When the toggle is **off**:

- The `Open Exports Folder` Button is hidden.
- Every Export click opens a native Save Picker defaulted to the user's Desktop with the canonical filename pre-filled, through the OS Adapter's `open_save_picker` call.

**Export feedback wording.** On every successful export — direct write or picker-chosen path, on every tab and in every detached window — the Notification Service shows a confirmation toast reading **`Saved to <path>`**, where `<path>` is the absolute path of the written file (`flow_diagram.md` §C/§D). On a failed write the temp-file-then-rename leaves no partial file and the Notification Service raises a blocking **error modal** reporting the failure (EC-RES-5; `flow_diagram.md` §C); the table or chart and its view state are unchanged. A picker the user cancels writes nothing and shows no toast.

### 5.3 Save-destination setting

```text
key:     ui.export_save_directly
type:    bool
default: false
layer:   user-saved (not per-run-overridable)
```

The key is registered in `08_Cross_Cutting/08-G_feature_flags.md` §7. It is a UI preference, not a run input, so it is never part of a run snapshot.

## 6. Run-selection logic

When the user picks a different run in the Dropdown:

1. The parent controller sets the selected run id.
2. It emits `_run_id_changed` so the Progress and Resume Benchmark widgets follow the same selection.
3. It refreshes the four tab caches from the Data Store and the aggregators.
4. The active tab repaints; the other three repaint lazily when next shown.

During an active benchmark:

- The new run is added to the Dropdown when `_run_list_changed` fires.
- The selection auto-jumps to the active run only on the run's **first appearance**. The parent controller holds a "user-locked selection" flag: once the user manually picks a different run, later run starts do not move the selection. Selecting the active run again clears the flag.

The Dropdown also follows an external selection: when another widget changes the selected run, the `_run_id_changed` event updates the Dropdown without re-emitting the event.

## 7. View-only-during-run rule

The Result Widget is view-only at all times — it never mutates run data. While **any** run is in a non-terminal state — `INCOMPLETE` with the pipeline actively executing, or paused — an additional restriction applies: every action that writes a file or generates new data is disabled, regardless of which run the user is viewing. The Result Widget reads this "any run non-terminal" state from the **shared run-activity gateway** and the `_run_*` lifecycle events (D-R-05), the same single source the Main Window and Progress widgets use — it does not independently re-derive run-active state, so the panels cannot disagree.

| Action | Allowed while a run is non-terminal |
|---|---|
| Pick a run in the Dropdown | yes — inspection and live observation are read-only |
| Switch tab | yes |
| Filter, sort, show/hide columns, reorder columns | yes — per-run view-state changes are not file writes |
| Detach a window (Summary, Details, Charts) | yes — detached windows are read-only views |
| Copy analysis text to clipboard | yes — no side effect |
| Prev/next chart navigation | yes |
| Export CSV / Markdown / PNG / SVG (every tab, every detached window) | no — disabled |
| Generate / Regenerate run analysis (opens `07_Common_Dialogs/generate_analysis_dialog.md`) | no — disabled by the view-only-during-run rule AND by the single-inference gate when another activity holds it (`08_Cross_Cutting/08-H_app_modes.md` §10) |

Every disabled export carries the tooltip **"Disabled — a benchmark is in progress."** The Generate / Regenerate run-analysis button's tooltip names the specific reason (run in progress, another inference activity in flight, or no completed results) per `05_Result_Widget/tabs/run_analysis_tab.md` §7. When the run reaches a terminal state — `_run_finished`, `_run_stopped`, or `_run_failed` — and the single-inference gate is `IDLE`, all actions re-enable atomically. The full composite blocked-states contract is in `08_Cross_Cutting/08-H_app_modes.md` §10.

## 8. Detached windows

Each tab whose content is a primary payload exposes a `Detach window` Button in its own toolbar. Detaching opens the content in a Modeless Dialog that the user may position alongside the main window for side-by-side comparison.

| Tab | Detach available | Detached content |
|---|---|---|
| Summary | yes | The Summary table with its toolbar and the uniform footer |
| Details | yes | The Details table, its drill-down panel, its toolbar, and the uniform footer |
| Charts | yes | The currently selected chart with its own prev/next navigation, chart-kind dropdown, filters, and the uniform footer |
| Run Analysis | no | A single text body; Copy and Regenerate in the toolbar already cover the use case |

Detached behaviour:

- A detached window replicates the uniform footer, so exports behave identically; the save-destination toggle is the same shared `ui.export_save_directly` value.
- A detached window subscribes to the data-changed events for its content, owner-bound to itself; closing the window auto-cancels the subscription.
- More than one detached window may be open at once — for example, two charts side by side.
- A detached window stays open independently when the user switches workspace (EC-WS-1); it is not destroyed by the workspace switch.
- Export and Regenerate inside a detached window obey the §7 view-only-during-run rule exactly as the main footer does.

## 9. Per-run table and chart view state

The Summary and Details tables and the Charts tab each carry view state — the filter-chip selection, the column visibility set and column order for tables, and the per-chart-kind filters, hidden legend series, last-opened chart kind, and outlier-exclusion toggle for charts. This state is persisted **per run**, not as one global preference, by the rule in `08_Cross_Cutting/08-G_feature_flags.md` §10.

| Situation | View state applied |
|---|---|
| A run opened for the first time — a newly created run, or any run never previously selected here | The built-in default view state for that table or tab and the run's mode |
| A previously opened run reopened | The last-saved view state for that run — the filters, visibility, order, and chart selection the user left it in |

When the user changes a filter, hides or shows a column, reorders columns, or changes a chart selection, the new state is written back against that run's id. A run thus remembers how the user last looked at it. The parent controller owns the per-run view-state store that the four tabs share; each tab reads and writes its own slice.

## 10. Empty states per tab

When the selected run has no data for a tab, the tab body shows a centred empty-state message in `mute` tone instead of an empty table or canvas.

| Tab | Empty-state message | Trigger |
|---|---|---|
| Summary | "No completed results yet." | The run has zero results in a terminal status |
| Details | "Detailed results will appear here once tasks complete." | The run has zero results in a terminal status |
| Charts | "Charts require at least one completed task." | No chart in the mode-aware set has data |
| Run Analysis | "Run-level analysis is generated when the benchmark finishes." | `BenchmarkRun.run_analysis` is absent |

A run with zero completed results (EC-RES-1) shows the Summary and Details empty states and the Charts empty state; the footer export buttons are **disabled with a tooltip** ("No completed results to export yet") because there is nothing to export (SPEC-082). No header-only file is written and no "Saved" toast is shown for an empty run — the disabled control plus tooltip is the feedback, consistent with the applicability-based hidden-vs-disabled rule (`00_Foundation/05_CONSTRAINTS.md`). Export enables as soon as at least one result is completed.

## 11. Persistence

| State | Stored where | When written |
|---|---|---|
| Selected tab | `ui.last_result_tab` | on tab switch |
| Save-destination toggle | `ui.export_save_directly` | on toggle |
| Per-run table view state — filters, column visibility, column order | per-run view-state store keyed by run id | on any filter / column change |
| Per-run chart view state — chart-kind filters, hidden series, last chart, outlier toggle | per-run view-state store keyed by run id | on any chart-view change |
| Selected run id | run-selection store | on Dropdown change or external `_run_id_changed` |

The widget holds no run data of its own across restarts. On reopen it rebuilds every tab from the Data Store and the aggregators, and restores the per-run view state for whichever run it selects.

## 12. Event-bus integration

All subscriptions are owner-bound to the widget or its controllers; the bus auto-cancels them on destruction (see `08_Cross_Cutting/08-J_event_bus_catalog.md` §2). Detached windows subscribe with themselves as owner.

Subscribed signals:

| Signal | Handler effect |
|---|---|
| `_run_id_changed` | switch the active selection; refresh all four tab caches; restore per-run view state |
| `_run_list_changed` | repopulate the run-selector dropdown |
| `_run_renamed` | update the affected dropdown item's text |
| `_run_started` | add the active run to the dropdown; auto-select it unless the selection is user-locked; enter the live-update state |
| `_run_finished`, `_run_stopped`, `_run_failed` | leave the live-update state; re-enable every export and the Regenerate action atomically |
| `_summary_data_changed` | refresh the Summary tab cache and repaint when it is the active tab |
| `_detailed_data_changed` | refresh the Details tab cache and repaint when it is the active tab |
| `_chart_data_changed` | refresh the Charts tab cache and repaint the current chart; also delivered to each detached chart window |
| `_run_analysis_received` | cache and repaint the Run Analysis tab |
| `_app_settings_changed` | re-read `ui.export_save_directly`; show or hide the `Open Exports Folder` Button on every footer |

Emitted signals: the widget emits `_run_id_changed` when the user changes the Dropdown selection. It emits no other event directly; export and regeneration actions call services that emit on its behalf — Regenerate calls the run-analysis service, which emits `_run_analysis_received`.

The table-data and chart-data events are debounced at 250 ms (see `08_Cross_Cutting/08-J_event_bus_catalog.md` §4), so a fast-completing run repaints the tabs at a perceptible, bounded rate (EC-PERF-3).

## 13. Service dependencies

The widget factory receives these dependencies (see `implementation_structure.md`). Full method contracts are in `08_Cross_Cutting/08-E_interfaces_contracts.md`.

- **Event Bus** — every live update and the run-selection announcement.
- **Data Store** — read run headers for the dropdown, and run results for the tab caches.
- **Settings Service** — read and persist `ui.last_result_tab` and `ui.export_save_directly`; read `ui.score_display_format` for table number formatting.
- **Run-analysis service** — regenerate the consolidated run-level analysis (see `11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`).
- **Chart aggregators** — compute each chart's dataset (see `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`).
- **Table serialisation service** — produce the Summary and Details CSV and Markdown payloads (see `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`).
- **OS Adapter** — `open_save_picker` for the indirect-save flow and `open_in_file_manager` for `Open Exports Folder`.
- **Notification Service** — confirmation toasts on a successful export and an error modal on a failed write.
- **Export-filename helper** — compose the canonical export filename per `10_Domain_and_Data/05_EXPORT_FORMATS.md` §2.

## 14. Edge cases

Referenced by ID from `08_Cross_Cutting/08-I_edge_cases.md`:

- **EC-RUN-3** — The selected run failed. Each tab renders the partial data cleanly; the Charts tab handles a chart with no data with its empty state; the Run Analysis tab shows whatever analysis text exists or its empty state.
- **EC-RES-1** — A run with zero completed results. Each tab shows its empty state; the export buttons are disabled with a "nothing to export" tooltip and write no file (SPEC-082).
- **EC-RES-2** — The same model name across two providers. Summary rows are split by the composite `(provider, model)` key, so the two targets never merge.
- **EC-RES-3** — Very long run-analysis text. The Run Analysis tab renders the narrative **in full with no length cap and no truncation**, inside a scrollable view (matching `tabs/run_analysis_tab.md`); the Markdown export carries the identical full text.
- **EC-RES-4** — A chart exported under the dark theme. The PNG and SVG background and palette match the active theme.
- **EC-RES-5** — Save-directly is on but the write fails. An error modal is shown; the toggle stays on; the atomic temp-file-then-rename leaves no partial file.
- **EC-RES-6** — A run name that sanitises to an empty string. The export filename falls back to `Run_<run_id>`.
- **EC-WS-1** — Workspace switch while a detached chart window is open. The detached window stays open independently of the workspace switch.
- **EC-PERF-3** — High-rate task completion. The table-data and chart-data events are debounced at 250 ms; the tabs repaint at a bounded rate.

## 15. Function inventory

A flat list of every callable behaviour, for tester traceability.

| Function | Primitive | Gated by |
|---|---|---|
| Pick a run | Dropdown | always |
| Switch tab | Tab Strip | always; persists to `ui.last_result_tab` |
| Toggle save-directly destination | Toggle | always; persists to `ui.export_save_directly` |
| Open the Exports Folder | Button | `ui.export_save_directly` is true |
| Export the Summary table — CSV or Markdown | Button | Summary tab active and no run in a non-terminal state |
| Export the Details table — CSV or Markdown | Button | Details tab active and no run in a non-terminal state |
| Export the current chart — PNG or SVG | Button | Charts tab active and no run in a non-terminal state |
| Export the run analysis — Markdown | Button | Run Analysis tab active and no run in a non-terminal state |
| Detach a window | Button | Summary, Details, or Charts tab active; allowed during a run |
| Regenerate the run analysis | Button | Run Analysis tab active and no run in a non-terminal state |
| Copy the analysis text | Button | Run Analysis tab active; analysis text present; allowed during a run |
| Prev / next chart | Buttons | Charts tab active; cycles within the mode-aware chart set |
| Follow an external run selection | implicit on `_run_id_changed` | always |

Each tab's own function inventory is in its file under `tabs/`.
