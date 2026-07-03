# YAML Task File Format

**Status:** Draft
**Owner:** architect
**Audience:** user, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** 09_Task_Editor/field_reference.md, 10_Domain_and_Data/02_DTOS_AND_ENUMS.md, 10_Domain_and_Data/06_IMPORT_FORMATS.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 11_Services_and_Algorithms/12_YAML_FORMATTER.md

This document is the authoritative schema for benchmark task files. A task file is a UTF-8 YAML document that describes one or more benchmark tasks. The Task File Loader reads these files at run-configuration time, and the Task Editor reads, validates, and writes them through a structured UI and a raw-YAML view. This document defines the file structure, every field, the validation policy, the on-save formatting rules, and a full set of worked examples.

---

## Table of Contents

1. Scope and ownership
2. File identity (extension, encoding, naming)
3. Top-level file structure
4. The `schema_version` field
5. Per-task field schema
6. The `required_terms` object
7. Field ordering on save
8. YAML conventions (block, flow, comments)
9. Validation policy (hard error, soft warning, soft info)
10. Comment-preserving round-trip guarantee
11. Worked examples
12. Edge cases

---

## 1. Scope and ownership

A task file holds the benchmark tasks that the application sends to the models under test. Tasks are **not** stored in the SQLite database; they live only in YAML files on disk (see `10_Domain_and_Data/07_FILE_LAYOUT.md` for where users keep them — task files are user-owned and live anywhere on the filesystem, not inside the app-data folder). Each benchmark result row stores a snapshot of the task it was produced from and joins back to the task by `task_id`.

Two components consume this format:

- The **Task File Loader** parses task files at run-configuration time into in-memory `BenchmarkTask` records (see `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`).
- The **Task Editor** provides a structured per-field editing UI plus a raw-YAML view, validates every file, and writes files back with comment-preserving formatting.

Both components apply the identical schema and validation policy defined here.

## 2. File identity (extension, encoding, naming)

| Aspect | Rule |
|---|---|
| Extension | `.yaml` or `.yml`. Any other extension is a hard error and the file is not loaded. |
| Encoding | UTF-8, no byte-order mark (BOM). A BOM is stripped on load; the editor never writes one. |
| Line endings | The editor writes LF (`\n`). Files with CRLF load correctly; on save they are normalised to LF. |
| Trailing newline | The editor writes exactly one trailing newline at end of file. |
| Filename | Free text. Convention is `<category>_<purpose>.yaml`, for example `coding_java.yaml`. The filename has no semantic effect. |

## 3. Top-level file structure

The canonical structure is a top-level `tasks:` key holding a sequence of task mappings. The editor **always writes this canonical form**, so downstream tooling can parse files deterministically.

```yaml
# Canonical form (Form A) — emitted by Save.
schema_version: 1
tasks:
  - task_id: coding_java_two_sum
    question: ...
    golden_answer: ...
  - task_id: coding_java_reverse_list
    question: ...
    golden_answer: ...
```

Two additional forms are **accepted on load** for convenience and are auto-converted to the canonical form in memory:

```yaml
# Form B — a bare top-level sequence (accepted on load).
- task_id: coding_java_two_sum
  question: ...
  golden_answer: ...
```

```yaml
# Form C — a single bare task mapping (accepted on load).
task_id: coding_java_two_sum
question: ...
golden_answer: ...
```

Rules for the top level:

- Form A is the only form the Task Editor writes. When a Form B or Form C file is loaded and saved, it is rewritten as Form A.
- An empty file, or a file whose `tasks:` is an empty sequence, is valid and produces zero tasks. It is saveable and emits `tasks: []`.
- If `schema_version` is present it must appear as a top-level key alongside `tasks:` (Form A). In Form B and Form C there is no place for `schema_version`; such files are treated as `schema_version: 1`.
- Any top-level key other than `schema_version` and `tasks` is unknown. The loader ignores it and the editor preserves it verbatim on round-trip, attaching a soft-info notice.

## 4. The `schema_version` field

```yaml
schema_version: 1
```

| Aspect | Rule |
|---|---|
| Type | Integer. |
| Required | Optional. Absent is treated as `1`. |
| Current value | `1`. |
| Purpose | Lets future readers detect format evolution without guessing. |
| On load | A value of `1` loads normally. A value greater than the highest version this build understands is a hard error for the whole file (the file was written by a newer application build); the loader refuses the file and the editor shows a banner. A value less than `1`, a non-integer, or a negative value is a soft warning and the loader proceeds as `schema_version: 1`. |
| On save | The editor always writes `schema_version: 1` as the first top-level key. |

The format is designed for **additive evolution**: new optional fields may be added under a future `schema_version: 2` without breaking version-1 readers, because unknown task fields are ignored, not rejected (see §5).

