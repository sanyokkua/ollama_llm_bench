---
id: STORY-062
title: Build the Result widget Summary tab — per-model aggregation, mode-aware columns, filters, sorting, and export
status: done
spec_clauses:
  - 05_Result_Widget/tabs/summary_tab.md#3-identity-model
  - 05_Result_Widget/tabs/summary_tab.md#4-column-reference
  - 05_Result_Widget/tabs/summary_tab.md#5-mode-aware-column-visibility
  - 05_Result_Widget/tabs/summary_tab.md#6-filter-bar
  - 05_Result_Widget/tabs/summary_tab.md#8-sorting
  - 05_Result_Widget/tabs/summary_tab.md#11-export
  - 05_Result_Widget/implementation_structure.md#51-summarytabcontroller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/results/
acceptance_criteria:
  - STORY-062-AC-1
  - STORY-062-AC-2
  - STORY-062-AC-3
  - STORY-062-AC-4
  - STORY-062-AC-5
edge_cases:
  - EC-RES-1
  - EC-RES-2
depends_on:
  - STORY-049
  - STORY-061
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-062 — Build the Result widget Summary tab — per-model aggregation, mode-aware columns, filters, sorting, and export

## Goal

Deliver the Summary tab sub-feature package under `ui/results/_internal/summary_tab/`: the
pure `(results) -> SummaryViewModel` aggregation that groups by the composite
`(provider_id, model_name)` key, the mode-aware column policy, the filter chips that
re-aggregate the contributing rows, the per-column filters, the column-visibility and reorder
controls, the default Avg-TPS-descending sort, and the CSV/Markdown export of exactly what the
user sees.

## In scope

- `_internal/summary_tab/select.py`: the pure aggregation producing one row per model group,
  the em-dash empty-aggregate rule, the low-sample marker, and the snapshot-name rendering.
- `_internal/summary_tab/controller.py` (`SummaryTabController`): subscribes
  `_summary_data_changed`; derives the aggregate rows, the mode-offered column set, and the
  filtered re-aggregation; reads/writes its per-run view-state slice.
- `_internal/summary_tab/view.py` (`SummaryTabView`): the filter bar, the aggregate table, the
  column-visibility popover, drag-to-reorder, and the debounced live re-aggregation.
- The export of the currently filtered, visible-column, sorted rows via
  `ResultGateway.serialize_table`.

## Out of scope

- The Result shell, run selector, footer, and per-run view-state store — owned by STORY-061.
- The Details, Charts, and Run Analysis tabs — owned by their own stories.
- Wiring the concrete `ResultGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `05_Result_Widget/tabs/summary_tab.md#3-identity-model` — the composite `(provider_id, model_name)` grouping key and the snapshot-name display rule that keeps two providers' same-named
  models distinct.
- `05_Result_Widget/tabs/summary_tab.md#4-column-reference` — the per-column aggregations,
  defaults, the em-dash empty-aggregate rule, and the Cosine-Score-as-only-numeric-quality rule.
- `05_Result_Widget/tabs/summary_tab.md#5-mode-aware-column-visibility` — the per-mode
  offered-column matrix; grading columns are offered only in `GRADED`.
- `05_Result_Widget/tabs/summary_tab.md#6-filter-bar` — the four filter chips, the re-aggregation
  on the row-scoped chips, and the Clear-filters rule.
- `05_Result_Widget/tabs/summary_tab.md#8-sorting` — the ascending/descending/clear cycle, the
  numeric sort, the em-dash-sorts-lowest rule, and the default Avg-TPS-descending sort.
- `05_Result_Widget/tabs/summary_tab.md#11-export` — the export mirrors the visible rows and is
  disabled while any run is non-terminal.
- `05_Result_Widget/implementation_structure.md#51-summarytabcontroller` — the sub-controller's
  concern, subscription, derivation, and view-state slice.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — `list_results`,
  `serialize_table`, `get_setting`.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The sub-controller depends only on `ResultGateway`, `EventBus`, and the shared
  `PerRunViewStateStore` (D-R-06).
- `select.py` is a pure function of the results; it holds no Qt import and no store.
- Grouping and display use the composite key and the snapshot `provider_name`, never the live
  catalog name and never the raw `provider_id` in a cell.
- The row-scoped chips (Verdict / Difficulty / Category) re-aggregate; the Models chip removes
  whole rows.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-062-AC-1

Given results for the same `model_name` under two different `provider_id` values, when the tab
aggregates, then two distinct rows are produced and never merged, each labelled with its
snapshot `provider_name`.

### STORY-062-AC-2

For each run mode, the offered column set matches the mode-visibility policy:

| Column group                                                                | SYNTHETIC | TASKS   | GRADED  |
| --------------------------------------------------------------------------- | --------- | ------- | ------- |
| Provider/Model, Tasks, timing, throughput                                   | offered   | offered | offered |
| Pass Rate, Cosine Score, Judge PASS/FAIL, Judge-timeout failures, Layer mix | hidden    | hidden  | offered |

### STORY-062-AC-3

Given a column group whose aggregation has no contributing rows, when the tab renders that cell,
then it shows an em dash, never `0` and never a blank.

### STORY-062-AC-4

Given a row-scoped filter chip (Difficulty) excludes a difficulty, when the tab re-aggregates,
then every visible column recomputes from the surviving contributing rows only.

### STORY-062-AC-5

Given the tab has active filters, a visible-column set, and a sort, when the user exports CSV or
Markdown, then `ResultGateway.serialize_table` is invoked with the run's id, the `"summary"`
table name, and the requested format. This story proves the invocation and the availability of
the current view state (`SummaryTabController.current_view_state`/`current_run_id`) needed to
produce exactly the currently filtered, visible-column, sorted rows; `serialize_table`'s own
signature (`08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway`) takes no
view-state parameter, so mirroring that state into the serialized output is the concern of the
concrete `ResultGateway` adapter that Phase 11 wires in `compose.py` — explicitly out of this
story's scope.

## Test plan

- STORY-062-AC-1 — unit (no Qt), colocated
  `src/ollama_llm_bench/ui/results/_internal/summary_tab/tests/test_select.py`,
  `test_same_model_two_providers_stay_distinct`. Covers EC-RES-2.
- STORY-062-AC-2 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/results/tests/test_summary_tab.py`,
  `test_offered_columns_per_mode`. Wrapped in `structlog.testing.capture_logs()`; asserts no
  captured entry's `log_level` is in `{"error", "critical"}`.
- STORY-062-AC-3 — unit (no Qt), `test_select.py`, `test_empty_aggregate_renders_em_dash`.
  Covers EC-RES-1.
- STORY-062-AC-4 — unit (no Qt), `test_select.py`, `test_row_scoped_filter_reaggregates`.
- STORY-062-AC-5 — unit (`pytest-qt`, fake `ResultGateway`), `test_summary_tab.py`,
  `test_export_mirrors_visible_rows`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-062.
- [x] EC-RES-1 and EC-RES-2 each have a passing test.
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Summary tab's
  empty/partial and populated states. (`view.py` 71%, `controller.py` 89%, `select.py` 97%.)
- [x] An architecture test confirms `select.py` imports no Qt symbol, the sub-controller depends
  only on `ResultGateway` and the shared view-state store, and the module references no
  `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/results/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-062.
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
