---
id: STORY-072
title: Wire the Resume widget Summary and Details export actions to real CSV and Markdown serialization
status: ready
spec_clauses:
  - 03_Resume_Benchmark_Widget/description.md#35-context-menu
  - 03_Resume_Benchmark_Widget/description.md#10-function-inventory
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#2-filename-composition
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#3-common-rules
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#4-summary-table--csv
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#6-details-table--csv
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/resume_benchmark/
acceptance_criteria:
  - STORY-072-AC-1
  - STORY-072-AC-2
  - STORY-072-AC-3
  - STORY-072-AC-4
depends_on:
  - STORY-056
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: M
---

# STORY-072 — Wire the Resume widget Summary and Details export actions to real CSV and Markdown serialization

## Goal

Make the Resume tab's four Summary/Details export actions actually export. Today Export Summary
(CSV), Export Summary (Markdown), Export Details (CSV), and Export Details (Markdown) all call the
`export_table_not_yet_available()` placeholder, which only shows a "Export not yet available" toast.
This story amends the widget's `ResumeGateway` Protocol with a `serialize_table`-shaped method —
mirroring the existing `ResultGateway.serialize_table(run_id, table, fmt) -> str` — wires the four
context-menu actions to invoke it and write the returned payload to the user-chosen destination, and
removes the placeholder. This is the "STORY-056b" promised in STORY-056's notes.

## In scope

- `ui/resume_benchmark/protocols.py`: add `serialize_table(run_id, table, fmt) -> str` to the
  locally-declared `ResumeGateway` Protocol, matching `ResultGateway.serialize_table` (08-E §7b.5).
- `_internal/actions.py`: replace `export_table_not_yet_available()` with real export handlers for
  the four Summary/Details × CSV/Markdown actions — each resolves the destination through
  `NativePickers.save_file` pre-filled with the canonical filename, calls
  `ResumeGateway.serialize_table` with the selected run's id, the correct table token, and the
  correct format, writes the returned payload, and emits an outcome toast.
- The canonical export filename `<sanitised_run_name>_<kind>.<ext>` for the Save picker default
  (`kind` is `Summary` or `Details`; `ext` is `csv` or `md`).

## Out of scope

- The run table, search, sort, status badges, context-menu structure and gating, Clone, Rename,
  Delete, and Show-run-log actions — delivered by STORY-056.
- The Export Run Analysis (Markdown) action — a separate menu item gated on non-empty
  `run_analysis`, not part of the Summary/Details export pair this story wires.
- The Resume/Retry flows — delivered by STORY-057.
- The concrete `ResumeGateway.serialize_table` body that delegates to
  `backend/csv_export`'s `TableSerializer` per the export-format spec — Phase 11 wires it in
  `compose.py`; `ui/resume_benchmark/` may not import `backend/csv_export` directly. This story
  proves the invocation contract and the write against a fake gateway, exactly as STORY-062 did for
  the Result Summary export.
- Wiring the concrete `ResumeGateway` in `compose.py` — this story **must not touch** `compose.py`.

## Spec inputs

- `03_Resume_Benchmark_Widget/description.md#35-context-menu` — the four Summary/Details export
  items (always enabled), the canonical `<effective_run_name>_<kind>.<ext>` filename rule, and the
  export-content-shapes-owned-by-05_EXPORT_FORMATS statement.
- `03_Resume_Benchmark_Widget/description.md#10-function-inventory` — items 12–15: Export Summary
  (CSV), Export Summary (Markdown), Export Details (CSV), Export Details (Markdown), each always
  available.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b3-resumegateway` — the gateway surface this
  widget declares locally; the surface to extend with `serialize_table`.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b5-resultgateway` — the `serialize_table(run_id, table, fmt) -> str` signature to mirror exactly.
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#2-filename-composition` — the canonical filename pattern,
  sanitisation, and the empty-name `Run_<run_id>` fallback.
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#3-common-rules` — UTF-8, LF, single trailing newline,
  and the rule that exports are written verbatim with no redaction step (own-machine data).
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#4-summary-table--csv` — the Summary export's fixed
  column set and content (the `"summary"` table payload).
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#6-details-table--csv` — the Details export's fixed
  column set and content (the `"details"` table payload).
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The controller holds only its `ResumeGateway` Protocol plus `EventBus`, `NativePickers`, and
  `FileSystemActions`; it never holds a `RunsStore`/`ResultsStore`/`TasksStore` directly (D-R-06).