## 5. Per-task field schema

Each entry in the `tasks:` sequence is a mapping. The table below is the complete field set. The per-field meaning, format, and validation detail live in `09_Task_Editor/field_reference.md`; this section is the schema-level summary.

| Field | Type | Requirement | Default | Notes |
|---|---|---|---|---|
| `task_id` | string | required, unique | none | Stable join key against result rows. |
| `cosine_enabled` | bool | optional | `true` | Task-level cosine opt-out (DD-46); cosine runs only when `true` and a `golden_answer` exists. |
| `question` | string | required | none | The exact prompt sent to the model. |
| `golden_answer` | string | optional | none | Reference answer for the cosine and judge layers (DD-68). Optional — matches the nullable DTO/DB and synthetic tasks that have none; a Task-Benchmark (timing-only) run never reads it. When absent in a Graded run, the cosine phase does not run for the task and the judge has no reference (it grades on the criteria/keywords only). |
| `category` | string | recommended | `""` | High-level grouping for charts and reports. |
| `sub_category` | string | recommended | `""` | Second-level grouping. |
| `pass_criteria` | string | recommended | `""` | Natural-language pass description for the judge. |
| `fail_criteria` | string | recommended | `""` | Natural-language fail description for the judge. |
| `difficulty` | enum | optional | `medium` | One of `easy`, `medium`, `hard`. |
| `source_language` | string | conditional | `""` | ISO 639-1 code; expected for `translation`. |
| `target_language` | string | conditional | `""` | ISO 639-1 code; expected for `translation`. |
| `source_material` | string | optional | `""` | Background text the prompt operates on. |
| `fail_example` | string | optional | `""` | A concrete known-bad answer shown to the judge. |
| `required_terms` | object | optional | empty | Keyword constraints; see §6. |

### 5.1 `task_id`

- Lowercase `snake_case`, ASCII letters, digits, and underscores. **Over 80 characters is a soft warning** (style); **over 128 characters is a hard error** — 128 is the `TaskIdStr` construction limit (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §2), so an id the loader accepts always constructs (SPEC-089). The soft-warning band is 81–128; nothing in the soft band blocks loading.
- Must be unique within the file. On a duplicate, the loader keeps the first occurrence and discards the rest; the editor flags every row sharing the id as a hard error.
- Empty after whitespace trimming is a hard error; the loader drops the task.

### 5.2 `cosine_enabled` (task-level cosine opt-out — DD-46)

An optional boolean, default `true`. The cosine phase runs for a task only when
`cosine_enabled` is `true` **and** the task has a `golden_answer` — exactly analogous to
the keyword phase, which runs only when the task declares keywords. Set `false` for tasks
where whole-text similarity is not a meaningful quality signal (for example code tasks:
two correct solutions can be textually unrelated); the keyword and judge phases still
grade such a task. A non-boolean value is a soft warning and falls back to `true`.

(The former `task_type` field is **retired** — DD-46: the judge uses one universal prompt
steered by `category`/`sub_category`, so the field had no remaining consumer. A legacy file
containing `task_type` loads with the key ignored and a soft warning.)

### 5.3 `difficulty` enum

An optional enum. A missing value takes the default silently. A value outside the enum is a soft warning, and the loader falls back to the default (`medium`).

### 5.4 Long string fields

`question`, `golden_answer`, `pass_criteria`, `fail_criteria`, `source_material`, and `fail_example` are long strings. Multi-line content uses a YAML literal block scalar (`|`) so that line breaks and indentation are preserved exactly. `question` is a hard error when empty after trimming. `golden_answer` is **optional** (DD-68): an empty/absent `golden_answer` is a **soft warning** ("no golden answer — the cosine phase will be skipped and the judge will have no reference if this task is run in a Graded Benchmark"), never a hard error; the rest are never hard errors on emptiness either.

### 5.5 Unknown task fields

Any task-level key not in the table above is unknown. The loader ignores it. The editor preserves it verbatim through a round-trip and attaches a soft-info notice ("Unrecognised field — preserved but unused"). Unknown fields are never a hard error; this is what makes additive schema evolution safe.

## 6. The `required_terms` object

`required_terms` is an optional mapping with three optional string-list members consumed by the keyword evaluation layer:

```yaml
required_terms:
  exact: ["HashMap", "containsKey"]
  semantic: ["complement lookup", "single pass"]
  forbidden: ["nested loop", "O(n^2)"]
```

| Member | Meaning |
|---|---|
| `exact` | Substrings that must appear verbatim in the response. A missing one fails the keyword layer. Case-sensitive. |
| `semantic` | Concepts the response should convey; matched semantically by the judge, so synonyms count. |
| `forbidden` | Substrings that must not appear in the response. |

