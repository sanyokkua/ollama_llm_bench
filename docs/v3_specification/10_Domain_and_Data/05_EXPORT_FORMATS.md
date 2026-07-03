# Export Formats

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** 05_Result_Widget/description.md, 10_Domain_and_Data/02_DTOS_AND_ENUMS.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 10_Domain_and_Data/08_REDACTION_PATTERNS.md, 11_Services_and_Algorithms/13_CHART_AGGREGATORS.md

This document defines every file the application produces when a user exports run data. It covers the Summary table, the Details table, the Charts, and the consolidated run analysis. For each export it fixes the filename pattern, the column order, the escaping and encoding rules, and gives a worked example. The application does not redact user-authored prompts or model responses on display or in exports — those are the user's own data on the user's own machine; redaction applies only at the two surfaces named in `10_Domain_and_Data/08_REDACTION_PATTERNS.md` (the `app.*` log records and the provider-SDK error-message wrapping at the adapter boundary).

---

## Table of Contents

1. Export surfaces and the export catalog
2. Filename composition
3. Common rules
4. Summary table — CSV
5. Summary table — Markdown
6. Details table — CSV
7. Details table — Markdown
8. Charts — PNG
9. Charts — SVG
10. Consolidated run analysis — Markdown
11. Save destination and overwrite behaviour
12. Edge cases

---

## 1. Export surfaces and the export catalog

Exports originate from the Result Widget (see `05_Result_Widget/description.md`). Each tab's footer exposes the export buttons appropriate to the kind of content shown. Every export is disabled while any run is in a non-terminal state.

| Source | Kinds produced | Formats |
|---|---|---|
| Summary tab (table) | Summary | CSV, Markdown |
| Details tab (table) | Details | CSV, Markdown |
| Charts tab (image) | one chart per export | PNG, SVG |
| Run Analysis tab (text) | RunAnalysis | Markdown |

The four export kinds and their canonical extensions:

| Kind token | Content | Extensions |
|---|---|---|
| `Summary` | Aggregated per-model statistics table | `.csv`, `.md` |
| `Details` | One row per benchmark result | `.csv`, `.md` |
| `Chart_<chart-slug>` | A single rendered chart | `.png`, `.svg` |
| `RunAnalysis` | Consolidated narrative run analysis | `.md` |

## 2. Filename composition

Every export filename is produced by the export-filename helper used across the application.

### 2.1 Canonical pattern

```
<sanitised_run_name>_<kind>.<ext>
```

Where:

- `sanitised_run_name` — the effective run name with every character outside the set `[A-Za-z0-9._-]` replaced by an underscore `_`. Consecutive underscores are collapsed to one. Leading and trailing underscores **and leading dots** are stripped (so a name can never begin with `.` or be `.`/`..`, closing any path-traversal/hidden-file vector — SPEC-064). The result is truncated to 80 characters. If sanitisation yields an empty string, the literal `Run_<run_id>` is used instead. The same rule applies to the `chart-slug`. This sanitisation guarantees a name-derived filename always stays inside the user-chosen directory; it is referenced from `12_Quality_and_NFRs/02_SECURITY_MODEL.md`.
- `kind` — `Summary`, `Details`, `RunAnalysis`, or `Chart_<chart-slug>`.
- `chart-slug` — the chart's display name sanitised the same way, with spaces replaced by hyphens, for example `Avg-TTFT-per-model`.
- `ext` — `csv`, `md`, `png`, or `svg`.

### 2.2 Collision handling

When a file with the target name already exists in the destination folder, a numeric suffix is appended before the extension: `_2`, `_3`, and so on. The first free index is used. This applies to both the Save Picker default name and direct saves to the exports folder.

### 2.3 Worked filename examples

```
Run_3_Graded_Benchmark_2026-05-16_14-53_Summary.csv
Run_3_Graded_Benchmark_2026-05-16_14-53_Details.md
Run_3_Graded_Benchmark_2026-05-16_14-53_Chart_Avg-TTFT-per-model.png
Run_3_Graded_Benchmark_2026-05-16_14-53_Chart_Pass-rate-per-model.svg
Run_3_Graded_Benchmark_2026-05-16_14-53_RunAnalysis.md
My_Custom_Run_Summary.csv
My_Custom_Run_Summary_2.csv          # collision with an existing file
```

## 3. Common rules

§3.1–§3.2 apply to every text export (CSV and Markdown); §3.3 applies to every export of every kind.

