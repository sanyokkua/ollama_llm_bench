# Persistence Schema — Cross-Cutting Summary

**Status:** Draft
**Owner:** coder
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `08_Cross_Cutting/08-E_interfaces_contracts.md`, `08_Cross_Cutting/08-M_app_lifecycle.md`

This is a short bridging document. It gives a cross-cutting overview of how Ollama LLM Bench stores its durable state — where the database lives, how connections are configured, what the table set is, how values are stored, how schema versioning works without migrations, and how a crash is recovered — and then points the reader to the single authoritative source. The full, binding SQLite DDL — every `CREATE TABLE`, every `CREATE INDEX`, every foreign key, the seed data, and the exact crash-recovery sweep statements — is in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md`. This summary never duplicates that DDL; where the two ever appear to differ, `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` is correct.

---

## Table of Contents

1. Authoritative source
2. Database file location
3. Connection pragmas
4. Table set
5. Storage convention
6. Schema versioning — additive structural steps; no data migration (DD-53)
7. Crash-recovery sweep
8. Related contracts

---

## 1. Authoritative source

`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` is the single authoritative persistence specification and the binding contract for the persistence module. It carries the complete DDL for all fifteen tables, every index with its rationale, every foreign key and `ON DELETE` policy, the seed data written on first start, and the verbatim crash-recovery SQL. Any implementation question that this summary does not answer is answered there.

The records that map to these tables — every `msgspec.Struct` and every `StrEnum` — are catalogued in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

---

## 2. Database file location

The application keeps all durable state in one SQLite database file in the per-OS application-data folder:

| OS | Database path |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/ollama_llm_bench.db` |
| Linux | `~/.local/share/OllamaLLMBench/ollama_llm_bench.db` |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\ollama_llm_bench.db` |

Write-ahead logging produces two SQLite-managed sidecar files alongside it — `ollama_llm_bench.db-wal` and `ollama_llm_bench.db-shm`. On first start the application creates the file, runs every `CREATE TABLE` statement, writes the single `app_meta` row, and seeds the built-in catalog data. On every later start it opens the existing file, runs the schema-version check, then runs the crash-recovery sweep.

---

## 3. Connection pragmas

Every connection applies the same pragmas immediately after opening, before any statement runs:

```sql
PRAGMA journal_mode = WAL;        -- background pipeline writes while the UI reads
PRAGMA synchronous = NORMAL;      -- safe under WAL; one fsync per checkpoint
PRAGMA busy_timeout = 5000;       -- wait up to 5000 ms for a lock before failing
PRAGMA foreign_keys = ON;         -- enforce foreign keys and ON DELETE CASCADE
PRAGMA temp_store = MEMORY;       -- keep transient B-trees off disk
PRAGMA wal_autocheckpoint = 1000; -- PASSIVE auto-checkpoint ~every 4 MB of WAL (SPEC-039)
PRAGMA journal_size_limit = 67108864; -- write connection only: cap -wal at 64 MB (SPEC-039)
```

`journal_mode = WAL` lets the benchmark pipeline write results from the dispatcher thread (through the single DB writer — one write connection guarded by one lock, DD-41) while the UI reads runs and results on read-only connections, with no writer-blocks-reader contention. `journal_mode` is persistent on the file once set; the others are connection-scoped and re-applied on every connection (`journal_size_limit` on the write connection only). Unbounded `-wal` growth during a long run is prevented by short-lived reader transactions plus a writer `wal_checkpoint(TRUNCATE)` at run end and clean shutdown (SPEC-039). The full rationale for each pragma is in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §2 / §2.1.

---

## 4. Table set

The schema has fifteen tables in two groups. Each is described in one line here; the full DDL for each is in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §4–§5.

**Catalog tables (six)** — configuration independent of any run; a run never writes to them:

| Table | Purpose |
|---|---|
| `app_meta` | Single-row schema marker: schema version and database creation time. |
| `providers` | One row per configured LLM provider. |
| `provider_models` | The hand-entered model list for providers without model discovery. |
| (embedding selection) | The selected embedding `(provider, model)` used by the cosine and semantic-keyword checks is **not a dedicated table** (D-R-13): it is stored as `app_settings` keys (`embedding.selected_provider_name`, `embedding.selected_model_name`), read live outside a run, and **frozen into the run snapshot at run start** (header name pair + `EMBEDDING`-role model row); a running or resumed pipeline uses only the frozen pair. The per-provider embedding-model *list* is dynamic (discovered from the provider) and is never persisted. |
| `app_settings` | The user-saved settings layer; one row per key changed from its built-in default. |
| `model_capabilities` | Per-`(provider, model, capability)` cache of probed model capabilities. |

**Run-data tables (nine)** — the immutable record of each benchmark run; all cascade-delete with their run:

| Table | Purpose |
|---|---|
| `benchmark_runs` | One row per run: mode, persisted status, counters, timestamps, run analysis. |
| `benchmark_run_models` | The run's frozen model snapshot — test, judge, and embedding model rows. |
| `benchmark_run_providers` | The run's frozen provider snapshot; the pipeline connects through it. |
| `benchmark_run_settings` | The run's frozen per-run-overridable settings snapshot. |
| `benchmark_tasks` | The run's frozen task snapshot, file-loaded or synthetic. |
| `benchmark_task_terms` | A task's keyword lists, one row per term. |
| `benchmark_results` | One row per `(task, provider, model)`: lifecycle status, binary verdict, metrics. |
| `benchmark_result_terms` | The keyword phase's per-term outcomes for one result. |
| `benchmark_result_attempts` | One row per inference attempt for a result, with its adaptive-timeout budget. |

A run mode (`SYNTHETIC`, `TASKS`, `GRADED`) is stored in `benchmark_runs.run_mode`. A result's binary `Verdict` (`PASS` / `FAIL`) is stored in `benchmark_results.verdict`, separate from its eleven-value lifecycle `status` (the authoritative member list is `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.3 — five pipeline-position states, six terminal, per DD-34). The judge produces no numeric score; the only numeric quality value, the **Cosine Score**, is stored in `benchmark_results.cosine_similarity`.

