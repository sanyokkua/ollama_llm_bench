# Task Editor — Field Reference

**Status:** Draft
**Owner:** architect
**Audience:** user, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `09_Task_Editor/description.md`, `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`, `11_Services_and_Algorithms/12_YAML_FORMATTER.md`

This document is the authoritative per-field reference for the Task Editor. For every field of a benchmark task it states the name, type, requirement, validation rules and their severities, the default value, the inline format hint, the help-popover text, example values, the YAML serialization, and any mode-specific notes. The Task Editor's per-field help popover renders its content from this file. The schema-level summary and worked file examples live in `10_Domain_and_Data/04_YAML_TASK_FORMAT.md`; the per-field detail here and the schema there are kept consistent — where they overlap, this file is the editor-facing presentation of the same rules.

---

## Table of Contents

1. How to read this reference
2. Top-level file structure
3. The `schema_version` field
4. Field — `task_id`
5. Field — `category`
6. Field — `sub_category`
7. Field — `cosine_enabled`
8. Field — `difficulty`
9. (retired — DD-45)
10. Field — `question`
11. Field — `golden_answer`
12. Field — `pass_criteria`
13. Field — `fail_criteria`
14. Field — `required_terms.exact`
15. Field — `required_terms.semantic`
16. Field — `required_terms.forbidden`
17. Field — `source_language`
18. Field — `target_language`
19. Field — `source_material`
20. Field — `fail_example`
21. File-level validations
22. Severity policy and Save gating
23. YAML formatting on save

---

## 1. How to read this reference

Each field section below maps one-to-one to a Field Row in the Task Editor's Field-editor pane and to a key in a task mapping in the YAML file. Every section has the same shape:

- **Name and YAML key** — the key as it appears in the file.
- **Type** — the value type, mappable to the `BenchmarkTask` field in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.
- **Requirement** — required, recommended, optional, or conditional.
- **Default** — the value applied when the key is absent.
- **Format hint** — the muted single line the editor shows below the field label.
- **Help text** — the field's meaning, rendered in the help popover.
- **Validation** — every rule and its severity (hard error, soft warning, soft info).
- **Examples** — at least one example value.
- **YAML serialization** — how Save writes the field.
- **Mode-specific notes** — where the field's relevance depends on the run mode or the task type.

Severities follow the validation cascade (`11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`) and the policy in §22.

## 2. Top-level file structure

A task file is a UTF-8 YAML document. The canonical structure — the only form the Task Editor writes — is a top-level `schema_version` key followed by a top-level `tasks:` key holding a sequence of task mappings:

```yaml
schema_version: 1
tasks:
  - task_id: factual_capitals_france
    question: What is the capital of France?
    golden_answer: Paris
```

Two further forms are accepted on load and auto-converted to the canonical form in memory: a bare top-level sequence of task mappings, and a single bare task mapping. The complete top-level structure rules, including the accepted forms, are specified in `10_Domain_and_Data/04_YAML_TASK_FORMAT.md` §3. The editor always writes the canonical form on Save.

## 3. The `schema_version` field

- **YAML key:** `schema_version`
- **Type:** integer
- **Requirement:** optional
- **Default:** `1`
- **Help text:** Identifies the task-file format generation. The current value is `1`. The editor writes it as the first top-level key on every Save.
- **Validation:**

| Rule | Severity |
|---|---|
| Value greater than the highest version the build understands | Hard error — the whole file is rejected; the editor shows a banner and Save is disabled. |
| Non-integer, negative, or less than `1` | Soft warning — the file is treated as `schema_version: 1`. |
| Absent | None — treated as `1`. |

- **YAML serialization:** Save always writes `schema_version: 1` as the first top-level key.

`schema_version` is a file-level key, not a per-task field; it has no Field Row in the per-task editor.

---

## 4. Field — `task_id`

