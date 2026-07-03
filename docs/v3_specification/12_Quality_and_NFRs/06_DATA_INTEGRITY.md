# Data Integrity

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester, arch
**Last Updated:** 2026-06-06
**Cross-references:** 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 12_Quality_and_NFRs/04_ERROR_RECOVERY.md, 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md, 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md, 08_Cross_Cutting/08-I_edge_cases.md

This document states the data-integrity guarantees of Ollama LLM Bench per write operation: which writes are atomic, which state is eventually consistent, and which operations are idempotent. The application's durable store is a single SQLite database in WAL mode plus a small set of files written with the atomic temp-then-rename pattern. The integrity model is simple by design — one writer, transactional commits, and a recovery sweep that repairs the only indeterminate state — so a developer can reason about every persisted byte without ambiguity.

---

## Table of Contents

1. Integrity vocabulary
2. SQLite WAL transactional guarantees
3. The single-writer discipline
4. Atomicity per write operation
5. Eventual consistency — what lags, and for how long
6. Idempotency per operation
7. File writes outside the database
8. Data-integrity guarantees summary

---

## 1. Integrity vocabulary

Three properties are used throughout this document, with precise meanings:

- **Atomic.** The write either fully happens or does not happen at all. There is no observable intermediate state and no partial write. After a crash, the write is present in full or absent in full.
- **Eventually consistent.** A derived or displayed value may briefly lag the authoritative value, but converges to the authoritative value within a bounded, stated time without any further user action.
- **Idempotent.** Performing the operation twice produces the same persisted state as performing it once. A retry, a duplicate event, or a re-run of recovery is safe.

The authoritative store is the SQLite database. Everything the UI shows is a view of that store; the store, not the view, is the source of truth.

## 2. SQLite WAL transactional guarantees

The database opens in WAL journal mode with `synchronous = NORMAL`, `busy_timeout = 5000`, `foreign_keys = ON`, and `temp_store = MEMORY` (see 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md §2). WAL mode gives the application the following transactional guarantees:

- **A committed transaction is atomic and durable against an application crash.** Once a transaction commits, all of its statements are present; a crash, force-quit, or kill after the commit cannot lose or partially apply it.
- **An interrupted transaction rolls back atomically.** A crash *during* a transaction leaves the database at the previous commit boundary. The `-wal` and `-shm` sidecar files are recovered automatically the next time the database is opened; no partial transaction survives.
- **Readers and the writer do not block each other.** WAL lets the background pipeline write while the UI reads concurrently. A query never sees a half-applied transaction; it sees the most recent committed snapshot.
- **`synchronous = NORMAL` is durable against an application crash but not against an operating-system crash or power loss.** Under WAL, `NORMAL` performs one `fsync` per checkpoint rather than per commit. The last few committed transactions can be lost if the operating system itself crashes or power is cut. This is an accepted trade — it removes a per-commit `fsync` from the pipeline's hot path — and its only consequence is that a run interrupted by a power loss may show one or two fewer completed results than it actually finished; the recovery sweep then re-runs those, so no result is wrong, only re-computed.
- **Power loss can only lose a contiguous suffix of the commit sequence.** WAL frames are written sequentially and recovery replays the valid prefix, so a later transaction never survives a power loss that an earlier one did not. Because the application's writes are fully serialized through the single writer (one connection, one lock — §3), commit order equals program order, which makes the suffix property directly usable for recovery reasoning.
- **Ordering invariant (normative): the run header's terminal write comes last.** The dispatcher persists every result row of a run and only then issues the header write that sets the terminal status (`COMPLETED`/`FAILED`/`STOPPED`). Combined with the suffix property, this guarantees that a surviving terminal header implies every one of its result rows also survived — a terminal run can never have fewer committed terminal rows than its header claims, with **no startup audit of terminal runs needed**. An implementation change that finalised the header before the last row write would silently void this guarantee and is forbidden.
- **Foreign keys and cascade deletes are enforced.** With `foreign_keys = ON`, deleting a run row cascades atomically to all eight descendant tables in one statement; there is never a run with orphaned child rows or a child row with no parent.

## 3. The single-writer discipline

