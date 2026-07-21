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
  - adapters/file_system_actions/
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

## Notes

- **`modules:` amendment.** The front matter was amended before implementation to add
  `adapters/file_system_actions/` alongside `ui/results/`. The Charts tab's PNG export
  produces binary content, but the existing `FileSystemActions.write_export_file`/
  `.write_text_file` (STORY-061) accept `content: str` only. Two purely-additive methods —
  `write_export_file_bytes` (the exports-folder direct-write counterpart of
  `write_export_file`, identical numeric-suffix collision rule) and `write_binary_file` (the
  Save-Picker counterpart of `write_text_file`) — were added to the `FileSystemActions`
  Protocol and its concrete `QtFileSystemActions` implementation, duplicating the existing
  atomic temp-file-then-rename structure with only the open mode/payload type changed. This
  is a genuine cross-module change, hence the front-matter amendment. Every existing
  `FileSystemActions` fake in the codebase (`ui/results/tests/conftest.py`'s
  `FakeFileSystemActions`, plus three independent local `_FakeFileSystemActions` doubles in
  `ui/resume_benchmark/tests/`) was updated to keep satisfying the widened Protocol —
  `just typecheck` on the whole `src` tree is the enforcement mechanism, since Python's
  structural typing means a Protocol extension breaks every implementer, not just the ones
  this story otherwise touches.

- **`ResultGateway.chart_data` carries no `ChartFilters` parameter.** The frozen
  `08-E_interfaces_contracts.md#7b5` contract — and the `ui/results/protocols.py` Protocol it
  was transcribed into verbatim by STORY-061 — is `chart_data(self, run_id: RunId, chart_kind: ChartKind) -> ChartData`, with no filter-selection or per-chart-option
  parameter, even though `charts_tab.md` §5/§6 describe the aggregator narrowing on the
  tab's global filters and per-chart options. `ChartsTabController` therefore fetches every
  mode-offered chart kind's **full-run** data on each recompute (no filters ever forwarded)
  and the tab's filter-chip/option UI state is captured, persisted, and rendered (dropdown
  "(no data)" suffix, meta line, option controls) but has **no effect on the painted data** —
  a real functional gap versus the full spec, not a simplification of this story's own
  making. Closing it requires either widening the `ResultGateway#7b5` contract with a
  `ChartFilters` parameter or accepting narrower-than-spec behaviour permanently; that
  contract change is out of this story's reach (`compose.py`/interface-contract changes are
  explicitly out of scope — "This story must not touch `compose.py`"). A follow-up story
  should widen `ResultGateway.chart_data` and thread the tab's `ChartFilterState` through it.

- **`ResultGateway.chart_data`'s return type is annotated `-> ChartData`, never
  `HeatmapData`**, even though its docstring says "Compute one chart's prepared
  `ChartData`/`HeatmapData`" and `HEATMAP_TASK_BY_MODEL` (chart 9) genuinely needs
  `HeatmapData`. `ChartsTabController`'s `_chart_data_cache` is typed
  `dict[ChartKind, ChartData | HeatmapData]` to accommodate the wider type the moment a real
  adapter implementation returns one (Python is duck-typed; nothing prevents a concrete
  `ResultGateway` from returning a `HeatmapData` instance at runtime despite the narrower
  static annotation), and `painting.py`/`view.py`'s heatmap paint/hit-test paths are fully
  implemented and unit-tested directly against `HeatmapData` — only the frozen gateway
  contract's return-type annotation itself is narrower than the real need. No test double in
  this story exercises a `HeatmapData` value flowing through `FakeResultGateway.chart_data`
  end-to-end for exactly this reason (its `set_chart_data` helper is typed `ChartData` only,
  matching the Protocol precisely). A follow-up interface-contract story should widen the
  annotation to `ChartData | HeatmapData`.

