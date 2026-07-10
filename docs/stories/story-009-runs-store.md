---
id: STORY-009
title: Provide the RunsStore over the run header and its three frozen snapshot tables
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#71-runsstore
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#51-benchmark_runs
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#7-foreign-keys-and-cascade-policy
  - 12_Quality_and_NFRs/06_DATA_INTEGRITY.md#2-sqlite-wal-transactional-guarantees
  - 12_Quality_and_NFRs/06_DATA_INTEGRITY.md#4-atomicity-per-write-operation
modules:
  - backend/persistence/runs/
acceptance_criteria:
  - STORY-009-AC-1
  - STORY-009-AC-2
  - STORY-009-AC-3
depends_on:
  - STORY-008
owner: coder
estimate: S
---

# STORY-009 — Provide the RunsStore over the run header and its three frozen snapshot tables

## Goal

Give the application the durable gateway for a benchmark run's header and its frozen model,
provider, and settings snapshots: create a run and its complete frozen context atomically, read
one run fully assembled, list runs newest-first, apply partial status/counter/timestamp updates,
rename a run, and delete a run with its full cascade. The run's terminal header write is issued
last so a surviving terminal run always has all of its result rows.

## In scope

- The `RunsStore` Protocol and its concrete implementation: `create_run`, `get_run`,
  `list_runs`, `update_run_status`, `rename_run`, `delete_run` per `08-E` §7.1.
- `create_run` inserting the `benchmark_runs` header plus the three frozen snapshot child tables
  (`benchmark_run_models`, `benchmark_run_providers`, `benchmark_run_settings`) in one
  transaction, honouring the two singleton partial unique indexes (`ux_run_models_one_judge`,
  `ux_run_models_one_embedding`) and the header's both-or-neither judge / embedding CHECK
  constraints.
- `list_runs` returning headers newest-first (via `idx_runs_timestamp`); `update_run_status`
  applying a `RunStatusPatch` to the header only (identity columns and snapshot tables
  immutable); `rename_run` setting or clearing `run_name`; `delete_run` cascading to all eight
  descendant tables.
- `PersistenceError` on every storage failure, and on `get_run` for a missing run.

## Out of scope

- The `benchmark_tasks` / `benchmark_task_terms` tables — owned by STORY-010 (`TasksStore`).
- The `benchmark_results*` tables and the initial `pending` result rows written in the
  run-creation transaction — owned by STORY-011 (`ResultsStore`); the dispatcher composes the
  two stores at run-creation time.
- The single-writer connection and lock this store writes through — owned by STORY-008 and
  injected by `compose.py`.
- Orphan-run handling and the completed-task-counter recompute at startup — a later
  app-lifecycle phase.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#71-runsstore` — the six method signatures,
  their one-transaction guarantees, and the immutable-identity/immutable-snapshot rule.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#51-benchmark_runs` — the header columns, the four
  persisted `status` values, the nullable `run_name`, and the judge/embedding snapshot CHECK
  constraints this store must satisfy on write.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#7-foreign-keys-and-cascade-policy` — the
  `ON DELETE CASCADE` behaviour `delete_run` relies on and the deliberate non-foreign-key
  `judge_provider_id` this store must not treat as an FK.
- `12_Quality_and_NFRs/06_DATA_INTEGRITY.md#2-sqlite-wal-transactional-guarantees` — the
  normative ordering invariant that the run header's terminal write comes last.
- `12_Quality_and_NFRs/06_DATA_INTEGRITY.md#4-atomicity-per-write-operation` — the create-a-run,
  update-status, and delete-a-run atomic units this store implements.

## Design constraints

- `backend/persistence/runs/` is Qt-free and asyncio-free; it imports only `backend/domain`,
  `backend/infra`, `backend/errors`, `msgspec`, and `sqlite3` (`01_MODULE_INVENTORY.md`
  row 152). It does not import any other `backend/persistence/*` sibling.
- All writes go through the injected single-writer connection + lock (STORY-008, DD-41) with
  `BEGIN IMMEDIATE`, synchronously on the calling thread; reads use the injected read-only
  connection factory.
- `create_run` is one transaction over four tables — the header and its three snapshot children
  appear together or not at all; a run never exists with a partial snapshot.
- **Ordering invariant (normative, `06_DATA_INTEGRITY.md` §2): the run header's terminal write
  comes last.** `update_run_status` setting a terminal status (`completed`/`failed`/`stopped`)
  is always issued by the caller after every result-row write of that run; this store's
  `update_run_status` writes only the header row so the caller controls ordering, and this
  invariant is asserted by a dedicated test in this story.

## Acceptance criteria

### STORY-009-AC-1

Given a `BenchmarkRun` carrying its model, provider, and settings snapshot collections, when
`create_run` is called, then the `benchmark_runs` header and all three snapshot child tables are
written in one transaction and `get_run` returns the run fully assembled with its snapshot
collections; if the transaction is interrupted, no partial run header or snapshot row survives.

### STORY-009-AC-2

Given a run persisted with result rows already committed, when the caller finalises the run by
issuing `update_run_status` with a terminal status, then the terminal header write is the last
write of that run's write sequence, so a surviving terminal header implies every one of the
run's result rows was committed before it (the run header's terminal write comes last).

### STORY-009-AC-3

Given several persisted runs, `list_runs` returns their headers newest-first by `timestamp`;
`update_run_status` changes only the header's status/counter/timestamp columns and leaves the
snapshot tables and identity columns untouched; `delete_run` removes the run and cascades to all
eight descendant tables, leaving no orphan child row.

## Test plan

- STORY-009-AC-1 — integration (real `tmp_path` SQLite),
  `tests/integration/persistence/test_runs_store.py`,
  `test_create_run_writes_header_and_snapshots_atomically`.
- STORY-009-AC-2 — integration, same file,
  `test_terminal_header_write_comes_last_after_all_result_rows`.
- STORY-009-AC-3 — integration, same file,
  `test_list_newest_first_update_status_and_cascade_delete`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-009.
- [ ] Integration tests run against a real `tmp_path` SQLite database — never an in-memory
  database.
- [ ] The "run header write comes last" durability-ordering invariant has a dedicated passing
  test (STORY-009-AC-2).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/persistence/runs/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
