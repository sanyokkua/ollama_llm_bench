---
id: STORY-008
title: Provide the single-writer connection, schema lifecycle, and AppSettingsStore
status: done
spec_clauses:
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#21-connection-topology-dd-41
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#2-connection-pragmas
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#8-schema-versioning--additive-structural-steps-no-data-migration-dd-53
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#10-seed-data
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#76-appsettingsstore
  - 08_Cross_Cutting/08-O_persistence_schema.md#6-schema-versioning--additive-structural-steps-no-data-migration-dd-53
  - 08_Cross_Cutting/08-I_edge_cases.md#ec-persist-1--database-schema-version-mismatch-at-startup
  - 08_Cross_Cutting/08-I_edge_cases.md#ec-persist-5--database-file-missing-or-unreadable-at-startup
modules:
  - backend/persistence/app_settings/
acceptance_criteria:
  - STORY-008-AC-1
  - STORY-008-AC-2
  - STORY-008-AC-3
  - STORY-008-AC-4
  - STORY-008-AC-5
  - STORY-008-AC-6
edge_cases:
  - EC-PERSIST-1
  - EC-PERSIST-5
depends_on:
  - STORY-001
  - STORY-002
  - STORY-004
adrs:
  - ADR-0004
owner: coder
estimate: M
---

# STORY-008 — Provide the single-writer connection, schema lifecycle, and AppSettingsStore

## Goal

Give the persistence layer its foundation: the one write connection guarded by one lock, the
read-only connection factory, the first-run schema creation, the startup schema-version check
with additive-only structural evolution, the single `app_meta` seed row, and the typed
user-saved settings store. This is the module every other persistence store is constructed over
— it opens and versions the database so the five sibling stores can write through the same
single writer.

## In scope

- The **single-writer connection manager** (DD-41): one write connection guarded by one
  `threading.Lock`, opened once, applying the §2 pragmas (`journal_mode = WAL`,
  `synchronous = NORMAL`, `busy_timeout = 5000`, `foreign_keys = ON`, `temp_store = MEMORY`,
  `wal_autocheckpoint = 1000`, and `journal_size_limit = 67108864` on the write connection
  only); a `BEGIN IMMEDIATE` transaction helper that runs synchronously on the calling thread
  and commits before returning; and a read-only connection factory for readers. Exposed through
  this module's `api.py` as factory functions, per ADR-0004.
- The **first-run schema creation**: when the database file is absent, create it, run every
  `CREATE TABLE` and `CREATE INDEX` statement of `03_PERSISTENCE_SCHEMA.md` §4–§6, write the
  single `app_meta` row (`id = 1`, `schema_version` = the embedded expected version,
  `created_at` = current UTC), all inside one transaction.
- The **schema-version check and additive evolution** (DD-53): read `app_meta.schema_version`
  and compare it to the single embedded expected-version constant; on match, continue; on an
  older same-major version, apply the ordered additive structural steps (each one idempotent,
  single-transaction, and exactly `ALTER TABLE … ADD COLUMN` / `CREATE TABLE` / `CREATE INDEX`,
  never an `UPDATE`/backfill), then update `app_meta.schema_version`; on a higher or cross-major
  version, raise a hard startup error that alters nothing.
- The `AppSettingsStore` Protocol and its concrete implementation: `get_setting`,
  `upsert_settings`, `list_settings`, and `get_schema_version` per `08-E` §7.6, over the
  `app_settings` and `app_meta` tables.
- `PersistenceError` on every storage failure, per the §7 store envelope.

## Out of scope

- The three built-in seed providers and the embedding-selection probe — owned by STORY-012
  (`ProvidersStore` seeds the providers; the embedding-key *storage* mechanism is
  `AppSettingsStore.upsert_settings`, but no probe runs in Phase 2 — the capability probe that
  writes the embedding keys is a later readiness/UI phase concern, per `03_PERSISTENCE_SCHEMA.md`
  §10).
- The run-data and catalog tables' row-level read/write logic — owned by STORY-009 through
  STORY-013; this story creates the tables' DDL but implements row logic only for
  `app_settings`/`app_meta`.
- The crash-recovery sweep — owned by STORY-011 (`ResultsStore.recover_in_flight_results`).
- Orphan-run handling and the startup-sequence orchestration (which module calls the sweep,
  the version check, in which order) — a composition-root / app-lifecycle concern of a later
  phase; this story provides the version-check and connection primitives it will call.
- Corrupt/unreadable-database detection surfacing beyond raising a hard error — the modal
  dialog is a UI/compose concern of a later phase.

## Spec inputs

- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#21-connection-topology-dd-41` — the one
  write-connection-plus-one-lock discipline, `BEGIN IMMEDIATE`, synchronous-on-calling-thread,
  and the read-only connection rule this module implements.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#2-connection-pragmas` — the exact pragma set,
  and which pragma is write-connection-only.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#8-schema-versioning--additive-structural-steps-no-data-migration-dd-53`
  — the match / older-same-major / higher-or-cross-major / file-absent branch behaviour and the
  three permitted additive step kinds.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#10-seed-data` — the single `app_meta` row and the
  empty-`app_settings` starting state; the deferral of embedding keys until a probe finds a
  model.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#76-appsettingsstore` — the `AppSettingsStore`
  method contracts and their `PersistenceError`/`None` semantics.
- `08_Cross_Cutting/08-O_persistence_schema.md#6-schema-versioning--additive-structural-steps-no-data-migration-dd-53`
  — the bridging summary of the four version-check branches.
- `08_Cross_Cutting/08-I_edge_cases.md#ec-persist-1--database-schema-version-mismatch-at-startup`
  — the older-same-major vs newer/cross-major behaviour this story enforces.