Every write to the database is funnelled through the single-writer discipline, defined concretely (DD-41) as: **exactly one write connection**, owned by the persistence layer, guarded by **one `threading.Lock`** — "the single DB writer". A store write acquires the lock, runs its transaction (`BEGIN IMMEDIATE`, claiming SQLite's write lock up front) **synchronously on the calling thread**, commits, and releases. When the call returns, the data is committed — the durability point and the code line coincide. There is **no write queue and no back-pressure**; writes are serialized one at a time regardless of which thread issued them (this matches EC-PERSIST-3 in 08_Cross_Cutting/08-I_edge_cases.md).

Who writes: during a run, all run-domain writes (result rows, the run header) are issued **only by the dispatcher thread** (DD-38) — worker units return their data and never touch the database. The GUI thread issues only the small fast writes (a settings save, a run rename); a worker unit outside a run (for example a configuration import) writes through the same lock. Readers use separate **read-only connections** and observe WAL snapshots, so readers and the writer never block each other.

Consequences for integrity:

- Two writes never interleave. The pipeline persisting a result row and the UI persisting a settings change are serialised; neither sees the other half-applied.
- Write order is serialized and **causally ordered per caller**: a causally-ordered pair of writes issued by one thread (create the run row, then create its result rows) always applies in that order, because each write completes synchronously before the caller issues the next. (The lock serializes all writers; it does not promise global fairness across unrelated threads, which no integrity guarantee relies on.)
- A reader always observes a committed snapshot, never a write in progress.

The single-writer discipline is a concurrency guarantee detailed in 12_Quality_and_NFRs/05_CONCURRENCY_GUARANTEES.md; it is the mechanism that makes every per-operation guarantee below hold.

## 4. Atomicity per write operation

Every write operation below runs inside one SQLite transaction and is therefore atomic — fully applied or not applied at all.

| Operation | Tables written | Atomic unit | Notes |
|---|---|---|---|
| Create a run | `benchmark_runs` plus its frozen snapshots `benchmark_run_models`, `benchmark_run_providers`, `benchmark_run_settings`, `benchmark_tasks`, `benchmark_task_terms`, and the initial `pending` `benchmark_results` rows | One transaction | The run and its complete frozen context appear together or not at all — a run never exists with a partial snapshot |
| Persist one result | One `benchmark_results` row update plus its `benchmark_result_terms` and `benchmark_result_attempts` child rows | One transaction | A result row and its child rows are consistent at every commit; this is why a pause checkpoint can land safely after a result persist |
| Update a run's status and counters | `benchmark_runs` (status, `completed_tasks`, `total_elapsed_ms`, `finished_at`) | One transaction | Status moves only between the four persisted values |
| Delete a run | `benchmark_runs` row; cascades to all eight descendant tables | One transaction (one statement plus cascade) | Either the whole run and all its data are gone, or none of it is |
| Add a provider | One `providers` row (with a store-generated UUID4 `provider_id`, DD-33) plus its `provider_models` rows | One transaction | The `UNIQUE (name)` constraint enforces global name uniqueness; a duplicate-name insert raises atomically inside the transaction so a half-applied row never persists. The `add(draft) -> ProviderId` returns the generated id only after commit, so the caller never observes an uncommitted id |
| Update a provider | One `providers` row plus its `provider_models` rows | One transaction | `provider_id` is immutable; `name` and the other mutable columns are updated together; `UNIQUE (name)` enforces no-collision atomically |
| Delete a provider | `providers` row; cascades to `provider_models` and `model_capabilities` | One transaction | The frozen `benchmark_run_providers` snapshots, plus the snapshot fields on `benchmark_runs` (`judge_provider_id`/`judge_provider_name`) and `benchmark_results` (`provider_id`/`provider_name`), are deliberately not foreign-keyed and survive, so past runs stay readable and continue to render the historical name |
| Change the embedding selection | The two `embedding.selected_*` keys in `app_settings` | One transaction | Written atomically with other settings via `upsert_settings` |
| Save settings | `app_settings` rows for the changed keys | One transaction | All changed keys commit together |
| Reset to defaults | Delete from `providers`, `provider_models`, `app_settings`; re-seed the three default providers | One transaction | The catalog never exists in a half-reset state |
| Crash-recovery sweep | Clear child rows of mid-flight results; reset those results to `pending` | One transaction | The whole sweep applies atomically; a crash during the sweep simply re-runs it next launch |
| Write `app_meta` and seed catalog (first run) | `app_meta`, the three seed `providers` rows | One transaction | First-run seeding is all-or-nothing |

No operation spans two transactions; there is no multi-step write that could be observed half-done.

## 5. Eventual consistency — what lags, and for how long

The database is always strongly consistent. What is *eventually* consistent is the set of derived and displayed values that the UI computes from the database. These lag the store briefly and converge without user action.

| Value | Authoritative source | Lag | Converges by |
|---|---|---|---|
| The Result Widget's tables and charts during a live run | The `benchmark_results` rows | Up to one debounce interval (a fixed coalescing window, sub-second) | The next debounced refresh tick |
| The on-screen run-log panel | The run's event stream | Up to one frame-drain interval | The next periodic buffer drain |
| Progress counters in the Progress Widget | The pipeline's progress events | Up to one coalescing window | The next coalesced progress update |
| Provider health dots | The most recent readiness probe | Up to the probe interval, plus probe latency | The next completed probe |
| A run's `completed_tasks` counter after a crash | The surviving terminal `benchmark_results` rows | One startup | The recovery sweep recomputes it at the next launch |

Two rules bound this lag:

- **The lag is always toward staleness, never toward wrongness.** A debounced UI shows a slightly older but always self-consistent snapshot; it never shows a value that was never true.
- **Convergence needs no user action.** Every lagging value is refreshed by a timer, a probe, or the recovery sweep. The user never has to manually reload to see the truth.

UI repaint coalescing is required, not optional — it is how the application stays responsive under a high result-completion rate (see EC-PERF-3 in 08_Cross_Cutting/08-I_edge_cases.md). The brief lag is the deliberate cost of that responsiveness.

## 6. Idempotency per operation

Idempotency is what makes retries and recovery safe.

| Operation | Idempotent? | Why it matters |
|---|---|---|
| Crash-recovery sweep | Yes | Running it twice resets the same already-`pending`-or-terminal rows to the same state. A crash during the sweep is recovered by simply running the sweep again. |
| Resume a run | Yes | Resume re-reads the persisted completion set and schedules only not-yet-completed units. Resuming a run that is already complete schedules nothing and changes nothing. |
| Persist one result | Yes, per `(run_id, task_id, provider_id, model_name)` | A result row is keyed by its composite identity. Re-persisting after a retry overwrites the same row; it never creates a duplicate. The child rows are cleared and rewritten, so a retry leaves no stale child data. |
| First-run schema creation and seeding | Yes | The `CREATE TABLE` statements and the directory creation are idempotent; a partially created tree or schema is completed, not rejected. |
| Application-data-directory creation | Yes | A recursive, idempotent make-directory completes a partial tree (see 10_Domain_and_Data/07_FILE_LAYOUT.md §10). |
| Settings save | Yes | Saving the same setting values twice produces the same `app_settings` rows. |
| Run-log and backup cleanup at startup | Yes | A second run of cleanup finds nothing further to prune. |
| Create a run | No — by design | Each create allocates a new `run_id` and is a distinct run. Start is disabled while a run is active so a double-click cannot create two runs (see EC-RUN-1 in 08_Cross_Cutting/08-I_edge_cases.md); creation is guarded at the UI, not made idempotent. |
| Delete a run | Effectively yes | Deleting an already-deleted run is a no-op — the row is already gone. |

The composite-key idempotency of result persistence is the single most important integrity property of the run pipeline: it is what lets a task be retried, a run be resumed, and a recovery sweep reset a row, all without ever producing a duplicate or losing a completed result.

## 7. File writes outside the database

Files written outside the database — log files, exports, settings backups — are not transactional, so they use the atomic temp-then-rename pattern instead:

- Content is written to a temporary file, then renamed into its final path. The rename is atomic on every supported filesystem.
- A file at its final path is therefore always complete: a crash mid-write leaves a stranded temporary file in `<app-data>/temp/`, never a truncated final file.
- The temp folder is emptied at every startup, discarding any stranded temporary file.
- A disk-full condition fails the temporary write before the rename, so the final path is untouched and the failure is surfaced (see EC-FL-9 in 08_Cross_Cutting/08-I_edge_cases.md).

Log appends are the one continuous-write exception: a log file is appended to line by line rather than rewritten. The atomicity unit there is the single line — a crash may lose the last partially written line but never corrupts an earlier record — which is acceptable because a log is an append-only evidence trail, not a transactional store.

## 7a. UNIQUE-on-name invariants and auto-id atomicity (DD-33)

One catalog table carries a `UNIQUE (name)` constraint enforced inside every transaction that mutates it:

- **`providers.name`** — the user-entered display label of a provider. The `ProvidersStore.add(draft) -> ProviderId` path generates a fresh UUID4 for the row's `provider_id` and inserts the row inside one transaction; a duplicate-name attempt raises atomically before commit. The dialog's friendly-error path (a pre-check via `ProvidersStore.get_by_name(name)` that disables Save) is the user-facing layer; the DB constraint is the backstop that guarantees the invariant even if the dialog is bypassed (a race against another importer, a programmer error, an automation script). The `add` method returns the generated `provider_id` only after commit, so a caller never observes an uncommitted id; on the duplicate-name failure path it returns no id at all (the call raises).

**Result → snapshot test-model integrity (SPEC-038).** Every `benchmark_results` row references, via `(run_id, provider_id, model_name)`, a `role = 'test'` row in `benchmark_run_models`. There is no declared foreign key for this (the same `(provider, model)` may appear under two roles in one run — test and judge — so the triple is not unique; see `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §5.7). The invariant is guaranteed at the write source — the run-creation transaction inserts `pending` result rows only for snapshotted test targets — and verified two ways: a data-integrity self-check available at startup/diagnostics, and an architecture test asserting no result row names a `(run_id, provider_id, model_name)` outside the run's `test`-role snapshot. The two model-snapshot singletons (at most one `judge` row, at most one `embedding` row per run) are enforced directly by the partial unique indexes `ux_run_models_one_judge` / `ux_run_models_one_embedding`.

This invariant applies only to the LIVE catalog. The historical snapshot fields (`benchmark_run_providers.name`, `benchmark_runs.judge_provider_name`, `benchmark_runs.embedding_provider_name`, `benchmark_runs.embedding_model_name`, `benchmark_results.provider_name`) carry **no uniqueness constraint** — the snapshot is a point-in-time copy and may legitimately contain a value that has since been renamed in the live catalog (and may even briefly match the renamed value if the user, after the run, deliberately renames a different provider to the same name).

The atomicity rule for the snapshot capture is binding: `BenchmarkRun.judge_provider_id` / `judge_provider_name` are written in the same transaction that inserts the `benchmark_runs` row (`create_run` per the table above); `BenchmarkResult.provider_id` / `provider_name` are written in the same transaction that creates the initial result rows. The pipeline never observes a half-snapshot.

## 8. Data-integrity guarantees summary

| Property | Guarantee |
|---|---|
| Every database write operation | Atomic — one SQLite transaction; fully applied or not at all |
| `providers.name` | Globally unique per the `UNIQUE` constraint; duplicate-name inserts raise atomically; dialog `get_by_name` pre-check is the friendly-error path (DD-33) |
| `provider_id` generation | Generated by the store inside the insert transaction; returned to the caller only after commit |
| A committed transaction | Durable against an application crash, force-quit, or kill |
| An interrupted transaction | Rolls back atomically; the database is consistent at the prior commit |
| Power loss / OS crash | May lose the last few committed transactions; the recovery sweep re-runs the affected tasks; no result is ever wrong, only re-computed |
| Write ordering | Serialized through the one write connection + lock (DD-41); synchronous on the calling thread; causally ordered per caller; no two writes interleave |
| Result persistence | Idempotent per composite key; a retry overwrites, never duplicates |
| Recovery sweep and resume | Idempotent; safe to run twice |
| Run deletion | Atomic cascade to all descendant tables; no orphan rows ever |
| UI-displayed values | Eventually consistent; lag is sub-second and toward staleness only |
| Files outside the database | Atomic temp-then-rename; a final-path file is always complete |