- **YAML key:** `task_id`
- **Type:** string · `BenchmarkTask.task_id` (`TaskIdStr`)
- **Requirement:** required
- **Default:** none
- **Format hint:** `snake_case, ASCII, max 80 characters, unique in file`
- **Help text:** The unique identifier of the task within its file. It is the stable join key against every benchmark result row, so changing it after a run separates the task from its historical results. Use lowercase `snake_case`. A common convention is `<category>_<sub_category>_<short_summary>`.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty after whitespace trimming | Hard error — the Task File Loader would drop the task. |
| Duplicate of another task's `task_id` in the same file | Hard error — reported on every row sharing the id; the loader keeps the first occurrence and discards the rest. |
| Not lowercase `snake_case` (contains uppercase, spaces, or dashes), or longer than 80 characters | Soft warning — editor convention. |

- **Examples:** `coding_java_two_sum`, `translation_uk_en_greeting`, `factual_capitals_france`
- **YAML serialization:** A plain single-line scalar; quoted only if the value would otherwise not parse as a string.
- **Mode-specific notes:** Required in every mode. `Add Task` seeds the value `<filename_stem>_new_<N>`; `Duplicate Task` appends `_copy<N>` to keep the clone unique.

## 5. Field — `category`

- **YAML key:** `category`
- **Type:** string · `BenchmarkTask.category`
- **Requirement:** recommended
- **Default:** `""` (empty string)
- **Format hint:** `recommended, free text, Sentence Case`
- **Help text:** The high-level grouping the task belongs to, shown in charts and reports (for example "Coding", "Text Operations", "Data Extraction and Transformation"). Leaving it empty does not block a run but removes the task from per-category aggregation.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty after whitespace trimming | Soft warning — "Category recommended for chart aggregation". |
| Longer than 60 characters | Soft warning. |

- **Examples:** `Coding`, `Text Operations`, `Data Extraction and Transformation`
- **YAML serialization:** A plain single-line scalar. Not emitted when absent.
- **Mode-specific notes:** Used by the per-category charts and the category filter of the Result widget.

## 6. Field — `sub_category`

- **YAML key:** `sub_category`
- **Type:** string · `BenchmarkTask.sub_category`
- **Requirement:** recommended
- **Default:** `""` (empty string)
- **Format hint:** `recommended, free text, Sentence Case`
- **Help text:** The second-level grouping within a category (for example "Java", "Translation", "Text to JSON"). It refines `category` and gives finer-grained breakdowns in reports.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty after whitespace trimming | Soft warning. |
| Longer than 60 characters | Soft warning. |

- **Examples:** `Java`, `Translation`, `Text to JSON`
- **YAML serialization:** A plain single-line scalar. Not emitted when absent.
- **Mode-specific notes:** None.

## 7. Field — `cosine_enabled`

- **YAML key:** `cosine_enabled`
- **Type:** bool · `BenchmarkTask.cosine_enabled`
- **Requirement:** optional
- **Default:** `true`
- **Format hint:** `optional, default true`
- **Help text:** Task-level cosine opt-out (DD-46). When checked (the default), the cosine
  phase compares the model's response to the golden answer and grades it against the
  single `eval.cosine_threshold`. Uncheck it for tasks where whole-text similarity is not
  a meaningful signal — for example code tasks, where two correct solutions can be
  textually unrelated; the keyword and judge phases still grade the task.
- **Validation:**

| Rule | Severity |
|---|---|
| Absent | None — defaults to `true`. |
| Not a boolean | Soft warning — the loader falls back to `true`. |

- **Examples:** `true`, `false`
- **YAML serialization:** A plain boolean scalar; omitted on save when `true` (the default).
- **Mode-specific notes:** Consumed by the cosine phase, which runs only in `GRADED`
  mode and only for tasks that have a `golden_answer`. In `TASKS` and `SYNTHETIC`
  no grading runs, so the value is recorded but unused.

(The former field 7, `task_type`, is **retired** — DD-46: the judge uses one universal
prompt steered by `category`/`sub_category`. A legacy file containing `task_type` loads
with the key ignored and a soft warning.)

