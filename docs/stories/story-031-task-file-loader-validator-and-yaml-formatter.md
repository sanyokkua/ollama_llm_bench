---
id: STORY-031
title: Load, validate, and comment-preservingly write YAML task files
status: ready
spec_clauses:
  - 11_Services_and_Algorithms/12_YAML_FORMATTER.md#63-canonical-field-order
  - 11_Services_and_Algorithms/12_YAML_FORMATTER.md#65-comment-anchoring-and-preservation
  - 11_Services_and_Algorithms/12_YAML_FORMATTER.md#66-atomic-save
  - 11_Services_and_Algorithms/12_YAML_FORMATTER.md#11-test-cases
  - 11_Services_and_Algorithms/14_VALIDATION_CASCADE.md#63-the-three-severity-levels
  - 11_Services_and_Algorithms/14_VALIDATION_CASCADE.md#64-severity-aggregation-up-the-cascade
  - 10_Domain_and_Data/04_YAML_TASK_FORMAT.md#3-top-level-file-structure
modules:
  - backend/task_files/
  - backend/yaml_formatter/
acceptance_criteria:
  - STORY-031-AC-1
  - STORY-031-AC-2
  - STORY-031-AC-3
  - STORY-031-AC-4
  - STORY-031-AC-5
  - STORY-031-AC-6
depends_on:
  - STORY-001
  - STORY-002
  - STORY-004
owner: coder
estimate: M
---

# STORY-031 — Load, validate, and comment-preservingly write YAML task files

## Goal

Give the application its task-file I/O layer: a loader-tolerant reader that parses a YAML
task file into `BenchmarkTask` records while skipping malformed tasks, an editor-strict
validator that reports every field-, task-, and file-level problem at its correct severity, and
a comment-preserving `ruamel.yaml` writer that emits each task's fields in the canonical order,
preserves every user comment anchored to its construct, and commits the file atomically so an
interrupted save never leaves a truncated file on disk.

## In scope

- `backend/task_files/`: the `TaskFileLoader` Protocol (loader-tolerant — malformed tasks are
  skipped, not raised) and the `TaskFileValidator` Protocol (editor-strict — reports every
  problem), plus their `make_*` factories and a `backend/task_files/testing.py` fake.
- The three-level validation cascade (field, task, file) and the three-severity model (hard
  error, soft warning, soft info) with maximum-severity aggregation up the cascade, as the
  backend algorithm that both the loader's run-time verdict and the Task Editor's live badges
  consume.
- `backend/yaml_formatter/`: the `YamlFormatter` Protocol and `make_yaml_formatter` factory —
  the single writer of task files — with canonical field ordering, comment preservation, style
  normalization, and the write-temp-then-fsync-then-rename atomic save.

## Out of scope

- The Task Editor UI (files pane, field editor, badge widgets, debounce `QTimer`, live
  re-validation) — owned by `ui/task_editor/` in a later phase; this story supplies the
  Protocols that widget consumes.
- The Task File Loader's consumption inside the New Benchmark run-configuration flow — owned by
  `ui/new_benchmark/` in a later phase.
- The per-field rule catalog authored in `09_Task_Editor/field_reference.md` narrative form —
  this story implements the cascade algorithm that applies those rules and their fixed
  severities, not a re-derivation of each rule's prose.

## Spec inputs

- `11_Services_and_Algorithms/12_YAML_FORMATTER.md#63-canonical-field-order` — the exact fixed
  field order, the unknown-key-preserved-after-canonical rule, and the Form-A top-level
  normalization.
- `11_Services_and_Algorithms/12_YAML_FORMATTER.md#65-comment-anchoring-and-preservation` — how
  end-of-line, standalone, sequence-item, and file-head/tail comments travel with their
  construct through reordering, and the comment-token-count check.
- `11_Services_and_Algorithms/12_YAML_FORMATTER.md#66-atomic-save` — the temp-write, fsync,
  atomic-rename sequence and the untouched-target-on-failure guarantee.
- `11_Services_and_Algorithms/12_YAML_FORMATTER.md#11-test-cases` — YF-1..YF-22, in particular
  the round-trip determinism case YF-20.
- `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md#63-the-three-severity-levels` — the hard
  error / soft warning / soft info definitions and their save behaviour.
- `11_Services_and_Algorithms/14_VALIDATION_CASCADE.md#64-severity-aggregation-up-the-cascade` —
  the `clean < info < warning < error` maximum-severity aggregation from field to task to file.
- `10_Domain_and_Data/04_YAML_TASK_FORMAT.md#3-top-level-file-structure` — the canonical
  `tasks:` top-level shape (Form A) the loader parses and the formatter always writes.