Rules:

- Each member defaults to an empty list when absent. An absent `required_terms` mapping is equivalent to all three being empty.
- A list entry that is empty after trimming is a soft warning ("Empty term has no effect").
- A string that appears in both `exact` and `forbidden` is a soft warning ("Term is in both exact and forbidden").
- Empty lists are written in flow style (`[]`); lists with two or more entries are written in block style. A single-entry list is written in flow style.

## 7. Field ordering on save

When `task_editor.auto_format_on_save` is `true` (the default), the editor writes each task's fields in this canonical order:

```
task_id, category, sub_category, difficulty, cosine_enabled,
question, golden_answer, pass_criteria, fail_criteria,
required_terms (exact, semantic, forbidden),
source_language, target_language, source_material, fail_example
```

Fields not present in a task are not emitted (the loader applies defaults). Unknown fields are appended after the known fields, in the order they were first seen. When `auto_format_on_save` is `false`, the editor preserves the file's existing field order and only writes the fields the user changed.

## 8. YAML conventions (block, flow, comments)

| Convention | Rule |
|---|---|
| Indentation | 2 spaces. Tabs are never written and are a hard error on load (invalid YAML). |
| Multi-line strings | Written as literal block scalars (`|`). Single-line strings are written plain or quoted as needed. |
| Lists | Block style for 2+ entries; flow style (`[...]`) for empty and single-entry lists. |
| Mapping keys | Always plain scalars, never quoted. |
| Comments | Preserved on round-trip; see §10. |
| Anchors / aliases | Accepted on load (standard YAML); the editor resolves and does not re-emit them. |

## 9. Validation policy

The Task Editor and the Task File Loader share one validation policy with three severities.

| Severity | Loader behaviour | Editor behaviour |
|---|---|---|
| Hard error | The offending task is dropped (or, for file-level errors, the file is rejected). | Save disabled for the file; the task row shows a red border with a tooltip. |
| Soft warning | The loader accepts the value, applies a fallback where applicable, and records a line in the run log. | Save allowed; the task row shows an amber dot. |
| Soft info | The loader accepts the value silently. | Save allowed; the field strip shows a blue marker. |

### 9.1 File-level rules

| Rule | Severity |
|---|---|
| File extension is not `.yaml` or `.yml` | Hard error — file not loaded. |
| File contains malformed YAML | Hard error — file rejected; editor shows a banner. |
| `schema_version` greater than the highest supported version | Hard error — file rejected. |
| `schema_version` non-integer, negative, or less than 1 | Soft warning — treated as `1`. |
| File has zero tasks | Soft warning — saveable; emits `tasks: []`. |
| Two tasks share the same `task_id` | Hard error on every row sharing the id. |
| Unknown top-level key | Soft info — preserved, unused. |

### 9.2 Per-task rules

| Rule | Severity |
|---|---|
| `task_id` empty after trim | Hard error. |
| `task_id` not `snake_case`, or 81–128 characters | Soft warning (style; does not block). |
| `task_id` longer than 128 characters | Hard error — exceeds the `TaskIdStr` limit (SPEC-089). |
| `task_type` present (retired key — DD-46) | Soft warning — the key is ignored; the file still loads. |
| `cosine_enabled` not a boolean | Soft warning — falls back to `true`. |
| `question` empty after trim | Hard error. |
| `golden_answer` empty after trim | Soft warning (DD-68) — cosine skipped and judge has no reference if run graded; never blocks loading. |
| `difficulty` not in enum | Soft warning — falls back to `medium`. |
| `response_scope` present (retired key — DD-45) | Soft warning — the key is ignored; the file still loads. |
| `pass_criteria` / `fail_criteria` empty in a graded run | Soft warning. |
| `source_language` / `target_language` present for a non-translation task | Soft info. |
| `source_language` / `target_language` not a 2-letter lowercase code | Soft warning. |
| `required_terms` list entry empty after trim | Soft warning. |
| Same string in `required_terms.exact` and `required_terms.forbidden` | Soft warning. |
| Unknown task-level key | Soft info — preserved, unused. |

## 10. Comment-preserving round-trip guarantee

The Task Editor preserves user comments through a load-edit-save cycle. The guarantee:

- A comment attached to a task, a field, or the file header survives a round-trip and stays attached to the same logical element.
- The editor never re-flows or rewrites the text of a comment block.
- When `auto_format_on_save` reorders fields, a comment that precedes a field moves with that field.
- A comment on an unknown field is preserved together with that field.
- Saving a file the user never edited is byte-stable except for the canonical-form conversion (Form B/C to Form A) and end-of-file newline normalisation.

