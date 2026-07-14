---
id: STORY-032
title: Serialize result tables to CSV/Markdown and render result-detail and log HTML
status: ready
spec_clauses:
  - 11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md#63-csv-serialization
  - 11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md#64-markdown-serialization
  - 11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md#66-column-order-invariant
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#21-canonical-pattern
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#4-summary-table--csv
  - 10_Domain_and_Data/05_EXPORT_FORMATS.md#6-details-table--csv
  - 11_Services_and_Algorithms/20_HTML_RENDERING.md#63-escaping-and-safety
  - 11_Services_and_Algorithms/20_HTML_RENDERING.md#61-result-detail-rendering
modules:
  - backend/csv_export/
  - backend/html_rendering/
acceptance_criteria:
  - STORY-032-AC-1
  - STORY-032-AC-2
  - STORY-032-AC-3
  - STORY-032-AC-4
  - STORY-032-AC-5
  - STORY-032-AC-6
edge_cases:
  - EC-EXP-1
  - EC-EXP-2
  - EC-RES-2
depends_on:
  - STORY-001
  - STORY-002
owner: coder
estimate: M
---

# STORY-032 — Serialize result tables to CSV/Markdown and render result-detail and log HTML

## Goal

Give the Result widget its two pure, Qt-free text-transform backends: a table serializer that
converts the Summary and Details result tables into RFC 4180 CSV and GitHub-flavoured Markdown
with a single shared column descriptor per table (so the two formats never drift), a
path-traversal-safe export-filename composer, and an HTML renderer that turns a `BenchmarkResult`
into the task-detail fragment and a `LogEntry` into a log-line fragment, HTML-escaping every
value that originates from a task file, a model, or a provider so no untrusted input can inject
markup.

## In scope

- `backend/csv_export/`: the `TableSerializer` Protocol and `make_table_serializer` factory
  emitting the fixed 13-column Summary and 17-column Details tables in CSV and Markdown, plus
  `compose_export_filename` with the SPEC-064 sanitisation/path-traversal guard.
- `backend/html_rendering/`: the `ResultHtmlRenderer` Protocol and `make_result_html_renderer`
  factory rendering the ordered result-detail section sequence and the log-line fragment, with
  mandatory HTML escaping and the fixed light/dark inline-style palette.

## Out of scope

- Writing the serialized string to disk (atomic temp-then-rename, Save Picker vs direct-save,
  collision suffixing) — owned by `ui/results/` and the OS-adapter layer in a later phase; this
  story returns strings only and never touches the filesystem.
- The view-mirroring rule (applying filter chips, column visibility, order, sort, row selection
  before serialization) — the caller resolves the row set; this story serializes exactly what it
  receives in the order it receives it (`05_EXPORT_FORMATS.md` §3.3).
- Chart PNG/SVG export and the run-analysis Markdown wrapper header — owned by `backend/charts/`
  and the Result widget respectively.
- Qt rich-text widget wiring — this story produces HTML fragment strings only.

## Spec inputs

- `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md#63-csv-serialization` — the RFC 4180
  quoting rules and the verbatim-content, no-formula-injection-prefix policy.
- `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md#64-markdown-serialization` — the metadata
  header block, pipe/`<br>` escaping, and empty-cell single-space rule.
- `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md#66-column-order-invariant` — the single
  shared ordered `(header, extractor)` descriptor iterated by both CSV and Markdown paths.
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#21-canonical-pattern` — the filename sanitisation
  rule: the `[A-Za-z0-9._-]` allowlist, collapsed underscores, stripped leading dots, the
  80-char truncation, and the `Run_<run_id>` fallback (SPEC-064 path-traversal guard).
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#4-summary-table--csv` — the fixed 13-column Summary
  order and headers, including the always-empty `Avg Score` reserved column.
- `10_Domain_and_Data/05_EXPORT_FORMATS.md#6-details-table--csv` — the fixed 17-column Details
  order and headers, and the verbatim `Response` column.
- `11_Services_and_Algorithms/20_HTML_RENDERING.md#63-escaping-and-safety` — the mandatory
  `&`/`<`/`>`/`"` escaping and the prohibition on `<script>`/`<style>`/`<iframe>`/`on*`/network
  `href`/`src` in any output.
- `11_Services_and_Algorithms/20_HTML_RENDERING.md#61-result-detail-rendering` — the ordered
  result-detail section sequence and the omit-empty-section rule.