- The export path imports no redaction function: content is written verbatim exactly as
  `serialize_table` returns it (own-machine data, `05_EXPORT_FORMATS.md` §3).
- The `table` argument uses the same token vocabulary as `ResultGateway.serialize_table`
  (`"summary"` / `"details"`); the `fmt` argument uses the same format vocabulary (`"csv"` /
  `"markdown"`) — the two gateways stay signature-compatible so the concrete adapter can share one
  serializer.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope and emits `DEBUG`-level events —
  static event name + keyword fields — at every Gateway call and every user-triggered action.

## Acceptance criteria

### STORY-072-AC-1

For each Summary/Details export action, triggering it invokes `ResumeGateway.serialize_table` with
the selected run's id and the specified table and format tokens:

| Menu action               | table token | fmt token  |
| ------------------------- | ----------- | ---------- |
| Export Summary (CSV)      | `summary`   | `csv`      |
| Export Summary (Markdown) | `summary`   | `markdown` |
| Export Details (CSV)      | `details`   | `csv`      |
| Export Details (Markdown) | `details`   | `markdown` |

### STORY-072-AC-2

Given a run is selected and the user picks a save destination, when an export action runs, then the
payload returned by `ResumeGateway.serialize_table` is written to the chosen path and a success
toast is emitted — the `export_table_not_yet_available` "Export not yet available" toast is never
emitted from any of the four actions.

### STORY-072-AC-3

Given `serialize_table` returns a payload, when the export writes it to disk, then the written bytes
equal that payload verbatim, with no redaction transform applied to the content.

### STORY-072-AC-4

Given a run and a Summary/Details export action, when the Save picker opens, then it is pre-filled
with the canonical filename `<sanitised_run_name>_<kind>.<ext>` (`kind` being `Summary` or
`Details`; `ext` being `csv` or `md`), and a run name that sanitises to empty falls back to
`Run_<run_id>_<kind>.<ext>`.

## Test plan

- STORY-072-AC-1 — table-driven unit (`pytest-qt`, fake `ResumeGateway`), colocated
  `src/ollama_llm_bench/ui/resume_benchmark/tests/test_actions.py`,
  `test_export_invokes_serialize_table_per_action`.
- STORY-072-AC-2 — unit (`pytest-qt`, fake `ResumeGateway` + fake `NativePickers`), same file,
  `test_export_writes_payload_and_no_placeholder_toast`.
- STORY-072-AC-3 — unit, same file, `test_export_writes_payload_verbatim_without_redaction`.
- STORY-072-AC-4 — table-driven unit (`pytest-qt`, fake `NativePickers`), same file,
  `test_export_prefills_canonical_filename`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-072.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises each of the four export
  actions.
- [ ] An architecture test confirms the controller depends only on `ResumeGateway` (plus the
  OS-adapter helpers and Event Bus), that the export path imports no redaction function, and
  that the module references no `setStyleSheet`, embeds no colour literal, and imports no
  `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/resume_benchmark/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-072.
- [ ] The module inventory is unchanged.
- [ ] `export_table_not_yet_available()` is removed and no context-menu action reaches a
  not-yet-available placeholder.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records.

## Notes

- STORY-056's note recorded that landing real Summary/Details export content requires a
  `ResumeGateway.serialize_table` amendment mirroring `ResultGateway.serialize_table` and a
  fold-back into 08-E §7b.3. Because `docs/v3_specification/` is read-only, the 08-E §7b.3 fold-back
  is a spec-owner action, not part of this story; the widget declares the amended method on its
  **locally-owned** `ResumeGateway` Protocol (the established pattern from STORY-056), so no spec
  edit is needed for the code to land and be tested.
- No ADR is introduced: extending the local `ResumeGateway` to match `ResultGateway.serialize_table`
  follows an already-settled interface pattern rather than making a new architectural decision.