| Aspect | Rule |
|---|---|
| Encoding | UTF-8, no byte-order mark. |
| Line endings | LF (`\n`) on every platform, including Windows. |
| Trailing newline | Exactly one at end of file. |
| Empty values | An empty cell is an empty string. CSV writes `""` only when quoting is otherwise required; Markdown writes a single space to keep the table grid intact. |
| Numbers | Rendered as plain decimal text using `.` as the decimal separator, never localised. Durations are in seconds with 3 decimal places; rates in tokens-per-second with 2 decimal places; scores and rates as a 0.000–1.000 decimal with 3 decimal places. |
| Timestamps | ISO 8601 UTC with a trailing `Z`, for example `2026-05-16T14:53:07Z`. |
| Redaction | The application does not redact user-authored prompts or model responses on display or in exports — these are the user's own data on the user's own machine. Redaction applies only at the two surfaces named in `10_Domain_and_Data/08_REDACTION_PATTERNS.md`. Cell values are written verbatim (after rendering and format-specific escaping). |

### 3.1 CSV escaping

The CSV writer follows RFC 4180 with these specifics:

- Field delimiter is a comma `,`.
- A field is wrapped in double quotes if it contains a comma, a double quote, a line feed, or a carriage return.
- A literal double quote inside a quoted field is doubled (`"` becomes `""`).
- Cell content is written **verbatim** — there is no formula-injection mangling and no neutralizing prefix. Exports carry the user's own task data and the responses of models the user explicitly configured and ran; the export is trusted local content by design (see the threat-model note in `12_Quality_and_NFRs/02_SECURITY_MODEL.md`). RFC 4180 quoting is applied solely for CSV well-formedness, and quoting does not (and is not claimed to) change how a spreadsheet application interprets cell content.
- The header row is always present and follows the same escaping rules.

### 3.2 Markdown table rules

- Tables use GitHub-flavoured Markdown pipe syntax: a header row, a separator row of dashes, then data rows.
- A literal pipe `|` inside a cell is escaped as `\|`.
- A line feed inside a cell is replaced with `<br>` so the table grid stays intact.
- Columns are left-aligned (separator `---`).

### 3.3 View-mirroring rule (filters, visibility, ordering, sort)

Every export reflects the user's **current view** of the source surface. The export captures exactly what the user sees in the active tab at the moment they click the export button; nothing more, nothing less. The rule applies uniformly to all export kinds.

**Tables (Summary CSV, Summary Markdown, Details CSV, Details Markdown).** The exported document contains:

