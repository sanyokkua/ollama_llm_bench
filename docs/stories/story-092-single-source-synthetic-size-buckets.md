---
id: STORY-092
title: Expose the synthetic-size bucket table on the generator's public surface and consume it from the New Benchmark widget
status: draft
spec_clauses:
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#23-size-definitions
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#8-error-handling
  - 02_New_Benchmark_Widget/description.md#6-validation-rules
modules:
  - backend/performance_task_generator/
  - ui/new_benchmark/
acceptance_criteria:
  - STORY-092-AC-1
  - STORY-092-AC-2
  - STORY-092-AC-3
edge_cases: []
depends_on: []
adrs: []
owner: coder
estimate: M
---

# STORY-092 — Expose the synthetic-size bucket table on the generator's public surface and consume it from the New Benchmark widget

## Goal

Remove a real structural-debt item recorded in STORY-071: the fixed synthetic-size bucket table
(`tiny`=64, `small`=256, `medium`=1024, `large`=4096, `xlarge`=16384 tokens) is hardcoded twice —
once in the New Benchmark widget and once inside the Performance Task Generator's private
`_internal/`, because the UI cannot reach into another module's `_internal/`. The two copies can
silently drift, letting the widget offer a size the generator no longer recognizes. This story makes
the generator the single source: it publishes the bucket table on its public surface, and the
widget consumes that published table instead of holding its own copy, so the widget-local
synthetic-size rule derives its bucket knowledge from the one authoritative source.

## In scope

- Exposing the fixed size-bucket table (bucket label ↔ target token count) on
  `backend/performance_task_generator/`'s public surface (`api.py` / `models.py`), as the single
  authoritative definition per §2.3.
- Changing `ui/new_benchmark/` to read the offered input/output sizes from that published table
  rather than from its own hardcoded copy, and removing the widget-local duplicate.
- Deriving the New Benchmark synthetic "select at least one input size and one output size"
  hard-error rule's bucket-membership knowledge from the published table, so the widget-local
  `SyntheticSizeRuleValidator` no longer carries an independent bucket copy.

## Out of scope

- Building a separate backend `RunValidator` service that subsumes all New Benchmark validation
  rules — there is **no** such module in the module inventory and no spec clause defines it (see
  Notes); this story single-sources the size-bucket table only and folds the size-membership check
  onto the generator's public surface, not into a new backend module.
- The generator's cartesian-expansion algorithm and its `PerformanceConfig` DTO — already delivered
  by STORY-034; unchanged here.
- The performance-matrix controls, defaults, and estimate line — delivered by STORY-071; this story
  only changes where the widget reads the bucket table from.

## Spec inputs

- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#23-size-definitions` — the fixed
  application size-bucket table (label ↔ approximate target token count) that both the generator and
  the widget must share; this is the single authoritative definition.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#8-error-handling` — the generator
  rejects a numeric size with no matching bucket; the membership check the widget performs must
  agree with this by deriving from the same table.
- `02_New_Benchmark_Widget/description.md#6-validation-rules` — the synthetic-mode hard error
  "Select at least one input size and one output size." that gates Start; its size knowledge derives
  from the shared table.

## Design constraints

- `backend/performance_task_generator/` is Qt-free; the published bucket table is plain data
  (`msgspec`/mapping), never a Qt object.
- The UI reads the table only through the generator module's public surface — never by importing the
  generator's `_internal/` package (the `import-linter` contract forbids it), which is exactly why
  the duplicate existed.
- The widget still holds only its `NewBenchmarkGateway` (D-R-06); the published bucket table is
  consumed as read-only data, and no backend store/service Protocol is held directly.
- No `setStyleSheet`, no colour literal, no `asyncio` in the touched UI module.

## Acceptance criteria

### STORY-092-AC-1

Given the Performance Task Generator's public surface, when the size-bucket table is read, then it
returns exactly the canonical mapping `{tiny: 64, small: 256, medium: 1024, large: 4096, xlarge: 16384}`.

### STORY-092-AC-2

Given a fresh New Benchmark widget in Synthetic mode, when it offers input and output sizes, then the
set of offered size buckets equals the generator's published bucket table, and the widget holds no
independent bucket-table copy.

### STORY-092-AC-3

Given Synthetic mode with no input size or no output size selected, when the synthetic size rule
runs, then it produces the hard error "Select at least one input size and one output size." and its
bucket-membership check derives from the generator's published table.

## Test plan

- STORY-092-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_size_buckets_public.py`,
  `test_public_bucket_table_is_the_canonical_mapping`.
- STORY-092-AC-2 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/_internal/tests/test_performance_matrix.py`,
  `test_offered_sizes_equal_generator_published_table`.
- STORY-092-AC-3 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/new_benchmark/tests/test_synthetic_validation.py`,
  `test_missing_size_hard_error_uses_shared_bucket_table`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-092.
- [ ] The widget-local bucket-table copy is removed; a grep/architecture check confirms the token
  targets `64/256/1024/4096/16384` are defined only in `backend/performance_task_generator/`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.

## Notes

- **No backend `RunValidator` module exists.** STORY-071's follow-up spoke of a future backend
  `RunValidator` that would subsume the widget-local `SyntheticSizeRuleValidator`. Neither the module
  inventory (`14_Process_and_Traceability/01_MODULE_INVENTORY.md`) nor the service inventory
  (`11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`) defines such a service or module, and no
  spec clause specifies a backend run-validation service — the New Benchmark validation rules are a
  UI concern (`02_New_Benchmark_Widget/description.md#6-validation-rules`) and the generator does its
  own precondition validation (§4/§8). This story therefore resolves the concrete, spec-grounded half
  of the debt (single-sourcing the bucket table on the generator's public surface). Creating a
  standalone backend `RunValidator` would require an inventory addition and a new spec clause, which
  is a spec-owner decision — reported to the architect run as a gap.
