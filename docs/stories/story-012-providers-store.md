---
id: STORY-012
title: Provide the ProvidersStore with UUID4 id generation and built-in provider seeding
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#74-providersstore
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#42-providers
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#43-provider_models
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#10-seed-data
  - 12_Quality_and_NFRs/06_DATA_INTEGRITY.md#7a-unique-on-name-invariants-and-auto-id-atomicity-dd-33
modules:
  - backend/persistence/providers/
acceptance_criteria:
  - STORY-012-AC-1
  - STORY-012-AC-2
  - STORY-012-AC-3
  - STORY-012-AC-4
  - STORY-012-AC-5
depends_on:
  - STORY-008
owner: coder
estimate: M
---

# STORY-012 — Provide the ProvidersStore with UUID4 id generation and built-in provider seeding

## Goal

Give the application the durable gateway for the provider catalog: list providers in display
order, look one up by name, add a provider with a store-generated UUID4 identifier, update or
delete a provider, replace the whole catalog atomically, and seed the three built-in local
providers on first start. The user never types a provider identifier; the store owns it.

## In scope

- The `ProvidersStore` Protocol and its concrete implementation: `list_providers`,
  `get_by_name`, `add`, `update`, `delete`, `replace_providers` per `08-E` §7.4, over the
  `providers` and `provider_models` tables.
- `add(draft) -> ProviderId` generating a fresh UUID4 textual `provider_id` on insert (DD-33)
  and returning it only after commit; `update` mutating every column except the immutable
  `provider_id`; `delete` cascading to `provider_models` and `model_capabilities` while leaving
  run-history snapshot rows untouched; `replace_providers` replacing the whole catalog in one
  transaction.
- Enforcing `UNIQUE (name)`: a duplicate-name `add`/`update`/`replace_providers` raises
  `PersistenceError` (the DB constraint is the backstop; `get_by_name` is the caller's
  friendly-error pre-check).
- Seeding the three built-in providers (Ollama, LM Studio, llama.cpp) — all
  `provider_type = 'openai_compatible'`, `enabled = 1`, no API key, `provider_order` 0/1/2, each
  with a fresh UUID4 `provider_id` — inside one transaction on first start.
- `PersistenceError` on every storage failure.

## Out of scope

- The `app_meta` seed row and the schema lifecycle — owned by STORY-008; provider seeding runs
  after the schema exists.
- The embedding-selection `app_settings` keys and the first-run embedding-capability probe — the
  probe is deferred to a later readiness/UI phase (`03_PERSISTENCE_SCHEMA.md` §10); this story
  seeds no embedding keys.
- The Settings "Reset to Defaults" action's UI flow — a later UI phase; this story provides the
  `replace_providers` / seed mechanism it will call.
- Literal-secret rejection in `api_key_raw` (the `ConfigurationError` on a value that looks like
  a credential) — enforced at the Settings-editor / import boundary in a later phase; this store
  stores the env-var name as given.
- The single-writer connection and lock this store writes through — owned by STORY-008.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#74-providersstore` — the six method contracts,
  the `add(draft) -> ProviderId` UUID4-generation ownership, the immutable-`provider_id` rule,
  and the `get_by_name` pre-check pattern.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#42-providers` — the `providers` columns, the
  `provider_type` CHECK, the `UNIQUE (name)` constraint, and the `api_key_raw`-is-an-env-var-name
  rule.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#43-provider_models` — the `provider_models`
  composite key, `model_order`, and the cascade FK to `providers`.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#10-seed-data` — the three built-in providers with
  fresh UUID4 ids, `provider_order` 0/1/2, no API key, all enabled, seeded in one transaction.
- `12_Quality_and_NFRs/06_DATA_INTEGRITY.md#7a-unique-on-name-invariants-and-auto-id-atomicity-dd-33`
  — the atomic UUID4 generation (returned only after commit) and the atomic duplicate-name raise.

## Design constraints

- `backend/persistence/providers/` is Qt-free and asyncio-free; it imports only
  `backend/domain`, `backend/infra`, `backend/errors`, `msgspec`, `sqlite3`, and `uuid`
  (`01_MODULE_INVENTORY.md` row 155). It does not import any other `backend/persistence/*`
  sibling.
- All writes go through the injected single-writer connection + lock (STORY-008, DD-41) with
  `BEGIN IMMEDIATE`, synchronously on the calling thread; reads use the injected read-only
  connection factory.
- `add` generates the UUID4 inside the insert transaction and returns it only after commit, so a
  caller never observes an uncommitted id; on a duplicate-name failure the call raises and
  returns no id.
- `delete` never propagates to run-history rows — the `provider_id` links in
  `benchmark_run_providers`, `benchmark_run_models`, `benchmark_runs`, and `benchmark_results`
  are logical, not foreign keys, so past runs keep their frozen snapshot.
- Seeding uses fresh UUID4 ids each time (including on a Reset to Defaults re-seed); the three
  seed `name` values are unique, satisfying `UNIQUE (name)`.

## Acceptance criteria

### STORY-012-AC-1

Given an empty provider catalog, when `add(draft)` is called, then the store generates a fresh
UUID4 textual `provider_id`, inserts the `providers` row and its `provider_models` rows in one
transaction, and returns the generated `provider_id` only after commit.

### STORY-012-AC-2

Given a provider named `N` already exists, when `add` (or `update` targeting a different row, or
`replace_providers` with an internally non-duplicate set) attempts to persist a second row named
`N`, then the store raises `PersistenceError` and no half-applied row survives; `get_by_name(N)`
returns the existing provider before the attempt.

### STORY-012-AC-3

Given a persisted provider, when `update` is called with a changed `name` and model list, then
every column except `provider_id` is updated on that row and the `provider_id` is unchanged.

### STORY-012-AC-4

Given a persisted provider with `provider_models` and `model_capabilities` rows and a past run
whose snapshot references it, when `delete` is called, then the provider and its
`provider_models` and `model_capabilities` rows are removed while the run's frozen snapshot rows
survive and remain readable.

### STORY-012-AC-5

Given an empty database, when the provider seed runs, then exactly three
`provider_type = 'openai_compatible'` providers exist — named Ollama, LM Studio, and llama.cpp —
each `enabled = 1` with no API key, with `provider_order` 0, 1, and 2 respectively and a distinct
UUID4 `provider_id`, written in one transaction.

## Test plan

- STORY-012-AC-1 — integration (real `tmp_path` SQLite),
  `tests/integration/persistence/test_providers_store.py`,
  `test_add_generates_uuid4_and_returns_it_after_commit`.
- STORY-012-AC-2 — integration, same file,
  `test_duplicate_name_raises_atomically_and_get_by_name_precheck`.
- STORY-012-AC-3 — integration, same file, `test_update_preserves_immutable_provider_id`.
- STORY-012-AC-4 — integration, same file,
  `test_delete_cascades_models_and_caps_but_preserves_run_snapshot`.
- STORY-012-AC-5 — integration,
  `tests/integration/persistence/test_provider_seed.py`,
  `test_seed_writes_three_builtin_providers_in_one_transaction`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-012.
- [ ] Integration tests run against a real `tmp_path` SQLite database — never an in-memory
  database.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/persistence/providers/`.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
