---
id: STORY-013
title: Provide the ModelCapabilitiesStore over the probed-capability cache
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#75-modelcapabilitiesstore
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#46-model_capabilities
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#7-foreign-keys-and-cascade-policy
modules:
  - backend/persistence/model_capabilities/
acceptance_criteria:
  - STORY-013-AC-1
  - STORY-013-AC-2
  - STORY-013-AC-3
depends_on:
  - STORY-008
  - STORY-012
owner: coder
estimate: S
---

# STORY-013 — Provide the ModelCapabilitiesStore over the probed-capability cache

## Goal

Give the application the durable gateway for the per-`(provider, model)` capability cache: read
the cached capability records for one model and insert-or-update a single capability record. The
cache lets the app remember what a model supports (streaming, reasoning effort, thinking) without
re-probing every time.

## In scope

- The `ModelCapabilitiesStore` Protocol and its concrete implementation:
  `list_model_capabilities` and `upsert_model_capability` per `08-E` §7.5, over the
  `model_capabilities` table.
- `list_model_capabilities(provider_id, model_name)` returning the cached
  `ModelCapabilityRecord` rows for one model (via `idx_model_caps_model`);
  `upsert_model_capability` inserting or updating one row on the
  `(provider_id, model_name, capability)` primary key, honouring the `capability`, `supported`
  (tri-state `-1`/`0`/`1`), and `observed_via` CHECK constraints.
- `PersistenceError` on every storage failure.

## Out of scope

- The `providers` and `provider_models` tables and provider deletion — owned by STORY-012;
  deleting a provider cascades to its `model_capabilities` rows via the FK this store relies on.
- The capability probe that produces the records (the model-helpers capability service and the
  provider `probe_health` path) — owned by `backend/model_helpers/` and the provider modules in
  a later phase; this store only persists already-observed records.
- The single-writer connection and lock this store writes through — owned by STORY-008.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#75-modelcapabilitiesstore` — the two method
  signatures and their `PersistenceError` semantics.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#46-model_capabilities` — the
  `model_capabilities` columns, the `(provider_id, model_name, capability)` primary key, the
  tri-state `supported` CHECK, the `capability` / `observed_via` CHECK domains, and the cascade
  FK to `providers`.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#7-foreign-keys-and-cascade-policy` — the
  `ON DELETE CASCADE` from `providers` this store depends on for provider-deletion cleanup.

## Design constraints

- `backend/persistence/model_capabilities/` is Qt-free and asyncio-free; it imports only
  `backend/domain`, `backend/infra`, `backend/errors`, `msgspec`, and `sqlite3`
  (`01_MODULE_INVENTORY.md` row 156). It does not import any other `backend/persistence/*`
  sibling.
- All writes go through the injected single-writer connection + lock (STORY-008, DD-41) with
  `BEGIN IMMEDIATE`, synchronously on the calling thread; reads use the injected read-only
  connection factory.
- `upsert_model_capability` is keyed on `(provider_id, model_name, capability)` — re-observing
  the same capability overwrites the existing row rather than duplicating it.

## Acceptance criteria

### STORY-013-AC-1

Given no cached capability for a model, when `upsert_model_capability` writes a record, then
`list_model_capabilities(provider_id, model_name)` returns exactly that record with its
`supported`, `last_observed_at`, `observed_via`, and `detail` values preserved.

### STORY-013-AC-2

Given a cached capability record for a `(provider_id, model_name, capability)` triple, when
`upsert_model_capability` writes a new record for the same triple with a different `supported`
value, then the existing row is updated in place and `list_model_capabilities` returns one row
for that capability, not two.

### STORY-013-AC-3

Given cached capability rows for a provider, when that provider is deleted (STORY-012), then
`list_model_capabilities` returns an empty tuple for its models — the rows were cascade-removed.

## Test plan

- STORY-013-AC-1 — integration (real `tmp_path` SQLite),
  `tests/integration/persistence/test_model_capabilities_store.py`,
  `test_upsert_then_list_returns_record`.
- STORY-013-AC-2 — integration, same file,
  `test_upsert_same_triple_updates_in_place`.
- STORY-013-AC-3 — integration, same file,
  `test_provider_delete_cascades_capabilities`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-013.
- [ ] Integration tests run against a real `tmp_path` SQLite database — never an in-memory
  database.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for
  `backend/persistence/model_capabilities/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
