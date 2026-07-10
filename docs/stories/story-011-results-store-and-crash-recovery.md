---
id: STORY-011
title: Provide the ResultsStore with the resume, retry, and crash-recovery sweeps
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#73-resultsstore
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#57-benchmark_results
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#9-crash-recovery-sweep
  - 12_Quality_and_NFRs/04_ERROR_RECOVERY.md#4-the-result-row-recovery-sweep
  - 12_Quality_and_NFRs/06_DATA_INTEGRITY.md#6-idempotency-per-operation
  - 08_Cross_Cutting/08-I_edge_cases.md#ec-persist-4--a-retryable-failure-row-after-crash-recovery
modules:
  - backend/persistence/results/
acceptance_criteria:
  - STORY-011-AC-1
  - STORY-011-AC-2
  - STORY-011-AC-3
  - STORY-011-AC-4
  - STORY-011-AC-5
  - STORY-011-AC-6
edge_cases:
  - EC-PERSIST-4
depends_on:
  - STORY-008
  - STORY-009
  - STORY-010
owner: coder
estimate: M
---

# STORY-011 — Provide the ResultsStore with the resume, retry, and crash-recovery sweeps

## Goal

Give the application the durable gateway for per-task results: create the initial result rows,
apply partial updates that replace a result's term and attempt child rows wholesale, read a
run's results assembled with their children, select the resumable rows, reset rows for a full
re-run or a stage-preserving retry, and run the idempotent crash-recovery sweep that resets
every mid-flight row to `PENDING` while leaving terminal and retryable-failure rows untouched.

## In scope

- The `ResultsStore` Protocol and its concrete implementation: `create_results`,
  `update_result`, `list_results`, `list_resumable_results`, `reset_results`,
  `reset_results_for_retry`, and `recover_in_flight_results` per `08-E` §7.3.
- `update_result` applying a `ResultPatch` and, when the patch carries `terms` or `attempts`,
  replacing that result's `benchmark_result_terms` / `benchmark_result_attempts` child rows
  wholesale, in one transaction (identity columns immutable).
- `list_resumable_results` returning `PENDING` rows plus retryable terminal-failure rows;
  `reset_results` full whole-task reset to `PENDING`; `reset_results_for_retry` stage-preserving
  retry (DD-66) — judge-only reset to `AWAITING_JUDGE_CHECK` for `FAILED_JUDGE_TIMEOUT` /
  response-bearing `ERRORED`, full `PENDING` reset otherwise.
- `recover_in_flight_results` running the §9 two-step sweep in one transaction: clear child rows
  and reset every row in a non-terminal in-flight status to `PENDING`, clearing its in-flight
  columns; leave terminal and retryable-failure rows untouched; return the count reset;
  idempotent across repeated calls.
- `PersistenceError` on every storage failure.

## Out of scope

- The `benchmark_runs`, run-snapshot, and task tables — owned by STORY-009 / STORY-010; a result
  row's `(run_id, task_id)` FK parents must exist first.
- The run header's `completed_tasks` recompute and the run-status reconciliation after the sweep
  (`04_ERROR_RECOVERY.md` §4) — the caller re-derives the header via `RunsStore.update_run_status`
  in a later app-lifecycle phase; this story's sweep touches only `benchmark_results*`.
- Orphan-run handling and where in the startup sequence the sweep is invoked — a later
  composition-root / app-lifecycle concern; this story exposes `recover_in_flight_results` for
  that caller.
- The single-writer connection and lock this store writes through — owned by STORY-008.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#73-resultsstore` — the seven method contracts,
  the wholesale child-row replacement rule, the resumable-set definition, the two reset
  semantics, and the sweep contract.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#57-benchmark_results` — the eleven-value `status`
  domain, the `verdict`-null-until-completed rule, the `provider_id`/`provider_name` snapshot
  rule, and the child-table FKs.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#9-crash-recovery-sweep` — the verbatim two-step
  sweep SQL and the exact set of four non-terminal in-flight statuses it resets.
- `12_Quality_and_NFRs/04_ERROR_RECOVERY.md#4-the-result-row-recovery-sweep` — the
  reset-mid-flight / leave-terminal / leave-retryable-failure rules the sweep must honour.
- `12_Quality_and_NFRs/06_DATA_INTEGRITY.md#6-idempotency-per-operation` — the sweep's and
  resume's idempotency requirement (running twice equals running once).
- `08_Cross_Cutting/08-I_edge_cases.md#ec-persist-4--a-retryable-failure-row-after-crash-recovery`
  — the sweep leaves a retryable-failure row in its failure status and never converts it to
  `PENDING`.

## Design constraints

- `backend/persistence/results/` is Qt-free and asyncio-free; it imports only `backend/domain`,
  `backend/infra`, `backend/errors`, `msgspec`, and `sqlite3` (`01_MODULE_INVENTORY.md`
  row 154). It does not import any other `backend/persistence/*` sibling.
- All writes go through the injected single-writer connection + lock (STORY-008, DD-41) with
  `BEGIN IMMEDIATE`, synchronously on the calling thread; reads use the injected read-only
  connection factory.
