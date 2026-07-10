---
id: STORY-010
title: Provide the TasksStore over the frozen task snapshot and its keyword-term rows
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#72-tasksstore
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#55-benchmark_tasks
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#56-benchmark_task_terms
modules:
  - backend/persistence/tasks/
acceptance_criteria:
  - STORY-010-AC-1
  - STORY-010-AC-2
depends_on:
  - STORY-008
  - STORY-009
owner: coder
estimate: S
---

# STORY-010 — Provide the TasksStore over the frozen task snapshot and its keyword-term rows

## Goal

Give the application the durable gateway for a run's frozen task snapshot: insert every task and
its keyword-term child rows for a run in one transaction at run creation, and read a run's tasks
back in task order. The snapshot makes a run independent of the source task files.

## In scope

- The `TasksStore` Protocol and its concrete implementation: `create_tasks` and `list_tasks`
  per `08-E` §7.2.
- `create_tasks` inserting the `benchmark_tasks` rows and their `benchmark_task_terms` child
  rows (one row per exact/semantic/forbidden term) for a run in one transaction.
- `list_tasks` returning a run's frozen tasks in `task_order`, each assembled with its term
  child rows, via `idx_tasks_run` / `idx_task_terms_task`.
- `PersistenceError` on every storage failure.

## Out of scope

- The `benchmark_runs` header and the three run-snapshot tables — owned by STORY-009
  (`RunsStore`); the run must exist (FK parent) before its tasks are written.
- The `benchmark_results*` tables — owned by STORY-011 (`ResultsStore`).
- The single-writer connection and lock this store writes through — owned by STORY-008 and
  injected by `compose.py`.
- Task-file loading, validation, and synthetic-task generation that produce the `BenchmarkTask`
  values — owned by `backend/task_files/` and `backend/performance_task_generator/` in a later
  phase; this store only persists already-built tasks.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#72-tasksstore` — the two method signatures, the
  one-transaction insert guarantee, and the task-order read contract.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#55-benchmark_tasks` — the `benchmark_tasks`
  columns, the composite `(run_id, task_id)` primary key, the `task_origin` CHECK, and the
  cascade FK to `benchmark_runs`.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#56-benchmark_task_terms` — the
  `benchmark_task_terms` columns, the `term_kind` CHECK (`exact`/`semantic`/`forbidden`), the
  composite primary key, and the cascade FK to `benchmark_tasks`; a task with no required terms
  has no rows here.

## Design constraints

- `backend/persistence/tasks/` is Qt-free and asyncio-free; it imports only `backend/domain`,
  `backend/infra`, `backend/errors`, `msgspec`, and `sqlite3` (`01_MODULE_INVENTORY.md`
  row 153). It does not import any other `backend/persistence/*` sibling.
- All writes go through the injected single-writer connection + lock (STORY-008, DD-41) with
  `BEGIN IMMEDIATE`, synchronously on the calling thread; reads use the injected read-only
  connection factory.
- `create_tasks` is one transaction over both tables — a run's tasks and their terms appear
  together or not at all.
- The store persists tasks only for an existing run; the `(run_id, task_id)` FK to
  `benchmark_tasks` and the `run_id` FK to `benchmark_runs` are enforced by
  `PRAGMA foreign_keys = ON` (set by STORY-008's connection manager).

## Acceptance criteria

### STORY-010-AC-1

Given a run and a tuple of `BenchmarkTask` values whose tasks carry exact, semantic, and
forbidden terms, when `create_tasks` is called, then all `benchmark_tasks` rows and all their
`benchmark_task_terms` child rows are written in one transaction, and a task declaring no
required terms produces a task row with no term rows.

### STORY-010-AC-2

Given a run's persisted task snapshot, `list_tasks` returns the tasks in ascending `task_order`,
each assembled with its exact/semantic/forbidden term child rows, and returns an empty tuple for
a run that has no tasks.

## Test plan

- STORY-010-AC-1 — integration (real `tmp_path` SQLite),
  `tests/integration/persistence/test_tasks_store.py`,
  `test_create_tasks_writes_tasks_and_terms_atomically`.
- STORY-010-AC-2 — integration, same file,
  `test_list_tasks_returns_tasks_in_order_with_terms`.

## Definition of done

- [x] Every acceptance criterion has a passing test that names STORY-010.
- [x] Integration tests run against a real `tmp_path` SQLite database — never an in-memory
  database.
- [x] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/persistence/tasks/`.
- [x] The traceability record validates with no orphan clause and no orphan test.
- [x] The module inventory is unchanged.

## Notes

- `just trace` regenerates `traceability.yaml` cleanly for this story: `STORY-010-AC-1` and
  `STORY-010-AC-2` are each mapped to their proving test, and `backend/persistence/tasks/`
  introduces zero orphan clauses/tests of its own.
- `just trace-check` still fails at the repo level, but on the same four pre-existing gaps
  (`EC-PERSIST-6` dangling row; `EC-PROV-1a`/`EC-RUN-1a` uncovered; `EC-PERSIST-4` named by
  STORY-011 with no test yet) already documented as pre-existing by STORY-003 and STORY-005 —
  confirmed present with STORY-010's changes stashed out. STORY-010 itself introduces no new
  gap.
- `just test` — 467 passed, including both of this story's integration tests, independently
  re-run and verified by the tester agent (not just the coder's report).
- `backend/persistence/tasks/` is purely internal backend API — not yet wired into
  `compose.py` and not user-facing — so README.md and docs/architecture/ needed no change
  (confirmed, not assumed, by the docs-writer pass); CHANGELOG.md did warrant an entry and got
  one, under `[Unreleased] / Added`, matching the pattern set by STORY-008/STORY-009.
