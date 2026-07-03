---
name: sqlite-persistence-conventions
description: Use when touching any backend/persistence/* store or the SQLite schema.
---

# SQLite Persistence Conventions

Sources of truth:
- `docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` — the full DDL, pragmas, indexes, FK
  policy, schema-versioning rule, and crash-recovery sweep SQL.
- `docs/v3_specification/08_Cross_Cutting/08-O_persistence_schema.md` — the cross-cutting summary, the
  per-aggregate Store ownership table, and how this layer connects to the rest of the app.

## Single-writer discipline (DD-41)

There is **exactly one write connection** for the whole application, guarded by **one
`threading.Lock`** — together these are "the single DB writer." Every store write:

1. Acquires the lock.
2. Runs its transaction with `BEGIN IMMEDIATE` — claiming SQLite's write lock up front, so a transaction
   never fails a mid-flight lock upgrade.
3. Executes **synchronously on the calling thread**.
4. Commits and releases.

A write is durably committed the instant the store call returns. **There is no write queue and no
back-pressure.** Do not introduce a background writer thread, an async write queue, or batching — that
design was explicitly superseded (see ADR history if one exists) in favor of the simpler synchronous model.

Write affinity during a run (DD-38): run-domain writes (result rows, the run header) are issued only by the
dispatcher thread; worker units never write directly. Outside a run, the GUI thread issues small fast
writes (a settings save, a rename) and a worker unit (e.g. a configuration import) writes through the same
lock. `busy_timeout` remains as defence in depth, but with a single write connection, writer-vs-writer
`SQLITE_BUSY` cannot occur at the application level.

Read-only connections never block, and are never blocked by, the writer under WAL. Reads use short-lived
read transactions — each query or aggregation snapshot opens, reads, and closes its own read transaction;
no read transaction is held open across UI idle or for the span of a run. This is the guard against
unbounded `-wal` growth.

## Connection pragmas (verbatim)

Apply these immediately after opening every connection, before any statement runs:

```sql
PRAGMA journal_mode = WAL;        -- write-ahead logging: background pipeline writes while the UI reads
PRAGMA synchronous = NORMAL;      -- safe under WAL; one fsync per checkpoint, not per commit
PRAGMA busy_timeout = 5000;       -- wait up to 5000 ms for a lock before raising SQLITE_BUSY
PRAGMA foreign_keys = ON;         -- enforce every declared foreign key and ON DELETE CASCADE
PRAGMA temp_store = MEMORY;       -- keep transient B-trees off disk
PRAGMA wal_autocheckpoint = 1000; -- PASSIVE auto-checkpoint every ~1000 WAL pages (~4 MB); the default, set explicitly
PRAGMA journal_size_limit = 67108864; -- WRITE CONNECTION ONLY: truncate the -wal back to 64 MB after a checkpoint
```

`journal_mode` is persistent once set on the file. The other pragmas are connection-scoped and must be
re-applied on every connection — **except `journal_size_limit`, which is applied only on the single write
connection** (it governs how the writer truncates the shared `-wal` file; applying it to a read connection
would be a no-op at best and a source of confusion at worst).

The single writer additionally issues `PRAGMA wal_checkpoint(TRUNCATE)` at **run end** and at **clean
shutdown**, hard-reclaiming the WAL back to empty at natural quiescent points.

## The fully-relational rule: no JSON blob columns, anywhere

The schema stores **no JSON blob columns**. Every structured or multi-valued field gets its own dedicated
child table, one row per element:

| Multi-valued field | Child table |
|---|---|
| A run's model snapshot | `benchmark_run_models` |
| A run's provider snapshot | `benchmark_run_providers` |
| A run's settings snapshot | `benchmark_run_settings` |
| A task's keyword lists | `benchmark_task_terms` |
| A result's per-term keyword outcomes | `benchmark_result_terms` |
| A result's inference attempt history | `benchmark_result_attempts` |

Consequently every value is an individually addressable, typed, queryable column — there is no opaque
structure anywhere in the schema. If you find yourself reaching for a `TEXT` column to hold a serialized
JSON list or dict, stop: design a child table instead, even for what looks like a "small" structure.

Type conventions: `int`→`INTEGER`, `float`→`REAL`, `str`→`TEXT`, `bool`→`INTEGER` with
`CHECK (col IN (0,1))`, a `StrEnum`→`TEXT` with a `CHECK` enumerating allowed values, a timestamp→ISO-8601
UTC `TEXT`, an optional value→a nullable column with SQL `NULL`, an auto key→`INTEGER PRIMARY KEY`.

## The six persistence Store Protocols — and the hard boundary between them

Fifteen tables are owned by exactly six per-aggregate persistence Protocols:

| Persistence Protocol | Tables it owns |
|---|---|
| `RunsStore` | `benchmark_runs`, `benchmark_run_models`, `benchmark_run_providers`, `benchmark_run_settings` |
| `TasksStore` | `benchmark_tasks`, `benchmark_task_terms` |
| `ResultsStore` | `benchmark_results`, `benchmark_result_terms`, `benchmark_result_attempts` |
| `ProvidersStore` | `providers`, `provider_models` |
| `ModelCapabilitiesStore` | `model_capabilities` |
| `AppSettingsStore` | `app_settings`, `app_meta` |

**The boundary is hard: no store reaches across into another store's tables.** `ResultsStore` never issues
a query against `benchmark_tasks`; `RunsStore` never touches `providers`. When a feature genuinely needs
data from two aggregates — for example a Result widget controller composing run, results, and tasks — that
composition happens in the **consuming layer**, calling two or more stores and combining their results in
application code. It never happens by having one store's implementation step outside its own aggregate's
tables. This is a structural rule an architecture test enforces; do not special-case it for "just one
convenient join."

## The no-migration rule (DD-53)

The application has **no migration framework** and performs **no backward-compatibility data upgrade,
ever**, within a major schema lineage:

- The binary embeds a single integer constant: the expected schema version.
- On startup, the app compares `app_meta.schema_version` to the expected version.
- **Match** → continue normally (crash-recovery sweep next).
- **Stored version lower, same major lineage** → apply the ordered **additive structural steps** from the
  stored version up to the expected version. Each step is exactly one of three permitted kinds, run as one
  idempotent, single-transaction statement:
  - `ALTER TABLE ... ADD COLUMN ...` — nullable or with a `DEFAULT`.
  - `CREATE TABLE ...` (a wholly new table).
  - `CREATE INDEX ...` (a wholly new index).
  **No step is ever a data migration or conversion** — no `UPDATE`, no backfill, no transformation, no
  rewriting of existing rows. Existing rows simply acquire the new column's `NULL`/default. A failure
  mid-step leaves prior committed steps applied and halts with a hard error naming the failed step.
- **Stored version newer than expected, or from a different major lineage** → **hard startup error.** The
  application aborts launch, does not alter the database, does not show the main window, and reports the
  stored version, the expected version, and that the database is incompatible with this build.
- **File absent** → create fresh: every `CREATE TABLE`/`CREATE INDEX`, the single `app_meta` row at the
  expected version, and the seed catalog data.

Never write an `UPDATE`-based migration "just this once," even for a seemingly trivial data fix — that is
precisely the category of change this rule forbids. Any non-additive structural change is a new major
schema lineage and a fresh database file; existing data does not carry forward across majors.

## The crash-recovery sweep pattern

If the application terminates while a run is executing, the run-level state is already self-consistent:
`benchmark_runs.status` is `incomplete` (the in-memory `RUNNING`/`PAUSED` states are never written to the
database), so an interrupted run is correctly `incomplete` and resumable — there is nothing to sweep at the
run level.

Recovery is required only at the **result level**. The sweep runs **once at startup** (immediately after
the schema-version check passes) and **again on every resume**, inside a single transaction:

1. **Clear child rows** of every `benchmark_results` row left in a non-terminal in-flight status
   (`running_inference`, `awaiting_keyword_check`, `awaiting_cosine_check`, `awaiting_judge_check`) —
   delete its `benchmark_result_terms` and `benchmark_result_attempts` rows.
2. **Reset** each such row to `pending`, clearing every in-flight column (`started_at`, `finished_at`, the
   response fields, the metrics, the verdict fields, `error_kind`/`error_message`, and so on).

After the sweep, every result is either in a terminal status (`completed`, or a terminal-failure status) or
`pending` — none remains in flight. **Rows already in a terminal status, including the retryable
terminal-failure states (`failed_inference`, `failed_provider`, `failed_timeout`, `failed_judge_timeout`,
`errored`), are left completely untouched by the sweep.** The user decides explicitly, via the Resume or
Retry surface, whether to re-run those — that surface separately resets the chosen rows to `pending` and
clears their child rows, using the same shape as the sweep but driven by user selection rather than an
in-flight-status scan.

`ResultsStore` exposes the sweep as `recover_in_flight_results()`.

## Cross-references

- `docs/v3_specification/10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §§2, 6, 7 — full pragma rationale, every index, and the FK/cascade table.
- `docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md` §7 — the six Store Protocol contracts in full.
- `docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` — the broader concurrency model the single-writer rule fits into.
- The `secrets-and-provider-config` skill — the `providers.api_key_raw` column's special handling, layered on top of these general persistence rules.
- The `testing-standard-pyqt` skill — persistence tests always use a `tmp_path` database file, never an in-memory database (except a trivial test that doesn't exercise file behaviour).
