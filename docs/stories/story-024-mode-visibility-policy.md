---
id: STORY-024
title: Provide the data-driven mode-visibility policy over the RunMode x ConfigSection table
status: done
spec_clauses:
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#3-outputs
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#61-the-section-vocabulary
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#62-the-policy-table
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#63-the-lookup
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#8-error-handling
  - 11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#9-threading-and-concurrency
  - 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#3-master-service-table
modules:
  - backend/mode_visibility/
acceptance_criteria:
  - STORY-024-AC-1
  - STORY-024-AC-2
  - STORY-024-AC-3
  - STORY-024-AC-4
depends_on:
  - STORY-001
owner: coder
estimate: M
---

# STORY-024 — Provide the data-driven mode-visibility policy over the RunMode x ConfigSection table

## Goal

Give the New Benchmark widget one declarative lookup that answers, for each run mode and each
configuration section, whether that section is `VISIBLE`, `VISIBLE_REQUIRED`, `VISIBLE_FORCED`,
or `HIDDEN` — so the widget contains no hard-coded per-mode `if` branches and every per-mode
visibility rule lives, and is reviewed and tested, in one place. The lookup is a pure, total
function over the full `RunMode × ConfigSection` product: there is no `(mode, section)` pair for
which the answer is undefined.

## In scope

- The `ConfigSection` closed enum (the ten members of §6.1) and the `Visibility` closed enum (the
  four members of §3), owned by this module — neither is a persisted-enum-catalog member, so this
  module defines them.
- The `POLICY_TABLE` module-level constant: the exhaustive `3 × 10 = 30`-cell table of §6.2,
  built once at import time.
- The pure lookup functions on the module's public surface (`backend.mode_visibility.visibility`):
  `is_visible(mode, section) -> Visibility` (§6.3) and `visible_sections(mode) -> tuple[...]`
  (the sections whose cell is not `HIDDEN`, in section order).
- The startup self-check (§9) that iterates the full `RunMode × ConfigSection` product and
  asserts every cell resolves, failing fast if a maintenance gap ever leaves a cell undefined.
- The programmer-error behaviour of §8: `is_visible` called with a value outside `ConfigSection`
  raises rather than inventing a `HIDDEN` default.

## Out of scope

- The New Benchmark widget's `apply_mode` loop, the required/forced/hidden widget decoration, and
  the Start-precondition recomputation (§6.3) — owned by `ui/new_benchmark/` in a later phase;
  this story supplies the table the widget consults.
- The per-mode initial default of `feature.judge_run_analysis_enabled` (OFF in `SYNTHETIC`/`TASKS`,
  ON in `GRADED`) — supplied by the New Benchmark widget when it constructs the toggle, not
  encoded in the policy (§7); the policy only decides the toggle is shown in every mode.
- The judge-picker required-ness derived from the toggle state plus `eval.phase_judge_enabled` —
  a Start-precondition rule owned by the widget, not by the policy table.
- Readiness / run-state gating (disabling Start, disabled-while-running) — separate concerns in
  `09_READINESS_PROBE.md` and `08-H_app_modes.md`, not this policy.

## Spec inputs

- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#3-outputs` — the four `Visibility`
  values and the shown-vs-hidden distinction.
- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#61-the-section-vocabulary` — the ten
  `ConfigSection` members this module defines.
- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#62-the-policy-table` — the exact
  30-cell table every cell of the table-driven test must match.
- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#63-the-lookup` — the `is_visible`
  lookup and the purity requirement.
- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#8-error-handling` — the raise-not-
  default rule for an unknown section and the missing-cell self-check.
- `11_Services_and_Algorithms/10_MODE_VISIBILITY_POLICY.md#9-threading-and-concurrency` — the
  pure, immutable, stateless, import-time-built contract and the startup self-check.
- `11_Services_and_Algorithms/01_SERVICE_INVENTORY.md#3-master-service-table` — the
  `backend.mode_visibility.visibility` module path and its `is_visible` / `visible_sections`
  public surface.

## Design constraints

- `backend/mode_visibility/` is Qt-free and asyncio-free; it imports only `backend/domain`
  (`RunMode`) (`01_MODULE_INVENTORY.md` §4.4). No PySide6, no settings read, no I/O.