| View state | Effect on the export |
|---|---|
| Active filters (filter chips, per-column filters, search text) | Only rows that pass the active filter set are written. The header row is always present, even when zero rows pass. |
| Column visibility (per-tab show/hide toggles) | Hidden columns are absent from the export — they appear neither in the header row nor in any data row. |
| Column order (user's drag-to-reorder) | Columns appear in the user's current order, not in the canonical order. The header row order matches the data-row order. |
| Sort order (clicking a column header) | Rows are written in the user's current sort order. Stable secondary ordering preserves the user's prior sort key as a tie-breaker. |
| Row selection (Details tab) | When more than one row is selected, the export is narrowed to the selected rows only, still respecting filter, visibility, ordering, and sort. When zero rows are selected, all currently filtered rows are exported. |

A user who has filtered the Details table to "PASS verdicts only", hidden the `judge_reasoning` column, sorted by `total_time_s` ascending, and dragged `provider` to the right of `model` will get a CSV/Markdown whose header row begins `model,provider,...` (with `judge_reasoning` absent), whose rows are only PASS results sorted by `total_time_s` ascending. The on-disk file is the textual mirror of the on-screen table.

**Charts (PNG, SVG).** The exported image is the chart **as currently rendered on screen**, with the active global filter chips and the active per-chart options applied. The exporter renders the chart canvas after every aggregation, filter, and display option has been resolved; the file therefore is pixel-equivalent (PNG) or geometry-equivalent (SVG) to what the user sees on the canvas. Title, axes, legend, in-chart labels, theme palette, and the chart's empty-state message (when no row survives the filters) are all captured. The detached-chart-window export produces the identical bytes for the same view state.

**Consolidated run analysis (Markdown).** The analysis is text, not tabular or graphical, so view-state filters do not apply. The export is the full `BenchmarkRun.run_analysis` field as stored, framed with the standard header described in §10.

**Ownership.** The Result Widget's tab controllers prepare the filtered, visibility-trimmed, reordered, sorted row set before calling `TableSerializationService` (see `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md`); the service serializes exactly what it receives in the order it receives it. The Charts tab controller similarly captures the post-filter `ChartData` / `HeatmapData` produced by the chart aggregator (see `11_Services_and_Algorithms/13_CHART_AGGREGATORS.md`) and feeds it to the chart canvas's PNG/SVG exporter. Per the redaction model (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1), exports do not apply a redaction step; the bytes written to disk are the user's own task content and the model responses from the user's own machine.

## 4. Summary table — CSV

The Summary export holds one row per `(provider, model)` pair benchmarked in the run. Columns appear in this fixed order.

| # | Column header | Content |
|---|---|---|
| 1 | `Provider` | Provider display name — the SNAPSHOT `provider_name` from `BenchmarkResult.provider_name` (DD-33) so the export preserves the historical label across a later rename. The internal `provider_id` is never present in any export column. |
| 2 | `Model` | Model name. |
| 3 | `Tasks` | Number of tasks assigned to this model. |
| 4 | `Completed` | Number of tasks that produced a result. |
| 5 | `Passed` | Count of `PASS` verdicts. |
| 6 | `Failed` | Count of `FAIL` verdicts. |
| 7 | `Pass Rate` | Passed divided by Completed, 0.000–1.000. |
| 8 | `Avg Score` | Mean judge score across completed tasks, 0.000–1.000. |
| 9 | `Avg Cosine` | Mean cosine similarity across completed tasks, 0.000–1.000. |
| 10 | `Avg TTFT (s)` | Mean time to first token, seconds. |
| 11 | `Avg Total Time (s)` | Mean total response time, seconds. |
| 12 | `Avg TPS` | Mean tokens per second. |
| 13 | `Errors` | Count of tasks that ended in an error. |

Columns 7, 8, and 9 are written for every export regardless of run mode; in a performance-only run they hold empty cells where the underlying metric was not computed.

### 4.1 Example

```csv
Provider,Model,Tasks,Completed,Passed,Failed,Pass Rate,Avg Score,Avg Cosine,Avg TTFT (s),Avg Total Time (s),Avg TPS,Errors
ollama_local,llama3.2:3b,10,10,7,3,0.700,0.742,0.681,0.412,3.870,58.20,0
ollama_local,mistral:7b,10,9,8,1,0.889,0.851,0.770,0.905,7.221,41.05,1
anthropic,claude-sonnet-4-5,10,10,10,0,1.000,0.961,0.902,0.733,2.118,73.40,0
```

## 5. Summary table — Markdown

The Markdown export carries the same columns in the same order as the CSV, preceded by a metadata header.

### 5.1 Structure

```markdown
# Summary — Run "<effective run name>"

- Run id: <run_id>
- Mode: <run mode>
- Exported: <ISO 8601 UTC>
- Application: Ollama LLM Bench <app version>

| Provider | Model | Tasks | Completed | Passed | Failed | Pass Rate | Avg Score | Avg Cosine | Avg TTFT (s) | Avg Total Time (s) | Avg TPS | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ... | ... | ... |
```

### 5.2 Example

```markdown
# Summary — Run "Graded Benchmark 2026-05-16 14:53"

- Run id: 3
- Mode: Graded Benchmark
- Exported: 2026-05-16T15:04:22Z
- Application: Ollama LLM Bench 1.0.0

| Provider | Model | Tasks | Completed | Passed | Failed | Pass Rate | Avg Score | Avg Cosine | Avg TTFT (s) | Avg Total Time (s) | Avg TPS | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ollama_local | llama3.2:3b | 10 | 10 | 7 | 3 | 0.700 | 0.742 | 0.681 | 0.412 | 3.870 | 58.20 | 0 |
| anthropic | claude-sonnet-4-5 | 10 | 10 | 10 | 0 | 1.000 | 0.961 | 0.902 | 0.733 | 2.118 | 73.40 | 0 |
```

## 6. Details table — CSV

The Details export holds one row per benchmark result. Columns appear in this fixed order.

| # | Column header | Content |
|---|---|---|
| 1 | `Task Id` | The task's `task_id`. |
| 2 | `Category` | Task category. |
| 3 | `Sub Category` | Task sub-category. |
| 4 | `Difficulty` | `easy` / `medium` / `hard`. |
| 5 | `Provider` | Provider display name — the SNAPSHOT `provider_name` from `BenchmarkResult.provider_name` (DD-33). The internal `provider_id` is never present in any export column. |
| 6 | `Model` | Model name. |
| 7 | `Verdict` | `PASS`/`FAIL` (the `Verdict` enum, uppercased) on a `COMPLETED` row; the **status-derived display tokens** `ERROR` (any terminal-failure status) or `UNKNOWN` (a non-terminal/no-verdict row). `ERROR`/`UNKNOWN` are not `Verdict` enum members — they are render-only tokens (mapping in `11_Services_and_Algorithms/19_TABLE_SERIALIZATION.md` §6.2). Exports are one-way reports; result rows are never re-imported, so this column is not required to round-trip. |
| 8 | `Score` | Judge score, 0.000–1.000. |
| 9 | `Cosine` | Cosine similarity, 0.000–1.000. |
| 10 | `Resolution Layer` | The evaluation layer that set the verdict. |
| 11 | `TTFT (s)` | Time to first token, seconds. |
| 12 | `Total Time (s)` | Total response time, seconds. |
| 13 | `TPS` | Tokens per second. Prefixed `~` when the row's `tokens_estimated` is set (throughput estimated from the response length because the backend reported no usage; SPEC-047). |
| 14 | `Prompt Tokens` | Token count of the prompt. |
| 15 | `Response Tokens` | Token count of the response. |
| 16 | `Error` | Error message if the task failed; empty otherwise. |
| 17 | `Response` | The model's response text. |

Column 17 (`Response`) holds the raw model output. It can be long and multi-line; CSV quoting (§3.1) keeps it in one field. The response is the user's own machine's output and is written verbatim — the application does not apply redaction to exports (see §3 redaction row and `10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1).

### 6.1 Example

```csv
Task Id,Category,Sub Category,Difficulty,Provider,Model,Verdict,Score,Cosine,Resolution Layer,TTFT (s),Total Time (s),TPS,Prompt Tokens,Response Tokens,Error,Response
factual_capitals_france,General Knowledge,Geography,easy,ollama_local,llama3.2:3b,PASS,0.980,0.940,cosine,0.300,0.880,61.30,12,3,,"Paris"
coding_java_two_sum,Coding,Java,medium,ollama_local,mistral:7b,FAIL,0.410,0.000,judge,0.910,8.140,39.80,180,240,,"public int[] twoSum(int[] nums, int target) {
  for (int i = 0; i < nums.length; i++) { ... }
}"
```

## 7. Details table — Markdown

The Markdown Details export uses the same columns and order as the CSV, preceded by the same metadata header used for the Summary Markdown. Line feeds inside the `Response` and `Error` cells are replaced with `<br>` per §3.2.

### 7.1 Example

```markdown
# Details — Run "Graded Benchmark 2026-05-16 14:53"

- Run id: 3
- Mode: Graded Benchmark
- Exported: 2026-05-16T15:04:40Z
- Application: Ollama LLM Bench 1.0.0

| Task Id | Category | Sub Category | Difficulty | Provider | Model | Verdict | Score | Cosine | Resolution Layer | TTFT (s) | Total Time (s) | TPS | Prompt Tokens | Response Tokens | Error | Response |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| factual_capitals_france | General Knowledge | Geography | easy | ollama_local | llama3.2:3b | PASS | 0.980 | 0.940 | cosine | 0.300 | 0.880 | 61.30 | 12 | 3 |  | Paris |
```

## 8. Charts — PNG

Charts export as raster PNG images.

| Aspect | Rule |
|---|---|
| Format | PNG, 8-bit RGBA. |
| Dimensions | 2400 × 1600 physical pixels by default. Fixed; does not scale with display DPI. |
| Background | Solid; matches the active theme (light or dark). Never transparent. |
| Content | The single chart currently shown, including its title, axes, legend, and any in-chart labels. The active global filter chips and the active per-chart options are applied — the image is the chart as currently rendered on the canvas (see §3.3). |
| Colours | The application chart palette for the active theme. |
| Metadata | A `tEXt` chunk records `Software=Ollama LLM Bench <version>`, `Run=<run name>`, and `Exported=<ISO 8601 UTC>`. |
| Filename | `<sanitised_run_name>_Chart_<chart-slug>.png`. |

Each chart is exported individually; there is no combined-chart-sheet export. When the chart is shown in a detached window, the detached window's export produces the identical file.

## 9. Charts — SVG

Charts also export as vector SVG.

| Aspect | Rule |
|---|---|
| Format | SVG 1.1, standalone, UTF-8. |
| Canvas | `viewBox` of `0 0 2400 1600`; the SVG itself has no fixed pixel width so it scales cleanly. |
| Background | An explicit background rectangle matching the active theme. |
| Content | The chart as currently rendered on the canvas, with the active global filter chips and per-chart options applied (see §3.3). The detached-chart-window export produces the identical file. |
| Text | Rendered as `<text>` elements, not outlined paths, so labels remain selectable and searchable. |
| Fonts | The chart font family is named in the SVG; a generic `sans-serif` fallback is included. |
| Metadata | A `<metadata>` element records the application name and version, run name, and export timestamp. |
| Filename | `<sanitised_run_name>_Chart_<chart-slug>.svg`. |

## 10. Consolidated run analysis — Markdown

The Run Analysis tab exports the consolidated narrative analysis of the run as a single Markdown document.

### 10.1 Structure

```markdown
# Run Analysis — "<effective run name>"

- Run id: <run_id>
- Mode: <run mode>
- Started: <ISO 8601 UTC>
- Finished: <ISO 8601 UTC>
- Models: <provider/model list>
- Judge model: <provider/model, or "none" when the run used no judge>
- Exported: <ISO 8601 UTC>
- Application: Ollama LLM Bench <app version>

## Overview

<narrative paragraph(s) summarising overall run outcomes>

## Per-model observations

### <provider>/<model>

<narrative paragraph(s) for this model>

## Notable tasks

<bullet list of tasks worth attention, each with task_id and a short note>
```

Sections that have no content for a given run mode are omitted entirely rather than left empty. The narrative text is generated by the run-analysis service and written verbatim — the run-analysis service does not redact the narrative (`11_Services_and_Algorithms/22_RUN_ANALYSIS_SERVICE.md`), consistent with the redaction model in `10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1 (the narrative is a summary of the user's own benchmark data on the user's own machine).

### 10.2 Example

```markdown
# Run Analysis — "Graded Benchmark 2026-05-16 14:53"

- Run id: 3
- Mode: Graded Benchmark
- Started: 2026-05-16T14:53:07Z
- Finished: 2026-05-16T15:01:55Z
- Models: ollama_local/llama3.2:3b, ollama_local/mistral:7b, anthropic/claude-sonnet-4-5
- Judge model: anthropic/claude-sonnet-4-5
- Exported: 2026-05-16T15:05:10Z
- Application: Ollama LLM Bench 1.0.0

## Overview

Across 30 task executions the strongest performer was claude-sonnet-4-5
with a perfect pass rate, while the local 3B model passed 7 of 10 tasks,
struggling primarily on multi-step reasoning.

## Per-model observations

### ollama_local/llama3.2:3b

Fast first-token latency but lower accuracy on coding tasks; two failures
came from incorrect index handling in array problems.

### anthropic/claude-sonnet-4-5

Consistent passes across all categories with the highest average score.

## Notable tasks

- coding_java_two_sum — failed on mistral:7b due to an O(n^2) solution.
- text_summarize_release_note — all models passed.
```

## 11. Save destination and overwrite behaviour

The destination is governed by the `ui.export_save_directly` setting (see `05_Result_Widget/description.md` §4).

- When the toggle is **off**, an export opens a native Save Picker defaulting to the user's Desktop, pre-filled with the canonical filename. The user may rename or relocate; collision handling falls to the OS picker.
- When the toggle is **on**, an export writes directly to the exports folder `<app-data>/exports/` (see `10_Domain_and_Data/07_FILE_LAYOUT.md`) using the canonical filename and the §2.2 numeric-suffix collision rule. No picker appears.
- A write failure (permission denied, disk full) raises an error modal; the toggle state is unchanged and no partial file is left — the writer writes to a temporary file in the same folder and atomically renames it into place on success.

## 12. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-RES-1 | Run with zero completed results | Export is **disabled** (tooltip "No completed results to export yet") — no file is written and no success toast is shown (SPEC-082); charts export is likewise unavailable. |
| EC-RES-2 | Same model name across two providers | Rows are distinct because `Provider` and `Model` are separate columns. |
| EC-RES-3 | Very long judge analysis text | The full text is exported in full even though the tab truncates the on-screen preview. |
| EC-RES-4 | Chart export under a dark theme | The PNG/SVG background and palette match the active theme. |
| EC-RES-5 | Direct save fails mid-write | Atomic temp-file-then-rename leaves no partial file; an error modal is shown. |
| EC-RES-6 | Run name sanitises to an empty string | Filename falls back to `Run_<run_id>`. |
| EC-EXP-1 | A cell value begins with `=`, `+`, `-`, or `@` | Written verbatim (trusted-content policy); quoted only if RFC 4180 requires it (comma, quote, or newline present). The value byte-for-byte round-trips through any CSV parser. |
| EC-EXP-2 | A response cell contains commas and line feeds | RFC 4180 quoting keeps it in one CSV field; Markdown converts line feeds to `<br>`. |