- **Additional private files beyond the illustrative three-file sketch.** Task 1's
  implementation-structure sketch (§1 of `05_Result_Widget/implementation_structure.md`)
  lists only `view.py`/`controller.py`/`detached_window.py` under `charts_tab/`. This story
  additionally introduces `view_state.py` (the per-run, per-chart-kind persisted
  `ChartsViewState`, mirroring `details_tab/select.py`'s identical persistence-struct role),
  `mode_policy.py` (pure mode-offered-set and skip-empty navigation logic, kept separate from
  `select.py` since it has no dependency on `ChartsViewModel`), `drilldown.py` (pure
  chart-element-click mapping, charts_tab.md §8, kept separate since it is reused by both the
  live tab and `detached_window.py`), `painting.py` (the `QPainter` draw helpers for the five
  chart shapes plus the PNG/SVG export renderers — by far the largest single concern of this
  story and clearly warranting its own file), and `select.py` (the `(cache, filters, run context) -> ChartsViewModel` pure assembly function, extracted from `controller.py` to keep
  that module within the project's lines-per-class limit, mirroring `details_tab/select.py`'s
  and `summary_tab/select.py`'s identical precedent). Every sibling tab (`summary_tab/`,
  `details_tab/`) already carries a `select.py` beyond its own three-file sketch, so this is
  consistent with the established pattern, not a new one.

- **`ChartDrilldownRequest` gained a `category: str | None = None` field** (purely additive).
  Chart 10's (`PER_CATEGORY_BAR`) drill-down row in `charts_tab.md` §8 says a grouped sub-bar
  click narrows "the Models and Category chips" — the Details tab has no `Category` chip
  narrowing path today (`details_tab/select.py`'s `apply_drilldown` only ever sets
  `models`/`tasks`/`statuses`/`verdicts`), so without the field the request shape could not
  even represent chart 10's clicked category, let alone narrow by it. The field was added to
  the shared `ChartDrilldownRequest` struct and `drilldown.map_grouped_bar_click` populates
  it, but `details_tab/select.py`'s `apply_drilldown` (STORY-063, `done`) was **not** modified
  to consume it — the Details tab is explicitly out of this story's scope ("The Details tab
  that receives the drill-down — owned by STORY-063"). The net effect: clicking a chart-10
  sub-bar today narrows the Details tab to the correct model but not (yet) the category. A
  follow-up story extending `details_tab/select.py`'s `apply_drilldown` to also consume
  `request.category` would close this gap with a single additional filter assignment.

- **`select_charts_view_model`'s inputs are bundled into a private `ChartsSelectionInput`
  msgspec.Struct** (`select.py`, not re-exported from `models.py`) to satisfy the
  project's parameter-count limit — mirrors `ResultCollaborators`'s and
  `DetachedChartWindowConfig`'s identical dependency-bundle pattern for the same reason.

- **The "Detach window" click is wired at the parent `ResultController` level**
  (`_mount_charts_tab`/`_on_charts_detach_clicked`), not as a
  `ChartsTabController.on_detach_clicked(self) -> DetachedChartWindow` method as an earlier
  planning sketch suggested — that method would require `charts_tab/controller.py` to import
  `charts_tab/detached_window.py`, which itself imports `controller.py` (for
  `ChartsTabController`, the class `_NonPersistingChartsTabController` subclasses) — a
  circular import. `ResultController` already imports both modules and is the natural owner
  of window construction; this mirrors how `DetailsTabView`'s own "Detach window" action
  (Task Detail Panel, `details_tab.md` §9) is a self-contained reparent action with no
  controller-level detach method either.

- **Box-plot outlier-marker drill-down (chart 12) is not click-mapped.** `charts_tab.md` §8's
  row for chart 12 ("an outlier marker … the Tasks and Models chips narrowed to that marker's
  single `result_id`") is not exercised by any of this story's six acceptance criteria, and
  implementing precise outlier-marker hit-testing (as opposed to the box body, which is not
  itself clickable per the spec) was judged out of proportion to the story's `L` budget
  alongside the twelve-chart-kind painting/navigation/filter/drilldown/detach/export surface
  already covered. `ChartsTabView`'s module docstring documents this simplification. A
  follow-up story can add outlier-marker hit-testing to `_ChartCanvas` using the same
  `_index_*_hits` pattern already established for the other eleven chart-click mappings.

- **`render_chart_png`/`render_chart_svg` use `QImage` + temporary-file I/O, not
  `QPixmap`/`QSvgGenerator` + an in-memory `QBuffer`.** An initial `QBuffer`-backed
  `QIODevice` implementation (for both PNG via `QPixmap.save(buffer, ...)` and SVG via
  `QSvgGenerator.setOutputDevice(buffer)`) was found, empirically, to corrupt the process's
  Qt paint-engine state such that a *later* off-screen `QPixmap`/`QPainter` construction in
  the same process segfaulted — reproducible only when both the PNG and SVG export paths (or
  either alongside any other `QPixmap`-backed `QPainter` smoke test) ran in the same pytest
  session, confirmed via 15+ repeated runs before and after the fix. Switching to `QImage`
  (pure raster, no platform pixmap backend) plus `QSvgGenerator.setFileName`/`QImage.save`
  against a `tempfile`-created path resolved it with zero repeats failing across 15+ runs.
  This is documented here as a real, load-bearing implementation decision rather than a
  simplification — the fixed `2400 x 1600` export resolution and theme-token palette
  requirements (charts_tab.md §12, EC-RES-4) are otherwise unaffected.