## Design constraints

- `backend/csv_export/` and `backend/html_rendering/` are Qt-free and asyncio-free
  (`01_MODULE_INVENTORY.md` §4.5). No PySide6 — the HTML renderer produces a string and never
  touches a widget or reads a Qt palette.
- Both services are pure and stateless per call (the HTML renderer's only state is the recorded
  `UiTheme`); the same request yields a byte-identical result.
- **Neither the CSV nor the Details `Response` path redacts** — user prompts and model responses
  are the user's own data, written verbatim after format-specific escaping
  (`08_REDACTION_PATTERNS.md` §1); the HTML renderer escapes but does not redact.
- The Summary table has exactly 13 columns; the Details table has exactly 17 columns; the CSV
  and Markdown of one table iterate the same descriptor so their column sets are identical.
- `icontract` on any `api.py` symbol guards programmer invariants only.

## Acceptance criteria

### STORY-032-AC-1

Given a Summary serialization request, when it is serialized to CSV and to Markdown, then both
outputs carry exactly the 13 columns in the §4 order with identical header labels, the `Avg Score` cell is empty in every row, and the CSV header row is present even for an empty row set.

### STORY-032-AC-2

Given a Details result cell containing a comma, a double quote, and a line feed, when it is
serialized to CSV, then the field is wrapped in double quotes, the embedded quote is doubled, and
the line feed is kept inside the one field per RFC 4180; and when serialized to Markdown, the
line feed becomes `<br>` and a literal pipe becomes `\|`.

### STORY-032-AC-3

For every export-filename input, `compose_export_filename` produces a name containing only
characters in `[A-Za-z0-9._-]` plus the kind/extension separators, never beginning with `.`,
never equal to `.` or `..`, truncated to at most 80 characters for the run-name segment, and
falling back to `Run_<run_id>` when sanitisation yields an empty string.

### STORY-032-AC-4

Given a result-detail render request whose model response literally contains
`<script>alert(1)</script>`, when it is rendered, then the output contains the escaped entity
text and no executable `<script>` tag, and the output contains no `<style>`, `<iframe>`, `on*`
event attribute, or network `href`/`src`.

### STORY-032-AC-5

Given a result-detail render request, when it is rendered, then sections are emitted in the
fixed §6.1 order and a section with no content for the given `result`/`run_mode` is omitted
entirely rather than rendered empty — specifically, a `SYNTHETIC`-mode result omits the grading
section and the per-term table.

### STORY-032-AC-6

For a Details cell whose content originates from a task file or a model response, the serializer
writes it verbatim (after RFC 4180 / Markdown escaping) with no redaction and no formula-injection
neutralising prefix, even when the value begins with `=`, `+`, `-`, or `@`.

## Test plan

- STORY-032-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/csv_export/tests/test_summary_serialization.py`,
  `test_summary_csv_and_markdown_share_thirteen_columns`. Covers TS-01, TS-03, TS-09, TS-16.
- STORY-032-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/csv_export/tests/test_details_escaping.py`,
  `test_details_cell_with_comma_quote_newline_and_pipe`. Covers TS-04, TS-06, TS-07;
  covers EC-EXP-2.
- STORY-032-AC-3 — property (Hypothesis over arbitrary run names), colocated
  `src/ollama_llm_bench/backend/csv_export/tests/test_compose_export_filename.py`,
  `test_filename_is_traversal_safe_and_bounded`. Covers the SPEC-064 guard.
- STORY-032-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/html_rendering/tests/test_escaping_safety.py`,
  `test_result_detail_escapes_markup_and_emits_no_active_html`. Covers HR-06, HR-07, HR-17.
- STORY-032-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/html_rendering/tests/test_section_omission.py`,
  `test_synthetic_result_omits_grading_section`. Covers HR-01, HR-02.
- STORY-032-AC-6 — property (Hypothesis over cell content, incl. leading `=`/`+`/`-`/`@`),
  colocated `src/ollama_llm_bench/backend/csv_export/tests/test_verbatim_content.py`,
  `test_cell_content_is_verbatim_no_prefix`. Covers TS-15; covers EC-EXP-1 and EC-RES-2.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-032.
- [ ] EC-EXP-1, EC-EXP-2, and EC-RES-2 have passing tests.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/csv_export/` and
  `backend/html_rendering/`.
- [ ] An architecture test confirms both modules import no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-032.
- [ ] The module inventory is unchanged.