- `RunMode` is consumed from `backend/domain/` (STORY-001). `ConfigSection` and `Visibility` are
  defined in this module; they are `StrEnum`s and are not added to the persisted-enum catalog
  (they are structural-UI-layout types, not user-tunable or persisted values).
- The policy is a pure function group, not a Protocol and not faked — used directly in tests.
- The `POLICY_TABLE` is an immutable module-level constant; the lookup touches no shared mutable
  state and needs no locking (§9).
- `icontract` on any `api.py` symbol guards programmer invariants only.

## Acceptance criteria

### STORY-024-AC-1

For every `(mode, section)` in the full `RunMode × ConfigSection` Cartesian product,
`is_visible(mode, section)` returns a defined `Visibility` value — the function is total over all
`3 × 10 = 30` cells, asserted by an architecture-style totality test that enumerates the product.

### STORY-024-AC-2

Each `(mode, section)` cell resolves to exactly the `Visibility` value in the §6.2 table:

| `ConfigSection`        | `SYNTHETIC`        | `TASKS`            | `GRADED`           |
| ---------------------- | ------------------ | ------------------ | ------------------ |
| `RUN_MODE_SELECTOR`    | `VISIBLE`          | `VISIBLE`          | `VISIBLE`          |
| `TEST_MODELS_PICKER`   | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` |
| `INPUT_SIZES`          | `VISIBLE_REQUIRED` | `HIDDEN`           | `HIDDEN`           |
| `OUTPUT_SIZES`         | `VISIBLE_REQUIRED` | `HIDDEN`           | `HIDDEN`           |
| `REPEATS`              | `VISIBLE_REQUIRED` | `HIDDEN`           | `HIDDEN`           |
| `TASK_FILES`           | `HIDDEN`           | `VISIBLE_REQUIRED` | `VISIBLE_REQUIRED` |
| `JUDGE_MODEL_PICKER`   | `VISIBLE`          | `VISIBLE`          | `VISIBLE`          |
| `EMBEDDING_MODEL_INFO` | `HIDDEN`           | `HIDDEN`           | `VISIBLE_REQUIRED` |
| `RUN_ANALYSIS_TOGGLE`  | `VISIBLE`          | `VISIBLE`          | `VISIBLE`          |
| `ADVANCED_OPTIONS`     | `VISIBLE`          | `VISIBLE`          | `VISIBLE`          |

### STORY-024-AC-3

For every `RunMode`, `visible_sections(mode)` returns exactly the set of `ConfigSection` members
whose §6.2 cell for that mode is not `HIDDEN`, and no `HIDDEN`-celled section, in a stable order.

### STORY-024-AC-4

Given `is_visible` is called with a value that is not a `ConfigSection` member (or the table has a
cell removed), when the lookup or the startup self-check runs, then it raises a programmer error
and never returns a silent `HIDDEN` default.

## Test plan

- STORY-024-AC-1 — architecture/property (enumerates `RunMode × ConfigSection`), colocated
  `src/ollama_llm_bench/backend/mode_visibility/tests/test_table_totality.py`,
  `test_policy_table_is_total_over_the_product`. Covers T-1.
- STORY-024-AC-2 — unit (table-driven, one case per cell — 30 parametrised cases), colocated
  `src/ollama_llm_bench/backend/mode_visibility/tests/test_policy_cells.py`,
  `test_each_cell_matches_the_spec_table`. Covers T-2..T-8.
- STORY-024-AC-3 — unit, colocated
  `src/ollama_llm_bench/backend/mode_visibility/tests/test_visible_sections.py`,
  `test_visible_sections_are_the_non_hidden_cells`.
- STORY-024-AC-4 — unit, colocated
  `src/ollama_llm_bench/backend/mode_visibility/tests/test_error_handling.py`,
  `test_unknown_section_raises_and_self_check_catches_missing_cell`. Covers T-13/T-14.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-024.
- [x] An architecture-style test asserts the policy table is total — every one of the 30
  `RunMode × ConfigSection` cells is defined (STORY-024-AC-1).
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/mode_visibility/`.
- [x] An architecture test confirms `backend/mode_visibility/` imports no Qt and no `asyncio`.
- [x] The traceability record validates with no orphan clause and no orphan test for STORY-024.
- [x] The module inventory is unchanged.