## 8. Field — `difficulty`

- **YAML key:** `difficulty`
- **Type:** enum · `BenchmarkTask.difficulty` (`Difficulty`)
- **Requirement:** optional
- **Default:** `medium`
- **Format hint:** `optional, default medium`
- **Help text:** The declared difficulty band of the task, used for the per-difficulty breakdown in charts and reports. It does not change how the task is graded.
- **Allowed values:** `easy`, `medium`, `hard` — the members of the `Difficulty` enum.
- **Validation:**

| Rule | Severity |
|---|---|
| Absent | None — defaults to `medium`. |
| A value outside the enum | Soft warning — the loader falls back to `medium`. |

- **Examples:** `easy`, `medium`, `hard`
- **YAML serialization:** A plain single-line scalar. The editor's control is a dropdown of the three members, so an out-of-enum value only arises in externally edited files.
- **Mode-specific notes:** Used by the per-difficulty chart filters of the Result widget.

## 9. (retired — DD-45)

The `response_scope` field is **removed**: the cosine phase applies the single
user-configured `eval.cosine_threshold` to the whole-text Cosine Score; no per-task scope
exists. The numbering slot is kept to avoid renumbering fields 10+. A legacy task file
containing a `response_scope` key loads with the key ignored and a soft warning
(`10_Domain_and_Data/04_YAML_TASK_FORMAT.md` §9.2).

## 10. Field — `question`

- **YAML key:** `question`
- **Type:** string (long) · `BenchmarkTask.question` (`NonEmptyStr`)
- **Requirement:** required
- **Default:** none
- **Format hint:** `required, plain text or markdown`
- **Help text:** The exact prompt sent to the model. The model sees this verbatim — there is no template wrapping beyond the globally configured system prompt. Multi-line content and code fences are allowed.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty after whitespace trimming | Hard error — the loader would drop the task. |
| Longer than 8000 characters | Soft info — "Very long prompt — may push the model's context window". |

- **Examples:**

```yaml
question: What is the capital of France?
```

```yaml
question: |
  Translate the following text to English:
  Добрий день. Я хотів би дізнатися більше про ваші послуги.
```

- **YAML serialization:** Single-line values are written as plain scalars; any value containing a newline is written as a YAML literal block scalar (`|`), preserving line breaks and indentation verbatim.
- **Mode-specific notes:** Required in every mode that runs file tasks (`TASKS`, `GRADED`).

## 11. Field — `golden_answer`

- **YAML key:** `golden_answer`
- **Type:** string (long) · `BenchmarkTask.golden_answer`
- **Requirement:** required
- **Default:** none
- **Format hint:** `required, supports literal block`
- **Help text:** The reference answer used by the keyword and cosine evaluation layers and shown to the judge in `GRADED`. It can be plain text, code, JSON, CSV — anything a comparison makes sense over. For code answers use a literal block so indentation is preserved exactly.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty after whitespace trimming | Hard error — the loader would drop the task. |

- **Examples:**

```yaml
golden_answer: Paris
```

```yaml
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
```

- **YAML serialization:** As `question` — plain for single-line, literal block (`|`) for multi-line. The editor renders the input in a monospace font.
- **Mode-specific notes:** Used only in `GRADED`: the cosine phase compares the model's response to this value, and the judge phase is told about it. In `TASKS` and `SYNTHETIC` no grading runs, so the field is recorded in the task file but unused at evaluation time. A task authored for `GRADED` remains fully usable in `TASKS` — the field simply stays unused.

## 12. Field — `pass_criteria`

