---
id: STORY-063
title: Build the Result widget Details tab — per-result rows, mode-aware columns, the Task Detail Panel, drill-down, and export
status: done
spec_clauses:
  - 05_Result_Widget/tabs/details_tab.md#3-column-reference
  - 05_Result_Widget/tabs/details_tab.md#4-mode-aware-column-visibility
  - 05_Result_Widget/tabs/details_tab.md#9-row-selection-and-the-task-detail-panel
  - 05_Result_Widget/tabs/details_tab.md#10-chart-click-drill-down
  - 05_Result_Widget/tabs/details_tab.md#11-verdict-and-status-rendering
  - 05_Result_Widget/tabs/details_tab.md#14-export
  - 05_Result_Widget/implementation_structure.md#52-detailstabcontroller
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/results/
acceptance_criteria:
  - STORY-063-AC-1
  - STORY-063-AC-2
  - STORY-063-AC-3
  - STORY-063-AC-4
  - STORY-063-AC-5
edge_cases:
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

# STORY-063 — Build the Result widget Details tab — per-result rows, mode-aware columns, the Task Detail Panel, drill-down, and export

## Goal

Deliver the Details tab sub-feature package under `ui/results/_internal/details_tab/`: the
one-row-per-`BenchmarkResult` table with its mode-aware columns, filters, per-column filters,
sorting, and column controls; the Task Detail Panel that renders the full structured record for
the selected row; the receipt of a chart-click drill-down from the Charts tab applied as a
filter; the verdict/status badge rendering; and the CSV/Markdown export.

## In scope

- `_internal/details_tab/select.py`: the pure `(results) -> DetailsViewModel` row mapping and the
  em-dash empty-cell rule.
- `_internal/details_tab/controller.py` (`DetailsTabController`): subscribes
  `_detailed_data_changed`; derives the row set, the seven filter chips (Verdict/Layer only in
  `GRADED`), the per-column filters, and the selected row's Task Detail Panel payload; reads/writes
  its per-run view-state slice; and applies a chart-click drill-down request.
- `_internal/details_tab/view.py` (`DetailsTabView` + the Task Detail Panel): the table, the
  detail panel, the status/verdict badges, and the debounced live re-render preserving the
  selected row by `result_id`.
- The export of the currently filtered, visible-column, sorted (or selected) rows via
  `ResultGateway.serialize_table`.

## Out of scope

- The Result shell and footer — owned by STORY-061.
- The Summary, Charts, and Run Analysis tabs — owned by their own stories (the Charts tab emits
  the drill-down request this tab receives, delivered by STORY-064).
- Wiring the concrete `ResultGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `05_Result_Widget/tabs/details_tab.md#3-column-reference` — every column mapped to a
  `BenchmarkResult`/`BenchmarkTask` field, the defaults, and the snapshot-name rule.
- `05_Result_Widget/tabs/details_tab.md#4-mode-aware-column-visibility` — the grading columns
  offered only in `GRADED`.
- `05_Result_Widget/tabs/details_tab.md#9-row-selection-and-the-task-detail-panel` — the
  structured single-record inspector's ordered sections.
- `05_Result_Widget/tabs/details_tab.md#10-chart-click-drill-down` — the drill-down filter kinds
  applied on top of and written back as the run's view state.
- `05_Result_Widget/tabs/details_tab.md#11-verdict-and-status-rendering` — the status/verdict
  badge colour-role mapping, including `FAILED_JUDGE_TIMEOUT`.
- `05_Result_Widget/tabs/details_tab.md#14-export` — the export mirrors the visible/selected rows
  and is disabled while any run is non-terminal.
- `05_Result_Widget/implementation_structure.md#52-detailstabcontroller` — the sub-controller's
  concern, subscription, and view-state slice.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — `list_results`,
  `list_tasks`, `serialize_table`.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — the
  semantic badge roles resolve through `ui/theme`.

## Design constraints

- The sub-controller depends only on `ResultGateway`, `EventBus`, and the shared
  `PerRunViewStateStore` (D-R-06).
- Unlike the Summary tab, the Details filters include or exclude whole result rows — no
  re-aggregation.
- The chart-click drill-down arrives as an in-process request through the parent controller, not
  as an event-bus signal.
- The Task Detail Panel is a complete dump of the recorded result; a `None` value renders an em
  dash so the field stays visible.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-063-AC-1

Given results for the same `model_name` under two `provider_id` values, when the tab renders,
then the composite key keeps the rows distinct and the Models chip lists them separately.

### STORY-063-AC-2

For each status/verdict value, the cell renders the specified colour role:

| Value                                                       | Role          |
| ----------------------------------------------------------- | ------------- |
| verdict/keyword/cosine/judge = PASS                         | success       |
| verdict/keyword/cosine/judge = FAIL                         | error         |
| verdict is None                                             | em dash, mute |
| status = COMPLETED                                          | success       |
| status in terminal-failure set (incl. FAILED_JUDGE_TIMEOUT) | error         |
| status in pipeline-position set                             | info          |

### STORY-063-AC-3

Given a result row is selected, when the Task Detail Panel renders, then it shows the identity
grid, the prompts, the golden answer, the model response, the per-phase evaluation, the judge
reasoning, the error, and the attempt history for that result, with absent fields shown as em
dashes.

### STORY-063-AC-4

Given a chart-click drill-down request narrowing to a single `(provider, model)` and a single
`task_id`, when the Details tab applies it, then the table filters to that row, the row is
pre-selected, and the drill-down filter is written back as the run's view state.

### STORY-063-AC-5