- `08_Cross_Cutting/08-I_edge_cases.md#ec-persist-5--database-file-missing-or-unreadable-at-startup`
  — absent file is the first-run creation path; corrupt file is a hard error that never deletes
  or overwrites the file.

## Design constraints

- `backend/persistence/app_settings/` is Qt-free and asyncio-free; it imports only
  `backend/domain`, `backend/infra`, `backend/errors`, `msgspec`, and `sqlite3`
  (`01_MODULE_INVENTORY.md` row 157). No PySide6, no other `backend/persistence/*` sibling.
- **Ambiguity resolution (ADR-0004): the shared single-writer connection manager and the schema
  lifecycle live in this module and are exposed via its `api.py`** as factory functions
  alongside the `AppSettingsStore` factory; the five sibling stores receive the constructed
  write connection + lock (and the read-only connection factory) by constructor injection from
  `compose.py`. No seventh persistence module is introduced, so the module inventory is
  unchanged.
- **Ambiguity resolution: the schema-version check and the additive structural steps are
  performed by this module** (it owns `app_meta` and `get_schema_version`); the composition root
  in a later phase invokes this module's check-and-evolve entry point at startup before the
  crash-recovery sweep. This story implements the check and the evolution; it does not implement
  where in the startup sequence it is called.
- **Ambiguity resolution: first-run atomicity — schema DDL is applied first, then the seed DML
  (`app_meta` insert) runs in one transaction.** SQLite auto-commits each DDL statement, so DDL
  is not wrapped in the same transaction as the seed insert; the seed insert is its own single
  transaction, and its idempotency (a re-run completes a partial tree, per
  `12_Quality_and_NFRs/06_DATA_INTEGRITY.md` §6) makes an interruption between the two safe.
- All writes go through the single write connection + lock with `BEGIN IMMEDIATE`, synchronously
  on the calling thread; reads use a separate read-only connection. A write is committed when
  the call returns; there is no write queue.
- A higher-than-expected or cross-major `schema_version` raises a hard error that performs no
  DDL, no `UPDATE`, and no file mutation — the file is left exactly as found.

## Acceptance criteria

### STORY-008-AC-1

Given no database file exists at the resolved path, when the module opens the database, then a
new file is created, every `CREATE TABLE` and `CREATE INDEX` statement from
`03_PERSISTENCE_SCHEMA.md` §4–§6 has run, and the single `app_meta` row exists with `id = 1`,
`schema_version` equal to the embedded expected version, and a non-null `created_at`.

### STORY-008-AC-2

Given an existing database whose `app_meta.schema_version` equals the embedded expected version,
when the version check runs, then it reports a match and performs no DDL and no write to
`app_meta`.

### STORY-008-AC-3

Given an existing database whose `app_meta.schema_version` is higher than the embedded expected
version, or from a different major lineage, when the version check runs, then it raises a hard
startup error and the database file is left byte-for-byte unchanged (no DDL, no `UPDATE`, no
`app_meta` rewrite).

### STORY-008-AC-4

For every ordered sequence of additive structural steps declared to bring an older
same-major-lineage database forward to the expected version, applying the steps leaves every
pre-existing row's original column values unchanged and every new column populated only with its
declared `NULL`/`DEFAULT` — the evolution adds structure and never updates, backfills, or
rewrites an existing row.

### STORY-008-AC-5

Given a write issued through the single-writer connection, when a second write is issued
concurrently from another thread, then the two writes are serialized through the one lock, each
runs in its own `BEGIN IMMEDIATE` transaction synchronously on its calling thread, and neither
observes the other half-applied (the committed database contains both writes intact).

### STORY-008-AC-6

Given the `app_settings` table, when `upsert_settings` writes a set of keys and `get_setting` /
`list_settings` read them back, then a written key returns its stored value, an unwritten key
returns `None` from `get_setting`, and `get_schema_version` returns the integer stored in
`app_meta.schema_version`.

## Test plan

- STORY-008-AC-1 — integration (real `tmp_path` SQLite),
  `tests/integration/persistence/test_app_settings_store.py`,
  `test_first_run_creates_schema_and_seeds_app_meta`.
- STORY-008-AC-2 — integration, same file,
  `test_matching_schema_version_performs_no_ddl`.
- STORY-008-AC-3 — integration, same file,
  `test_newer_or_cross_major_version_is_hard_error_leaving_file_untouched`. Covers EC-PERSIST-1
  (the newer/cross-major branch).
- STORY-008-AC-4 — property (Hypothesis over generated additive-step sequences), colocated
  `src/ollama_llm_bench/backend/persistence/app_settings/tests/test_schema_evolution.py`,
  `test_additive_steps_never_mutate_existing_rows`. Covers EC-PERSIST-1 (the older-same-major
  additive branch).
- STORY-008-AC-5 — integration, same directory
  `tests/integration/persistence/test_single_writer.py`,
  `test_concurrent_writes_are_serialized_through_one_lock`.
- STORY-008-AC-6 — integration,
  `tests/integration/persistence/test_app_settings_store.py`,
  `test_setting_upsert_read_and_schema_version`.
- EC-PERSIST-5 — integration, same file, `test_absent_file_is_first_run_and_corrupt_file_is_hard_error`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-008.
- [ ] EC-PERSIST-1 and EC-PERSIST-5 have passing tests.
- [ ] Integration tests run against a real `tmp_path` SQLite database — never an in-memory
  database.
- [ ] A Hypothesis property test proves additive-only schema evolution never mutates an existing
  row (STORY-008-AC-4).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/persistence/app_settings/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