The implementing service and its comment-anchor algorithm are specified in `11_Services_and_Algorithms/12_YAML_FORMATTER.md`.

## 11. Worked examples

### 11.1 Minimal task

```yaml
schema_version: 1
tasks:
  - task_id: factual_capitals_france
    question: What is the capital of France?
    golden_answer: Paris
```

### 11.2 Full task with every field

```yaml
schema_version: 1
tasks:
  - task_id: coding_java_two_sum
    category: Coding
    sub_category: Java
    difficulty: medium
    question: |
      Implement a Java method `int[] twoSum(int[] nums, int target)` that
      returns the indices of the two numbers that add up to `target`.
      Assume exactly one solution exists.
    golden_answer: |
      public int[] twoSum(int[] nums, int target) {
          Map<Integer, Integer> seen = new HashMap<>();
          for (int i = 0; i < nums.length; i++) {
              int complement = target - nums[i];
              if (seen.containsKey(complement)) {
                  return new int[] { seen.get(complement), i };
              }
              seen.put(nums[i], i);
          }
          throw new IllegalArgumentException("No solution");
      }
    pass_criteria: |
      Uses a HashMap to store visited elements and find complements in a
      single pass, achieving O(n) time and O(n) space. Returns correct
      indices and handles duplicate values.
    fail_criteria: |
      Uses nested loops (O(n^2)), returns incorrect indices, fails on
      duplicate values, or is not valid Java.
    required_terms:
      exact:
        - HashMap
        - containsKey
      semantic:
        - complement lookup
        - single pass
      forbidden:
        - nested loop
        - O(n^2)
    source_language: ""
    target_language: ""
    source_material: ""
    fail_example: |
      for (int i = 0; i < n; i++)
        for (int j = i + 1; j < n; j++)   // O(n^2) — fails
          ...
```

### 11.3 Translation task

```yaml
schema_version: 1
tasks:
  - task_id: translation_uk_en_greeting
    category: Text Operations
    sub_category: Translation
    difficulty: easy
    source_language: uk
    target_language: en
    question: |
      Translate the following text to English:
      Добрий день. Я хотів би дізнатися більше про ваші послуги.
    golden_answer: |
      Good afternoon. I would like to learn more about your services.
```

### 11.4 Multi-task file with comments

```yaml
# Text Operations dataset — rewrite and summarization tasks.
# Maintained by the QA team. Keep task_id values stable.
schema_version: 1
tasks:
  # A proofreading task — the response must keep the meaning intact.
  - task_id: text_rewrite_proofread_email
    category: Text Operations
    sub_category: Rewrite
    difficulty: easy
    question: |
      Proofread and correct the grammar of this sentence:
      "Their going to send there report tomorrow."
    golden_answer: |
      They're going to send their report tomorrow.
    required_terms:
      forbidden:
        - Their going
        - send there

  # A summarization task — golden answer is one of several acceptable forms.
  - task_id: text_summarize_release_note
    category: Text Operations
    sub_category: Summarization
    difficulty: medium
    question: |
      Summarise the following release note in one sentence.
    source_material: |
      Version 2.1 adds dark mode, fixes a crash on file export, and
      improves chart rendering speed by roughly forty percent.
    golden_answer: |
      Version 2.1 adds dark mode, fixes an export crash, and speeds up
      chart rendering.
```

### 11.5 Custom task type

```yaml
schema_version: 1
tasks:
  - task_id: sql_query_orders_by_region
    category: Data Extraction and Transformation
    sub_category: SQL
    difficulty: hard
    question: |
      Write a SQL query that returns total order value per region for 2025,
      sorted descending.
    golden_answer: |
      SELECT region, SUM(order_value) AS total
      FROM orders
      WHERE order_year = 2025
      GROUP BY region
      ORDER BY total DESC;
```

## 12. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-TASK-1 | File is malformed YAML | Hard error; file rejected; editor banner. |
| EC-TASK-2 | Two tasks share a `task_id` | Hard error on all sharing rows; loader keeps first. |
| EC-TASK-3 | Task missing a required field | Hard error; loader drops the task. |
| EC-TASK-4 | Task sets `cosine_enabled: false` | Valid; the cosine phase is skipped for that task; keyword and judge phases still run. |
| EC-TASK-5 | Invalid `difficulty` | Soft warning; default applied. |
| EC-TASK-6 | `schema_version` newer than this build | Hard error; file rejected. |
| EC-TASK-7 | File with `tasks: []` or empty file | Soft warning; zero tasks; saveable. |
| EC-TASK-8 | Unknown top-level or task-level key | Soft info; preserved on round-trip. |
| EC-TASK-9 | File has a UTF-8 BOM | BOM stripped on load; never written on save. |