## Design constraints

- `backend/task_files/` and `backend/yaml_formatter/` are Qt-free and asyncio-free; they import
  only `backend/domain`, `backend/infra`, `backend/errors`, and `ruamel.yaml`
  (`01_MODULE_INVENTORY.md` §4.5). No PySide6.
- The formatter is the **single writer** of task files; the loader never serializes YAML. The
  formatter operates only on the round-trip `ruamel.yaml` document handle, never on a plain
  `BenchmarkTask` list, so comment tokens travel with the data.
- The atomic save is unconditional and cannot be disabled; `task_editor.auto_format_on_save`
  gates only the canonical reordering and style normalization, never the atomicity.
- The formatter reports a typed save failure to its caller; it does not raise to the wider
  application. The loader never raises on a malformed individual task — it skips it.
- `icontract` on any `api.py` symbol guards programmer invariants only — never file content.

## Acceptance criteria

### STORY-031-AC-1

For every valid task file, parsing it with `TaskFileLoader` and re-serialising it with
`YamlFormatter` (with `format_on_save` true) yields a file that parses to the same task list —
the round trip is an identity on task content modulo canonical field reordering (YF-20).

### STORY-031-AC-2

Given a task whose keys are in a non-canonical order, when the formatter writes it with
`format_on_save` true, then the written task maps its keys in the fixed canonical order of §6.3,
a canonical key absent from the source is not inserted, and any non-canonical key is preserved
and emitted after the last canonical key present.

### STORY-031-AC-3

Given a task file carrying end-of-line, standalone-above-key, sequence-item, and file-head/tail
comments, when the formatter writes it with fields reordered, then every comment is present in
the output anchored to the same construct it was written against, and the output comment-token
count equals the input count.

### STORY-031-AC-4

Given a save whose temporary-file write fails mid-write, when the formatter reports the failure,
then the target path retains its previous contents byte-for-byte and no temporary file remains.

### STORY-031-AC-5

Given a task file containing one or more malformed tasks among valid ones, when `TaskFileLoader`
loads it, then it returns the valid tasks as `BenchmarkTask` records and skips each malformed
task without raising.

### STORY-031-AC-6

The `TaskFileValidator` assigns each condition its fixed severity and aggregates state up the
cascade as `max(clean, info, warning, error)`, per this table:

| Condition                                  | Field/task/file level | Severity | File-level aggregate          |
| ------------------------------------------ | --------------------- | -------- | ----------------------------- |
| Empty `question` after whitespace-trim     | field                 | error    | error                         |
| Two tasks sharing a `task_id`              | file                  | error    | error                         |
| Non-`.yaml`/`.yml` extension               | file                  | error    | error                         |
| Empty `category`                           | field                 | warning  | warning (absent an error)     |
| Empty file (no tasks)                      | file                  | warning  | warning                       |
| Very long prompt                           | field                 | info     | info (absent a warning/error) |
| A retired `task_type` key in a legacy file | task                  | warning  | warning (absent an error)     |

## Test plan

- STORY-031-AC-1 — property (Hypothesis over generated valid task files), colocated
  `src/ollama_llm_bench/backend/yaml_formatter/tests/test_round_trip.py`,
  `test_load_serialize_load_is_identity_modulo_reorder`. Covers YF-20.
- STORY-031-AC-2 — unit (table-driven over canonical/non-canonical/unknown key mixes), colocated
  `src/ollama_llm_bench/backend/yaml_formatter/tests/test_field_order.py`,
  `test_formatter_emits_canonical_field_order`. Covers YF-5, YF-6, YF-7.
- STORY-031-AC-3 — unit, colocated
  `src/ollama_llm_bench/backend/yaml_formatter/tests/test_comment_preservation.py`,
  `test_comments_survive_reorder_and_token_count_matches`. Covers YF-1..YF-4, YF-19.
- STORY-031-AC-4 — unit (simulated write failure), colocated
  `src/ollama_llm_bench/backend/yaml_formatter/tests/test_atomic_save.py`,
  `test_write_failure_leaves_target_unchanged_and_no_temp`. Covers YF-15, YF-16, YF-17.
- STORY-031-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/task_files/tests/test_loader.py`,
  `test_loader_skips_malformed_tasks_and_returns_valid`.
- STORY-031-AC-6 — unit (table-driven, one case per condition), colocated
  `src/ollama_llm_bench/backend/task_files/tests/test_validation_cascade.py`,
  `test_validator_assigns_severity_and_aggregates`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-031.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/task_files/` and
  `backend/yaml_formatter/`.
- [ ] An architecture test confirms both modules import no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-031.
- [ ] The module inventory is unchanged.