- **YAML key:** `pass_criteria`
- **Type:** string (long) · `BenchmarkTask.pass_criteria`
- **Requirement:** recommended (effectively required for `GRADED`)
- **Default:** `""` (empty string)
- **Format hint:** `recommended, plain prose, 1-3 sentences`
- **Help text:** A natural-language description of what the model must do to receive a passing verdict. The judge weighs it heavily in `GRADED`. Cover the shape of a correct answer and the details that matter most.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty when the task is graded in a `GRADED` run | Soft warning — "Empty pass_criteria — the judge will fall back to a golden_answer comparison only". Shown when `task_editor.warn_on_empty_grading_criteria` is `true` (the default). |
| Longer than 500 characters | Soft info. |

- **Examples:**

```yaml
pass_criteria: |
  Uses a HashMap to store visited elements and find complements in a
  single pass, achieving O(n) time and O(n) space. Returns correct
  indices and handles duplicate values.
```

- **YAML serialization:** Plain for single-line, literal block (`|`) for multi-line.
- **Mode-specific notes:** Used only by the judge phase, which runs only in `GRADED`. `TASKS` and `SYNTHETIC` never grade, so the field is recorded in the task file but unused at evaluation time, and the empty-criteria warning does not fire. A task authored for `GRADED` remains fully usable in `TASKS` — the field simply stays unused.

## 13. Field — `fail_criteria`

- **YAML key:** `fail_criteria`
- **Type:** string (long) · `BenchmarkTask.fail_criteria`
- **Requirement:** recommended (effectively required for `GRADED`)
- **Default:** `""` (empty string)
- **Format hint:** `recommended, plain prose, often the inverse of pass_criteria`
- **Help text:** A natural-language description of what makes an answer fail. The judge uses it to detect anti-patterns that look correct on the surface but break the spirit of the task. It is often the inverse of `pass_criteria`.
- **Validation:**

| Rule | Severity |
|---|---|
| Empty when the task is graded in a `GRADED` run | Soft warning. Shown when `task_editor.warn_on_empty_grading_criteria` is `true`. |
| Longer than 500 characters | Soft info. |

- **Examples:**

```yaml
fail_criteria: |
  Uses nested loops (O(n^2)), returns incorrect indices, fails on
  duplicate values, or is not valid Java.
```

- **YAML serialization:** Plain for single-line, literal block (`|`) for multi-line.
- **Mode-specific notes:** Used only by the judge phase, which runs only in `GRADED`. In `TASKS` and `SYNTHETIC` the field is recorded but unused at evaluation time.

## 14. Field — `required_terms.exact`

- **YAML key:** `required_terms` → `exact`
- **Type:** list of strings · `BenchmarkTask.required_terms.exact` (`RequiredTerms.exact`)
- **Requirement:** optional
- **Default:** empty list
- **Format hint:** `substrings that MUST appear verbatim`
- **Help text:** Substrings that must appear verbatim in the model's response. The keyword evaluation phase fails the task if any of these is missing. Matching is case-sensitive. An empty list means no exact-term constraint.
- **Validation:**

| Rule | Severity |
|---|---|
| A list entry empty after whitespace trimming | Soft warning — "Empty exact term has no effect". |

- **Examples:** `["HashMap", "containsKey"]`
- **YAML serialization:** Written under `required_terms.exact`. A list with two or more entries is written in block style, one entry per line; an empty list is written in flow style as `[]`; a single-entry list is written in block style. The editor's control is a Chip Input.
- **Mode-specific notes:** Consumed by the keyword phase, which runs only in `GRADED`. In `TASKS` and `SYNTHETIC` the list is recorded but unused at evaluation time.

## 15. Field — `required_terms.semantic`

- **YAML key:** `required_terms` → `semantic`
- **Type:** list of strings · `BenchmarkTask.required_terms.semantic`
- **Requirement:** optional
- **Default:** empty list
- **Format hint:** `concepts the response should convey`
- **Help text:** Concepts the response should convey, matched semantically by embedding similarity rather than literally — synonyms count. Use short concept phrases.
- **Validation:**

| Rule | Severity |
|---|---|
| A list entry empty after whitespace trimming | Soft warning — "Empty semantic term has no effect". |