**Per-aggregate ownership of the table set.** The fifteen tables are owned by the six per-aggregate persistence Protocols defined in `08_Cross_Cutting/08-E_interfaces_contracts.md` §7:

| Persistence Protocol | Tables it owns |
|---|---|
| `RunsStore` (§7.1) | `benchmark_runs`, `benchmark_run_models`, `benchmark_run_providers`, `benchmark_run_settings` |
| `TasksStore` (§7.2) | `benchmark_tasks`, `benchmark_task_terms` |
| `ResultsStore` (§7.3) | `benchmark_results`, `benchmark_result_terms`, `benchmark_result_attempts` |
| `ProvidersStore` (§7.4) | `providers`, `provider_models` |
| `ModelCapabilitiesStore` (§7.5) | `model_capabilities` |
| `AppSettingsStore` (§7.6) | `app_settings`, `app_meta` |

The boundary is hard: no store reaches across into another store's tables. Cross-aggregate reads (for example a Result widget controller composing run, results, and tasks) go through the consuming layer combining several stores, never through one store stepping outside its aggregate.

---

## 5. Storage convention

The schema is fully relational and stores **no JSON blob columns**. Every structured or multi-valued field is decomposed into a dedicated child table with one row per element — a run's model, provider, and settings snapshots; a task's keyword terms; a result's per-term outcomes and inference attempts. Every value is therefore an individually addressable, typed, queryable column.

Value conventions: integers, reals, and text store directly; a `bool` is an `INTEGER` constrained to `0` or `1`; a `StrEnum` stores its member-value string in a `TEXT` column with a `CHECK` constraint listing the allowed values; a timestamp is an ISO-8601 UTC `TEXT` string; an unset optional value is SQL `NULL`; an auto-incrementing key is an `INTEGER PRIMARY KEY`. The mapping table is in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §3.

---

## 6. Schema versioning — additive structural steps; no data migration (DD-53)

The application performs **no data migrations or conversions, ever** (DD-53); within a major lineage the schema evolves only through purely structural additive steps applied at startup. The binary embeds one **expected schema version**; `app_meta.schema_version` records the version the file was created with, and `benchmark_runs.schema_version` records the version that wrote each run, for diagnostic traceability.

On every startup, after opening the database, the application compares `app_meta.schema_version` to the expected version:

- **Match** — startup continues with the crash-recovery sweep.
- **Older, same major lineage** — the ordered additive structural steps are applied (DD-53; existing rows never touched), then startup continues.
- **Newer than expected, or cross-major** — startup halts with a hard, clearly reported error. The application does not alter the database and does not show the main window.
- **File absent** — the application creates the database, runs every `CREATE TABLE` and `CREATE INDEX`, writes the `app_meta` row at the expected version, and seeds the catalog data.

Any future structural change is a new schema version and a new database file; existing data is not carried forward. The full rule is in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §8.

---

## 7. Crash-recovery sweep

If the application terminates while a run is executing, the persisted state is already self-consistent at the run level: the run's `status` is `incomplete`, because `incomplete` is exactly the status of a created or in-progress run and the in-memory `RUNNING` and `PAUSED` states are never written to the database. An interrupted run is therefore correctly `incomplete` and is offered for resume by the Resume widget; nothing needs to be swept on `benchmark_runs`.

Recovery is required only at the **result level**. A `benchmark_results` row can be left in a non-terminal in-flight status (`running_inference`, `awaiting_keyword_check`, `awaiting_cosine_check`, or `awaiting_judge_check`) when the application died mid-task. The crash-recovery sweep — run once at startup immediately after the schema-version check passes, and again whenever a run is resumed — clears such a row's child rows and resets the row to `pending`, clearing its in-flight columns, all inside a single transaction. After the sweep, every result is in a terminal status or in `pending`; no result remains in flight. Rows already in a terminal status, including the retryable terminal-failure states, are left untouched — the user retries those explicitly. The exact SQL statements are in `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §9.

The `ResultsStore` exposes this sweep as `recover_in_flight_results()`; its contract is in `08_Cross_Cutting/08-E_interfaces_contracts.md` §7.3, and its place in the startup sequence is in `08_Cross_Cutting/08-M_app_lifecycle.md`.

---

## 8. Related contracts

| Concern | Where specified |
|---|---|
| Full SQLite DDL, indexes, foreign keys, seed data, sweep SQL | `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` |
| The records and enums mapped to the tables | `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` |
| The six per-aggregate persistence Protocols (`RunsStore`, `TasksStore`, `ResultsStore`, `ProvidersStore`, `ModelCapabilitiesStore`, `AppSettingsStore`) | `08_Cross_Cutting/08-E_interfaces_contracts.md` §7 |
| Where the sweep runs in the startup sequence | `08_Cross_Cutting/08-M_app_lifecycle.md` |