- **Ambiguity resolution: this store *implements* `recover_in_flight_results`; it does not
  *invoke* it.** The startup/resume caller (a later composition-root / app-lifecycle phase)
  decides when to call it — once at startup after the schema-version check passes and again on
  every resume. This story delivers only the idempotent sweep method.
- The four non-terminal in-flight `ResultStatus` values the sweep resets are exactly
  `RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`, `AWAITING_COSINE_CHECK`, and
  `AWAITING_JUDGE_CHECK`; `PENDING` and the six terminal statuses (`COMPLETED`,
  `FAILED_INFERENCE`, `FAILED_PROVIDER`, `FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`)
  are never reset by the sweep.
- `list_results` may materialise tens of MB for a large run; the read is a single bounded read
  on a read-only connection (the caller runs it off the GUI thread) — this store never holds a
  read transaction open across UI idle.

## Acceptance criteria

### STORY-011-AC-1

Given a tuple of initial `BenchmarkResult` rows for a run, when `create_results` is called, then
all rows are inserted in one transaction, and `list_results` returns every result of the run,
each assembled with its `benchmark_result_terms` and `benchmark_result_attempts` child rows.

### STORY-011-AC-2

Given a persisted result, when `update_result` applies a `ResultPatch` carrying `terms` and
`attempts`, then that result's existing term and attempt child rows are replaced wholesale in
one transaction and its identity columns are unchanged.

### STORY-011-AC-3

The crash-recovery sweep resets each persisted result row according to its status:

| Status before sweep      | Action                                                               |
| ------------------------ | -------------------------------------------------------------------- |
| `PENDING`                | left unchanged                                                       |
| `RUNNING_INFERENCE`      | child rows cleared; row reset to `PENDING`, in-flight columns nulled |
| `AWAITING_KEYWORD_CHECK` | child rows cleared; row reset to `PENDING`, in-flight columns nulled |
| `AWAITING_COSINE_CHECK`  | child rows cleared; row reset to `PENDING`, in-flight columns nulled |
| `AWAITING_JUDGE_CHECK`   | child rows cleared; row reset to `PENDING`, in-flight columns nulled |
| `COMPLETED`              | left untouched                                                       |
| `FAILED_INFERENCE`       | left untouched                                                       |
| `FAILED_PROVIDER`        | left untouched                                                       |
| `FAILED_TIMEOUT`         | left untouched                                                       |
| `FAILED_JUDGE_TIMEOUT`   | left untouched                                                       |
| `ERRORED`                | left untouched                                                       |

### STORY-011-AC-4

Given a database containing result rows across every status, when `recover_in_flight_results` is
called twice in succession, then the second call resets zero additional rows and the database
state after the second call is identical to the state after the first — the sweep is idempotent.

### STORY-011-AC-5

Given a run's persisted results, `list_resumable_results` returns exactly the `PENDING` rows and
the rows in a retryable terminal-failure status (`FAILED_INFERENCE`, `FAILED_PROVIDER`,
`FAILED_TIMEOUT`, `FAILED_JUDGE_TIMEOUT`, `ERRORED`), and excludes every `COMPLETED` row and
every mid-flight row.

### STORY-011-AC-6

Given rows in retryable statuses, `reset_results` resets each named row fully to `PENDING`
(clearing verdicts, metrics, responses, and child rows), while `reset_results_for_retry` resets
a `FAILED_JUDGE_TIMEOUT` row (or an `ERRORED` row with a non-null `sanitized_response`) to
`AWAITING_JUDGE_CHECK` preserving the inference response, timing, keyword, and cosine outcomes,
and resets every other retryable status fully to `PENDING`.

## Test plan

- STORY-011-AC-1 — integration (real `tmp_path` SQLite),
  `tests/integration/persistence/test_results_store.py`,
  `test_create_and_list_results_with_child_rows`.
- STORY-011-AC-2 — integration, same file,
  `test_update_result_replaces_term_and_attempt_children_wholesale`.
- STORY-011-AC-3 — table-driven integration (one parametrized case per `ResultStatus` value),
  `tests/integration/persistence/test_crash_recovery_sweep.py`,
  `test_sweep_resets_only_the_four_mid_flight_statuses`.
- STORY-011-AC-4 — integration, same file, `test_recover_in_flight_results_is_idempotent`.
- STORY-011-AC-5 — integration,
  `tests/integration/persistence/test_results_store.py`,
  `test_list_resumable_returns_pending_and_retryable_failures`. Covers EC-PERSIST-4 (the sweep
  leaves the retryable-failure rows for the user to resume/retry).
- STORY-011-AC-6 — integration, same file,
  `test_reset_full_vs_stage_preserving_retry`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-011.
- [ ] EC-PERSIST-4 has a passing test.
- [ ] Integration tests run against a real `tmp_path` SQLite database — never an in-memory
  database.
- [ ] The crash-recovery sweep has a dedicated test for each of the four non-terminal
  `ResultStatus` values (`RUNNING_INFERENCE`, `AWAITING_KEYWORD_CHECK`,
  `AWAITING_COSINE_CHECK`, `AWAITING_JUDGE_CHECK`) via the STORY-011-AC-3 parametrization.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/persistence/results/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
