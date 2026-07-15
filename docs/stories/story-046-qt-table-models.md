---
id: STORY-046
title: Provide QAbstractTableModel adapters for the summary, details, and providers tables
status: ready
spec_clauses:
  - 14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules
  - 05_Result_Widget/implementation_structure.md#6-view-model-structs
  - 08_Cross_Cutting/08-Q_event_payload_schemas.md#6-table-and-chart-data-payloads
modules:
  - adapters/qt_table_models/
acceptance_criteria:
  - STORY-046-AC-1
  - STORY-046-AC-2
  - STORY-046-AC-3
depends_on:
  - STORY-001
owner: coder
estimate: M
---

# STORY-046 — Provide QAbstractTableModel adapters for the summary, details, and providers tables

## Goal

Give the UI the `QAbstractTableModel` adapters that back the three tabular surfaces — the
summary table, the details table, and the providers table — over the frozen domain / view-model
rows. Each model exposes rows and columns to a `QTableView` without the widget touching the
backend directly, and each honours Qt's model contract so a view can render, sort, and refresh
correctly.

## In scope

- One `QAbstractTableModel` factory per table (summary, details, providers), each taking a
  frozen row collection and exposing `rowCount`, `columnCount`, `data`, and `headerData`.
- An atomic whole-model reset (`beginResetModel` / `endResetModel`) when a new row collection is
  supplied, so a data refresh is a single consistent swap.
- Each model reads only frozen row objects; it holds no backend Protocol and performs no I/O.

## Out of scope

- The events that push new table data (`_summary_data_changed`, `_detailed_data_changed`) and
  the controllers that call `setRows` — owned by the Result widget's later UI phase; this story
  provides the models the controllers set rows on.
- The chart aggregations and the chart surface — `backend/charts/` and the Charts tab, not a
  table model.
- Row/column selection state and the export footer — owned by the Result widget.

## Spec inputs

- `14_Process_and_Traceability/01_MODULE_INVENTORY.md#5-adapters-modules` — `qt_table_models`
  provides the `QAbstractTableModel` adapters for the summary, details, and providers tables,
  each validated with `QAbstractItemModelTester`, depending only on PySide6 and
  `backend/domain`.
- `05_Result_Widget/implementation_structure.md#6-view-model-structs` — the summary and details
  row view-model shapes (columns and cell values) the models expose to the view.
- `08_Cross_Cutting/08-Q_event_payload_schemas.md#6-table-and-chart-data-payloads` — the summary
  and detailed table data payloads whose rows these models render.

## Design constraints

- `adapters/qt_table_models/` imports PySide6 and `backend/domain` only
  (`01_MODULE_INVENTORY.md` §5); it holds no backend store/service Protocol and does no I/O.
- Each model is validated with `QAbstractItemModelTester` (the Qt model-contract conformance
  check).
- Rows are frozen `msgspec.Struct` objects; the model never mutates a row in place — a data
  change is a whole-model reset.
- No `asyncio`.

## Acceptance criteria

### STORY-046-AC-1

For each table model (summary, details, providers), given a fixed collection of frozen rows,
then `rowCount()` equals the number of rows, `columnCount()` equals that table's column count,
and `data(index, DisplayRole)` at each cell returns the value of the corresponding row field
(table-driven over the three models).

### STORY-046-AC-2

For each table model, given the model wrapped in a `QAbstractItemModelTester`, when the tester
exercises the model, then no model-contract violation is reported (the model satisfies Qt's
`QAbstractItemModel` contract).

### STORY-046-AC-3

Given a table model populated with one row collection, when a new row collection is supplied via
the model's reset entry point, then the model performs a `beginResetModel`/`endResetModel` cycle
and subsequently reports the new rows (a refresh is an atomic whole-model swap).

## Test plan

- STORY-046-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/adapters/qt_table_models/tests/test_table_models.py`,
  `test_row_column_and_cell_data_per_model`.
- STORY-046-AC-2 — unit (`pytest-qt`, `QAbstractItemModelTester`), same file,
  `test_each_model_satisfies_qt_model_contract`.
- STORY-046-AC-3 — unit (`pytest-qt`), same file,
  `test_set_rows_performs_atomic_model_reset`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-046.
- [ ] Every model passes `QAbstractItemModelTester` (STORY-046-AC-2).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `adapters/qt_table_models/`.
- [ ] An architecture test confirms the module holds no backend store/service Protocol and
  imports no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