- **Examples:** `["complement lookup", "single pass"]`
- **YAML serialization:** As `required_terms.exact` — block style for two or more entries, flow `[]` for empty. Chip Input control.
- **Mode-specific notes:** Evaluated by embedding similarity in the keyword phase of a `GRADED` run. In `TASKS` and `SYNTHETIC` no grading runs, so the list is recorded but unused at evaluation time.

## 16. Field — `required_terms.forbidden`

- **YAML key:** `required_terms` → `forbidden`
- **Type:** list of strings · `BenchmarkTask.required_terms.forbidden`
- **Requirement:** optional
- **Default:** empty list
- **Format hint:** `substrings that MUST NOT appear`
- **Help text:** Substrings that must not appear in the model's response. Useful for "rewrite without these words" tasks and "avoid this pattern" coding tasks. The keyword phase fails the task if any forbidden term is present.
- **Validation:**

| Rule | Severity |
|---|---|
| A list entry empty after whitespace trimming | Soft warning — "Empty forbidden term has no effect". |
| A string that also appears in `required_terms.exact` | Soft warning — "Term is in both exact and forbidden". |

- **Examples:** `["nested loop", "O(n^2)", "brute force"]`
- **YAML serialization:** As the other term lists — block style for two or more entries, flow `[]` for empty. Chip Input control.
- **Mode-specific notes:** Consumed by the keyword phase, which runs only in `GRADED`. In `TASKS` and `SYNTHETIC` the list is recorded but unused at evaluation time.

## 17. Field — `source_language`

- **YAML key:** `source_language`
- **Type:** string · `BenchmarkTask.source_language`
- **Requirement:** optional
- **Default:** `""` (empty string)
- **Format hint:** `ISO 639-1 code, lowercase, two letters`
- **Help text:** The language code of the input prompt, used by the judge prompt template for translation tasks. Use the lowercase two-letter ISO 639-1 code.
- **Validation:**

| Rule | Severity |
|---|---|
| Absent | None — the field is optional (DD-46: no conditional driver exists). |
| Not a lowercase two-letter code | Soft warning. |

- **Examples:** `uk`, `en`, `de`, `hr`
- **YAML serialization:** A plain single-line scalar. Not emitted when absent.
- **Mode-specific notes:** Useful for translation-style tasks; lives in the always-available "Translation extras" group (DD-46).

## 18. Field — `target_language`

- **YAML key:** `target_language`
- **Type:** string · `BenchmarkTask.target_language`
- **Requirement:** optional
- **Default:** `""` (empty string)
- **Format hint:** `ISO 639-1 code, lowercase, two letters`
- **Help text:** The language code of the expected output. Same rules as `source_language`.
- **Validation:** Identical to `source_language` (§17), applied to the target language.
- **Examples:** `en`, `hr`, `de`
- **YAML serialization:** A plain single-line scalar. Not emitted when absent.
- **Mode-specific notes:** Useful for translation-style tasks; appears in the always-available "Translation extras" group (DD-46).

## 19. Field — `source_material`

- **YAML key:** `source_material`
- **Type:** string (long) · `BenchmarkTask.source_material`
- **Requirement:** conditional — expected for `text_rewrite`, `data_extraction`, and `summarization`
- **Default:** `""` (empty string)
- **Format hint:** `optional, plain text / markdown / code`
- **Help text:** Background material the prompt operates on — an article to summarise, a file to convert, code to review. It is often also embedded inside `question`; keeping both makes the task self-documenting.
- **Validation:**

| Rule | Severity |
|---|---|
| Longer than 8000 characters | Soft info. |

- **Examples:**

```yaml
source_material: |
  Version 2.1 adds dark mode, fixes a crash on file export, and
  improves chart rendering speed by roughly forty percent.
```

- **YAML serialization:** Plain for single-line, literal block (`|`) for multi-line. Not emitted when absent.
- **Mode-specific notes:** The Field Row appears in the "Rewrite source" group for `text_rewrite` and the "Input material" group for `data_extraction` and `summarization`.

