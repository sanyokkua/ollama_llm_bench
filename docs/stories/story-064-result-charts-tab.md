---
id: STORY-064
title: Build the Result widget Charts tab — mode-aware chart set, navigation, filters, drill-down, detach, and image export
status: ready
spec_clauses:
  - 05_Result_Widget/tabs/charts_tab.md#3-the-twelve-chart-kinds
  - 05_Result_Widget/tabs/charts_tab.md#4-mode-availability-matrix
  - 05_Result_Widget/tabs/charts_tab.md#7-prevnext-navigation-and-the-chart-kind-dropdown
  - 05_Result_Widget/tabs/charts_tab.md#8-chart-click-drill-down
  - 05_Result_Widget/tabs/charts_tab.md#11-empty-states
  - 05_Result_Widget/tabs/charts_tab.md#12-export
  - 05_Result_Widget/implementation_structure.md#53-chartstabcontroller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/results/
acceptance_criteria:
  - STORY-064-AC-1
  - STORY-064-AC-2
  - STORY-064-AC-3
  - STORY-064-AC-4
  - STORY-064-AC-5
  - STORY-064-AC-6
edge_cases:
  - EC-RES-4
depends_on:
  - STORY-049
  - STORY-061
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-064 — Build the Result widget Charts tab — mode-aware chart set, navigation, filters, drill-down, detach, and image export

## Goal

Deliver the Charts tab sub-feature package under `ui/results/_internal/charts_tab/`: the
one-chart-at-a-time canvas that paints the prepared `ChartData`/`HeatmapData` requested from the
gateway, the mode-aware chart set with non-wrapping prev/next navigation that skips
offered-but-empty charts, the global filter chips and per-chart options, the low-sample
hatch/`n=N` rendering, the chart-click drill-down request into the Details tab, the
detach-to-window, and the theme-aware PNG/SVG export.

## In scope

- `_internal/charts_tab/controller.py` (`ChartsTabController`): subscribes `_chart_data_changed`;
  derives the mode-offered chart list, requests the active chart's prepared data via
  `ResultGateway.chart_data`, computes the empty-state structure, and reads/writes its per-run,
  per-chart-kind view-state slice.
- `_internal/charts_tab/view.py` (`ChartsTabView`): the chart canvas, the prev/next + chart-kind
  dropdown toolbar, the global filter chips, the per-chart option controls, the interactive
  legend (charts 4 and 7), and the low-sample hatch/`n=N` rendering.
- `_internal/charts_tab/detached_window.py` (`DetachedChartWindow`): a modeless window forking
  the parent's filter/option state at open, with its own footer, subscribing to
  `_chart_data_changed` owner-bound to itself.
- The chart-click drill-down request routed to the Details tab through the parent controller, and
  the theme-aware off-screen PNG/SVG export via `ResultGateway.serialize_table`/the export helper.

## Out of scope

- The Result shell and footer — owned by STORY-061.
- The chart-aggregation service (`ChartAggregator`) that computes the datasets — consumed behind
  the gateway; the tab paints the finished structure and performs no aggregation arithmetic.
- The Details tab that receives the drill-down — owned by STORY-063.
- Wiring the concrete `ResultGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `05_Result_Widget/tabs/charts_tab.md#3-the-twelve-chart-kinds` — the `ChartKind` set and the
  Cosine-Score-as-only-numeric-quality rule.
- `05_Result_Widget/tabs/charts_tab.md#4-mode-availability-matrix` — the per-mode offered chart
  set and the offered-but-empty `(no data)` handling.
- `05_Result_Widget/tabs/charts_tab.md#7-prevnext-navigation-and-the-chart-kind-dropdown` — the
  non-wrapping navigation over the mode-offered subset and the skip-empty rule.
- `05_Result_Widget/tabs/charts_tab.md#8-chart-click-drill-down` — the per-element drill-down
  filter mapping into the Details tab.
- `05_Result_Widget/tabs/charts_tab.md#11-empty-states` — the kind-specific empty-state rendering.
- `05_Result_Widget/tabs/charts_tab.md#12-export` — the off-screen `2400 x 1600` render with the
  active theme's palette, disabled while any run is non-terminal.
- `05_Result_Widget/implementation_structure.md#53-chartstabcontroller` — the sub-controller's
  concern, subscription, derivation, and per-chart-kind view-state slice.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — `chart_data(run_id, chart_kind)`.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — the
  exported image uses the active theme's tokens, not the OS palette.

## Design constraints

- The sub-controller depends only on `ResultGateway`, `EventBus`, and the shared
  `PerRunViewStateStore` (D-R-06); it performs no aggregation arithmetic.
- Navigation cycles only the mode-offered subset, does not wrap, and prev/next skips
  offered-but-empty charts.
- A detached window forks the parent's state at open and is thereafter independent; it stays open
  through a workspace switch.
- The exported image renders from the active dark/light theme palette (EC-RES-4).
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-064-AC-1

For each run mode, the mode-offered chart set matches the mode-availability matrix:

| Mode      | Charts offered          |
| --------- | ----------------------- |
| SYNTHETIC | 1, 2, 3, 4, 8, 12 (six) |
| TASKS     | 1, 2, 3, 4, 8, 12 (six) |
| GRADED    | all twelve              |

### STORY-064-AC-2

Given the active chart is the first mode-offered chart, when the tab renders navigation, then
the previous button is disabled; and given it is the last, then the next button is disabled —
navigation never wraps.

### STORY-064-AC-3

Given an offered-but-empty chart lies between two populated charts, when the user clicks next
repeatedly, then navigation skips the empty chart while it remains reachable directly from the
chart-kind dropdown.

### STORY-064-AC-4

Given the user clicks a per-model bar element, when the tab handles the click, then it routes a
drill-down request through the parent controller narrowing the Details tab to that single
`(provider_id, model_name)`.

### STORY-064-AC-5

Given the active chart, when the user exports PNG or SVG, then the image is rendered from the
active theme's palette (not the OS palette) at the fixed off-screen resolution.

### STORY-064-AC-6

Given the user detaches the current chart, when the detached window opens, then it forks the
parent tab's filter and option state at open time and thereafter changing a filter in the
detached window does not change the parent and is not written to the per-run view-state store.

## Test plan

- STORY-064-AC-1 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/results/tests/test_charts_tab.py`,
  `test_offered_chart_set_per_mode`. Wrapped in `structlog.testing.capture_logs()`; asserts no
  captured entry's `log_level` is in `{"error", "critical"}`.
- STORY-064-AC-2 — unit (`pytest-qt`), same file, `test_navigation_does_not_wrap`.
- STORY-064-AC-3 — unit (`pytest-qt`), same file, `test_navigation_skips_empty_charts`.
- STORY-064-AC-4 — unit (`pytest-qt`), same file, `test_bar_click_routes_drilldown`.
- STORY-064-AC-5 — unit (`pytest-qt`), same file, `test_export_uses_active_theme_palette`.
  Covers EC-RES-4.
- STORY-064-AC-6 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_detached_chart_window.py`,
  `test_detached_window_forks_state_independently`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-064.
- [ ] EC-RES-4 has a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Charts tab's
  populated, empty, and detached states.
- [ ] An architecture test confirms the sub-controller depends only on `ResultGateway` and the
  shared view-state store, performs no aggregation arithmetic, and that the module references
  no `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/results/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-064.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
