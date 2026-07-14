---
id: STORY-034
title: Expand a PerformanceConfig into a deterministic synthetic BenchmarkTask set
status: done
spec_clauses:
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#3-outputs
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#61-generation-steps
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#5-postconditions
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#8-error-handling
  - 11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#11-test-cases
modules:
  - backend/performance_task_generator/
acceptance_criteria:
  - STORY-034-AC-1
  - STORY-034-AC-2
  - STORY-034-AC-3
  - STORY-034-AC-4
  - STORY-034-AC-5
depends_on:
  - STORY-001
owner: coder
estimate: M
---

# STORY-034 — Expand a PerformanceConfig into a deterministic synthetic BenchmarkTask set

## Goal

Give the `SYNTHETIC` run its task source: a pure, Qt-free generator that expands a
`PerformanceConfig` input-size × output-size × repeats grid into a deterministic tuple of fully
populated `BenchmarkTask` records, one per combination, each carrying a deterministic padded
prompt, a stable generated `task_id`, synthetic markers, and no grading fields — so the rest of
the pipeline treats synthetic tasks identically to file tasks.

## In scope

- `backend/performance_task_generator/`: the `PerformanceTaskGenerator` Protocol,
  `make_performance_task_generator` factory, and a `backend/performance_task_generator/testing.py`
  fake.
- The cartesian expansion with the fixed nesting order (input size outer, output size middle,
  repeat inner) and ascending-sorted axes, producing `len(input_sizes) × len(output_sizes) × repeats` tasks.
- Deterministic prompt construction (padding to the input bucket's target token count, appending
  the fixed output-length instruction) and the `perf_in-<label>_out-<label>_rep-<NN>` task id.
- The synthetic field values of §3 (`task_origin`, `category`, empty grading fields,
  size labels, `repeat_index`, `task_order`) and the size-bucket mapping.

## Out of scope

- Persisting the generated tasks as `benchmark_tasks` rows and creating the per-`(task × model)`
  `benchmark_results` fan-out — owned by the run-creation use case in `backend/benchmark_pipeline/`
  (STORY-029 and later); this story returns an in-memory tuple and persists nothing.
- Assembling the `PerformanceConfig` from the New Benchmark widget's size selections and repeat
  spinner — owned by `ui/new_benchmark/` in a later phase.
- Defining `PerformanceConfig`, `BenchmarkTask`, `TaskOrigin`, and `Difficulty` — consumed from
  `backend/domain/` (STORY-001).

## Spec inputs

- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#3-outputs` — the per-field value
  table for a synthetic task and the total-count formula.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#61-generation-steps` — the
  validate, sort-axes, cartesian-expand, build-prompt, compose-id, assemble, return steps and
  the fixed nesting order.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#5-postconditions` — the count,
  uniqueness, synthetic-marker, size-label, `task_order`, and determinism postconditions.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#8-error-handling` — the
  empty-axis, out-of-range repeats, unknown-size, and duplicate-value validation errors.
- `11_Services_and_Algorithms/21_PERFORMANCE_TASK_GENERATOR.md#11-test-cases` — PG-01..PG-16.

## Design constraints

- `backend/performance_task_generator/` is Qt-free and asyncio-free; it imports only
  `backend/domain` (`01_MODULE_INVENTORY.md` §4.5). No PySide6, no I/O.
- `generate` is a pure function of `config` alone with no shared mutable state; it is
  re-entrant and deterministic — the same `PerformanceConfig` yields a byte-identical task list
  in the same order on every call.
- The generator is all-or-nothing: it returns the complete tuple or raises a validation error
  before building any task; it never returns a partial set.
- Synthetic tasks carry no `golden_answer` and empty `required_terms`/`pass_criteria`/
  `fail_criteria` so the grading phases short-circuit downstream.
- The size-bucket table, filler passage, output-instruction phrasing, `category`, and `task_id`
  pattern are fixed constants, not settings; `icontract` on `api.py` guards programmer
  invariants only.

## Acceptance criteria

### STORY-034-AC-1

Given a `PerformanceConfig` with `i` input sizes, `o` output sizes, and `r` repeats, when
`generate` runs, then the returned tuple has exactly `i × o × r` tasks, every `task_id` is
unique within the tuple, and `task_order` runs `0 .. n-1` with no gaps and no duplicates.

### STORY-034-AC-2

Given a `PerformanceConfig`, when `generate` runs, then tasks are emitted with the input axis
sorted ascending outermost, the output axis sorted ascending in the middle, and the repeat index
`1..repeats` innermost, so all repeats of one `(input, output)` pair are contiguous.

### STORY-034-AC-3

For every generated synthetic task, `task_origin == TaskOrigin.SYNTHETIC`, `category == "Synthetic Benchmark"`, `golden_answer is None`, `pass_criteria`/`fail_criteria` are empty,
`required_terms` is empty, and `input_size_label`/`output_size_label`/`repeat_index` are all set.

### STORY-034-AC-4

Given the same `PerformanceConfig`, when `generate` is called twice, then the two calls return
identical task lists in identical order, and the three repeats of one `(input, output)` pair
carry byte-identical `question` text.

### STORY-034-AC-5

Given a `PerformanceConfig` whose axis carries a numeric size with no matching bucket, when
`generate` runs, then it raises a validation error naming the offending value and returns no
partial task list.

## Test plan

- STORY-034-AC-1 — unit (table-driven over grid shapes incl. the 5×5×50 maximum), colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_grid_expansion.py`,
  `test_task_count_and_order_sequence`. Covers PG-01, PG-03, PG-10, PG-13.
- STORY-034-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_ordering.py`,
  `test_axes_sorted_and_repeats_contiguous`. Covers PG-02, PG-06, PG-11.
- STORY-034-AC-3 — unit (over every task in a representative grid), colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_synthetic_fields.py`,
  `test_synthetic_markers_and_no_grading_fields`. Covers PG-04, PG-05, PG-09.
- STORY-034-AC-4 — property (Hypothesis over configs) + unit, colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_determinism.py`,
  `test_generate_is_deterministic_and_prompts_identical_per_pair`. Covers PG-07, PG-08, PG-12,
  PG-15, PG-16.
- STORY-034-AC-5 — unit, colocated
  `src/ollama_llm_bench/backend/performance_task_generator/tests/test_validation.py`,
  `test_unknown_size_raises_and_returns_no_partial`. Covers PG-14.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-034.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/performance_task_generator/`.
- [x] An architecture test confirms the module imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-034.
- [x] The module inventory is unchanged.