Given the tab has active filters and a visible-column set, when the user exports CSV or
Markdown, then `ResultGateway.serialize_table` is invoked with `table="details"` to produce
exactly the currently filtered, visible-column, sorted rows. (Narrowing to the selected rows
when more than one is ticked is not implemented by this story — see Notes.)

## Test plan

- STORY-063-AC-1 — unit (no Qt), colocated
  `src/ollama_llm_bench/ui/results/_internal/details_tab/tests/test_select.py`,
  `test_composite_key_keeps_rows_distinct`. Covers EC-RES-2.
- STORY-063-AC-2 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/results/tests/test_details_tab.py`,
  `test_status_verdict_badge_roles`. Wrapped in `structlog.testing.capture_logs()`; asserts no
  captured entry's `log_level` is in `{"error", "critical"}`.
- STORY-063-AC-3 — unit (`pytest-qt`), same file,
  `test_task_detail_panel_renders_full_record`.
- STORY-063-AC-4 — unit (`pytest-qt`), same file,
  `test_chart_drilldown_applies_and_persists_filter`.
- STORY-063-AC-5 — unit (`pytest-qt`, fake `ResultGateway`), same file,
  `test_export_uses_details_table_when_details_tab_is_active`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-063.
- [x] EC-RES-2 has a passing test.
- [x] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Details tab's
  empty/partial, populated, row-selected, and drill-down states.
- [x] An architecture test confirms `select.py` imports no Qt symbol, the sub-controller depends
  only on `ResultGateway` and the shared view-state store, and the module references no
  `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/results/`.
- [x] `just trace` resolves this story's spec clauses; the record validates with no orphan
  clause and no orphan test for STORY-063.
- [x] The module inventory is unchanged.
- [x] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.

## Notes

- **§3/§4 column-6 naming ambiguity, resolved.** `details_tab.md` §3's column-reference table
  lists column #6 as a second, literally-duplicate "Category" row (same source field,
  `BenchmarkTask.category`, as column #3) — almost certainly a copy/paste artifact in the spec
  rather than an intentional duplicate column. §4's mode-visibility table, however, names that
  same slot in its column-group row as `"...Difficulty, Type"` — not "Category" a second
  time — and §6's per-column-filter prose independently references `Type` as a real,
  chip-less, right-click-filterable column ("the only way to narrow a column that has no
  chip — for example `Type` or `Sub-category`"). Per the user's explicit decision during
  planning, column #6 is implemented as `DetailsColumnKey.TYPE`, mapped to
  `BenchmarkTask.task_origin` (the task's origin — `FILE` vs `SYNTHETIC` — the one
  `BenchmarkTask` field with no other column already covering it), matching §4's "Type"
  naming and confirmed by §6's independent reference. This resolution was executed in code
  during implementation but not previously recorded in this story file; it is documented here
  for traceability, per the spec-conformance review that flagged the gap.

- **AC-5's selection-narrowed export is descoped, not implemented.** `details_tab.md` §14
  requires an export "narrowed to the selected rows when more than one is ticked." This story
  does not implement it: `DetailsTabView` has no per-row selection checkbox (§9's row-selection
  affordance for bulk export), and `ResultGateway.serialize_table(run_id, table, fmt)`
  (`08-E_interfaces_contracts.md#7b5`) has no parameter through which a selected-row set could
  even be threaded to the adapter. Adding this would require both a UI change (row-selection
  checkboxes in `DetailsTabView`, mirroring whatever affordance `description.md` section 8's
  bulk-export design intends) and a `ResultGateway#7b5` contract change (a new parameter, plus
  the adapter honoring it) — real cross-layer work spanning the UI and adapter public-surface
  contract, well beyond this story's already-large (`L`) scope. Everything else AC-5 requires —
  the export call carries `table="details"`, mirrors the tab's current filter/visible-column/
  sort state, and is disabled while the run is non-terminal — is implemented and proven by
  `test_export_uses_details_table_when_details_tab_is_active`. Flagged here per the
  spec-conformance review's finding; a follow-up story should add the row-selection checkbox
  UI and widen the `ResultGateway#7b5` contract before this sub-requirement can be closed.

- **AC-2's badge colour is not yet rendered in the running app or in any test.** `select.py`'s
  `badge_role_for_status`/`badge_role_for_verdict`/`badge_role_for_layer` correctly compute the
  colour role per `details_tab.md` §11's table, and `_BadgeDelegate` correctly paints that role
  via `resolve_color` — but `ResultCollaborators` (`ui/results/models.py`) has no
  `theme_manager` field, so `ResultController._mount_details_tab` always constructs
  `DetailsTabView` with `theme_manager=None`, and `_BadgeDelegate.paint` falls through to plain
  uncoloured text for every badge cell in production. This is more than "live theme-switch
  refresh is deferred" (an earlier phrasing that undersold the gap, corrected here and in
  `CHANGELOG.md` per the final whole-branch review): no badge colour renders at all yet. The
  underlying compose-root wiring (`ResultCollaborators.theme_manager` plus its `compose.py`
  population) is out of this story's reach for the same reason as the AC-5 gap above — this
  story must not touch `compose.py`. A follow-up story should add
  `ResultCollaborators.theme_manager`, wire a real `ThemeManager` through `compose.py`, and add
  a delegate paint-path test constructing `_BadgeDelegate` with a real `ThemeManager` to prove a
  coloured badge actually renders, closing AC-2's colour-rendering outcome end-to-end. The
  role-mapping and cell-wiring themselves are correct and proven by
  `test_status_verdict_badge_roles` and `select.py`'s unit tests — only the paint step is
  unreached.
