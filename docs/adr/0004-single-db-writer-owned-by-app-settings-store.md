# ADR-0004 — House the single-writer connection manager and schema lifecycle in the app-settings persistence module

**Status:** accepted
**Date:** 2026-07-10
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** DD-41, DD-53

## Context and problem statement

The persistence specification defines two cross-cutting concerns that no single one of the six
per-aggregate stores obviously owns:

- **The single DB writer (DD-41).** Exactly one write connection guarded by one
  `threading.Lock`, with `BEGIN IMMEDIATE` transactions run synchronously on the calling
  thread, plus a small set of read-only connections under WAL
  (`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §2.1). All six stores write through the same
  writer; none of them individually owns it.
- **The schema lifecycle (DD-53).** First-run schema creation (every `CREATE TABLE` /
  `CREATE INDEX`), the startup schema-version check, and the ordered additive-only structural
  steps for an older same-major database
  (`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §8). This spans all fifteen tables, not one
  aggregate.

The `01_MODULE_INVENTORY.md` enumerates exactly six persistence modules (rows 152–157) and
adds no seventh "connection manager" or "schema" module. The investigator flagged that the
spec never names a module as owning these concerns, and left the ownership decision to the
architect. The question is where the shared connection manager and schema lifecycle live
without inventing a module the inventory does not list.

## Decision drivers

- The module inventory is authoritative and lists six persistence modules, no seventh.
- `AppSettingsStore` already owns `app_meta` — the table that records `schema_version` — and
  already exposes `get_schema_version()` (`08-E_interfaces_contracts.md` §7.6), so the
  schema-version *read* is already its responsibility.
- The single-writer connection and lock must be a *shared* dependency that all six stores
  receive by constructor injection, constructed once by `compose.py`
  (`08-E_interfaces_contracts.md` §7 "Co-construction").
- Adding a module not in the inventory would fail `just trace-check` (a `modules:` entry not
  in `01_MODULE_INVENTORY.md` is rejected) and would require an inventory edit.

## Considered options

- Option A — Add a new `backend/persistence/connection/` (or `backend/persistence/schema/`)
  module for the writer and schema lifecycle.
- Option B — House the shared connection manager and the schema lifecycle (first-run creation,
  version check, additive steps) inside `backend/persistence/app_settings/`, exposed through
  its `api.py` as connection/schema factory functions alongside `AppSettingsStore`; the other
  five stores receive the constructed connection handle by injection from `compose.py`.
- Option C — Duplicate connection/pragma setup inside each of the six stores.

## Decision outcome

Chosen option: **Option B.** The `backend/persistence/app_settings/` module houses the shared
single-writer connection manager (one write connection + one `threading.Lock`, the pragmas of
`03_PERSISTENCE_SCHEMA.md` §2, and read-only connection creation) and the schema lifecycle
(first-run DDL + seed of `app_meta`, the startup version check, and the ordered additive-only
structural steps), exposing them through its `api.py` as factory functions. This keeps the
module count at the six the inventory lists, and it co-locates the writer and schema lifecycle
with the store that already owns `app_meta`, `schema_version`, and `get_schema_version()`.
`compose.py` constructs the connection handle once and injects it into all six stores; no store
constructs its own connection, and no store reaches into another store's tables — the
per-aggregate ownership boundary of `08-O_persistence_schema.md` §4 is unchanged.

### Consequences

- Positive — The module count matches `01_MODULE_INVENTORY.md` exactly; no inventory edit and
  no seventh persistence module. The schema-version read (`get_schema_version`), the schema
  creation/upgrade, and the `app_meta` row live in one module, since all three concern the same
  table. The single-writer connection is constructed once and injected, honouring DD-41.
- Negative — `backend/persistence/app_settings/` carries more than a plain key/value store: it
  also owns the connection factory and the schema lifecycle. Mitigated by keeping these in
  clearly separated `_internal/` files and by the module still exposing one store Protocol plus
  the connection/schema factory functions.
- Neutral — The five other stores gain a constructor dependency on the shared connection handle
  produced by this module's factory, wired only in `compose.py`.

## Pros and cons of the options

### Option A — A new dedicated connection/schema module

- Good — Cleanest single-responsibility separation of the writer/schema concern.
- Bad — Introduces a seventh persistence module the inventory does not list; fails
  `just trace-check` until the inventory is edited, which is out of the architect's remit for a
  vendored, read-only spec artefact set.

### Option B — House it in `app_settings`

- Good — No new module; co-located with the `app_meta`/`schema_version` owner; single injected
  writer per DD-41.
- Bad — `app_settings` owns more than key/value settings.

### Option C — Duplicate per store

- Good — No shared module at all.
- Bad — Six copies of pragma/connection setup; violates the single-writer discipline (DD-41)
  by risking more than one write connection; unmaintainable.

## Links

- Spec clauses: `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#21-connection-topology-dd-41`,
  `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#8-schema-versioning--additive-structural-steps-no-data-migration-dd-53`,
  `08_Cross_Cutting/08-E_interfaces_contracts.md#7-persistence-stores`,
  `08_Cross_Cutting/08-O_persistence_schema.md#4-table-set`
- Stories: STORY-008 (applies this decision), STORY-009, STORY-010, STORY-011, STORY-012,
  STORY-013 (depend on the injected writer)