## 20. Field — `fail_example`

- **YAML key:** `fail_example`
- **Type:** string (long) · `BenchmarkTask.fail_example`
- **Requirement:** optional
- **Default:** `""` (empty string)
- **Format hint:** `optional, a concrete known-bad answer`
- **Help text:** A concrete example of an answer that should fail. The judge uses it as a contrasting reference when a response is ambiguous.
- **Validation:** No rule beyond the absence of a length cap; an empty value is never flagged.
- **Examples:**

```yaml
fail_example: |
  for (int i = 0; i < n; i++)
    for (int j = i + 1; j < n; j++)   // O(n^2) — fails
      ...
```

- **YAML serialization:** Plain for single-line, literal block (`|`) for multi-line. Not emitted when absent. Always available, in the "Optional context" group.
- **Mode-specific notes:** Used by the judge phase, which runs only in `GRADED`. In `TASKS` and `SYNTHETIC` the field is recorded but unused at evaluation time.

## 21. File-level validations

In addition to the per-field rules, the editor enforces file-wide rules. These belong to the file level of the validation cascade.

| Rule | Severity |
|---|---|
| Two tasks share the same `task_id` | Hard error on every row sharing the id. |
| The file has zero tasks | Soft warning — still saveable; Save writes an empty `tasks: []`. |
| The file extension is not `.yaml` or `.yml` | Hard error — the file is not loadable. |
| The file contains malformed YAML on load or reload | Hard error — the parse fails; the editor shows a banner; Save is disabled. |
| `schema_version` is greater than the highest supported version | Hard error — the file is rejected. |
| An unknown top-level key (other than `schema_version` and `tasks`) | Soft info — preserved verbatim on round-trip, unused. |
| An unknown task-level key | Soft info — preserved verbatim on round-trip, unused. |

## 22. Severity policy and Save gating

The three severities and their effect on Save:

| Severity | Save behaviour | UI |
|---|---|---|
| Hard error | Save **disabled** for the offending file; the file status icon is the error glyph; the offending task row carries the error glyph; the field input carries a red border with a tooltip; the toolbar pill is red. | — |
| Soft warning | Save **allowed**; the file status icon is the warning glyph; the task row carries the warning glyph; the field strip is amber. | — |
| Soft info | Save **allowed**; the file status icon stays the clean glyph; the field strip shows a blue marker. | — |

This policy mirrors the Task File Loader's run-time behaviour: a hard error is exactly the condition under which the loader would drop a task or reject a file, and a soft warning is what the loader accepts but records in the run log. Save is gated per file — a file with any hard error cannot be saved; Save All saves only the files free of hard errors. The full cascade algorithm, including the debounce timing and badge aggregation, is in `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md`.

## 23. YAML formatting on save

When `task_editor.auto_format_on_save` is `true` (the default), Save writes each task's fields in this canonical order:

```
task_id, category, sub_category, difficulty, cosine_enabled,
question, golden_answer, pass_criteria, fail_criteria,
required_terms (exact, semantic, forbidden),
source_language, target_language, source_material, fail_example
```

Formatting rules applied on Save:

- A canonical field absent from a task is not inserted; only the fields the task actually carries are written.
- An unknown (non-canonical) key is preserved and emitted after the last canonical key, in its original relative order.
- Multi-line string values are written as YAML literal block scalars (`|`).
- Term lists with two or more entries are written in block style; empty lists in flow style as `[]`.
- Indentation is two spaces; the file is UTF-8 with no BOM and ends with exactly one trailing newline.
- The top-level shape is normalised to the canonical `schema_version` + `tasks:` form.

When `auto_format_on_save` is `false`, Save preserves the file's existing field order and styles and normalises only the top-level shape. In every case Save is atomic (a temporary file written then renamed) and comment-preserving. The serializer that implements all of this — including the comment-anchoring algorithm — is specified in `11_Services_and_Algorithms/12_YAML_FORMATTER.md`.
