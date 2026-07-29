---
id: STORY-110
title: Implement the concrete Settings gateway with an atomic Save, an atomic Reset, and import/export
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 06_Settings_Dialog/implementation_structure.md#7-dependency-protocols
  - 06_Settings_Dialog/description.md#6-save-flow-atomic
  - 06_Settings_Dialog/description.md#9-reset-flow
modules:
  - ui/settings_dialog/
  - backend/settings/
  - adapters/ui_gateways/
acceptance_criteria:
  - STORY-110-AC-1
  - STORY-110-AC-2
  - STORY-110-AC-3
  - STORY-110-AC-4
  - STORY-110-AC-5
  - STORY-110-AC-6
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
owner: coder
estimate: L
---

# STORY-110 — Implement the concrete Settings gateway with an atomic Save, an atomic Reset, and import/export

## Goal

Make the Settings dialog able to read and write the real configuration. It lists the real provider
catalog and the real user-saved settings, warns live about a duplicate provider name, tests a
provider's connection, discovers a provider's models for the embedding picker, and probes readiness on
open. Saving commits the provider catalog and the settings values together so a mid-write failure can
never leave the two halves disagreeing, Reset wipes and re-seeds the whole configuration the same way,
and the import and export actions read and write the real backup files.

## In scope

- The concrete `SettingsGateway` implementation and its `make_settings_gateway(...)` factory on the
  adapters layer's public surface — all twenty-two methods.
- The provider-catalog surface (list, lookup by display name, atomic replace) and the settings surface
  (single read, full read, atomic multi-write, resolved effective read).
- The model-capability cache read and the user-override write.
- The connection test, the model discovery, the on-open readiness probe, the embedding probe, and the
  readiness snapshot for the health dots.
- `save_all(...)` and `reset_to_defaults(...)`: one real database transaction each, spanning both the
  provider store and the app-settings store, so neither is a partial write.
- The six import and export methods, over the existing import/export service.
- Promoting the settings registry's in-code defaults table from `backend/settings/`'s private
  internals onto its public surface, because Reset must re-seed **every** settings key and the dialog
  cannot enumerate them.

## Out of scope

- Wiring the gateway into `make_settings_dialog` and `build_app` — owned by STORY-077.
- The dialog's own behaviour, its working copy and dirty diff, and its four sub-dialogs — already
  delivered by STORY-066 … STORY-068; this story changes no user-interface code.
- The import file formats, the three-severity validation model, and the replace-not-merge rule —
  already delivered by `backend/import_export/`; this gateway delegates and adds no parsing.
- Writing an export payload to disk — owned by the native pickers and file-system-actions adapters at
  the dialog level; the export methods return the payload only.
- **How a caller waits for a *blocking* gateway method.** See Design constraints: this is an unsettled
  spec conflict that needs its own ADR before this story can move to `ready`.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway` — the fourteen base method
  signatures, verbatim, which methods are *fast-synchronous* and which are *blocking*, and the
  statement that this gateway wraps the providers store, the app-settings store (including the
  embedding selection keys), the model-capabilities store, `SettingsService`, `ProviderRegistry` (test
  probes and model discovery), and `ReadinessService`.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped
  to the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — a *blocking* method is
  invoked only on a `TaskRunner` worker thread; the graphical thread never blocks; the single write
  connection is guarded by one lock.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter holds the
  backend Protocols and decides how to satisfy each gateway method.
- `06_Settings_Dialog/implementation_structure.md#7-dependency-protocols` — the dialog's dependency
  set, read as the capabilities the adapter wires behind this gateway.
- `06_Settings_Dialog/description.md#6-save-flow-atomic` — Save is one atomic transaction across the
  provider catalog and the settings values; a failure leaves the prior configuration wholly intact.
- `06_Settings_Dialog/description.md#9-reset-flow` — Reset wipes the configuration and re-seeds the
  bundled providers and the in-code setting defaults, as one atomic step.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.
- **Atomicity is this gateway's own responsibility.** `save_all` and `reset_to_defaults` exist
  precisely because two independent void calls cannot express all-or-nothing. Each must wrap both
  store writes in one real database transaction on the single write connection, so that a failure in
  either half leaves both stores untouched. Do not implement either by calling
  `replace_providers` and then `upsert_settings` in sequence.
- `reset_to_defaults` must re-seed **every** key in the settings registry's defaults table — including
  opaque user-interface state keys such as `ui.window_geometry`, `ui.splitter_sizes` and
  `benchmark.last_mode` that the dialog has no visibility into — not just the General tab's own keys.
  That is why the defaults table must move onto `backend/settings/`'s public surface; reaching into
  `backend/settings/_internal/` from the adapters layer is forbidden by `import-linter`.
- `get_setting` returns `str | None`, so it reads through `AppSettingsStore.get_setting(key)`;
  `get_resolved_str` resolves the effective value through `SettingsService.get_str(key)`. Both
  collaborators are needed because `SettingsService` has no nullable getter.
- `export_providers` must never place the internal provider identifier in its payload (DD-33), and no
  literal secret value may appear in any export — only the name of the environment variable holding it.
- Constructing the gateway must be side-effect free — no backend read, no probe, no network call. This
  matters more here than anywhere else: §7b.6 says `probe_all` runs "the auto-check on open", so it
  must fire when the dialog opens, never when `build_app` constructs the gateway
  (STORY-077-AC-2).
- **Unsettled conflict this story must not resolve on its own.** `08-E` §7b.6 marks `test_provider`,
  `discover_models`, `probe_all`, `probe_embedding`, `replace_providers`, `upsert_settings`,
  `save_all`, `reset_to_defaults` and the six import/export methods *blocking* while pinning a
  synchronous return, and the shipped dialog calls several of them directly from graphical-thread
  slots (`ui/settings_dialog/_internal/providers_tab/controller.py`,
  `_internal/sub_dialogs/provider_edit_view.py`). SPEC-074 makes the gateway responsible for thread
  marshalling, but `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` names blocking the graphical
  thread on a work unit's future an anti-pattern. Those three cannot all hold at once. ADR-0014
  records the conflict; it needs its own ADR, and this story stays `draft` until that ADR exists.
- The gateway holds no Qt symbol on its public surface. `adapters/ui_gateways/` must not import `ui`
  (`import-linter`); the Protocol is satisfied structurally.

## Acceptance criteria

### STORY-110-AC-1

Each of the fourteen base `SettingsGateway` methods performs exactly the stated backend interaction
against its injected collaborators and returns that collaborator's value unchanged:

| Gateway method                                     | Backend interaction                                                        |
| -------------------------------------------------- | -------------------------------------------------------------------------- |
| `list_providers()`                                 | returns the providers store's full catalog                                 |
| `get_provider_by_name(name)`                       | returns the providers store's row for that display name, or `None`         |
| `replace_providers(configs)`                       | replaces the whole catalog through the providers store                     |
| `get_setting(key)`                                 | reads `key` from the app-settings store; returns `None` when unset         |
| `list_settings()`                                  | returns the app-settings store's full user-saved row set                   |
| `upsert_settings(values)`                          | writes `values` atomically through the app-settings store                  |
| `get_resolved_str(key)`                            | returns the settings service's resolved effective value for `key`          |
| `list_model_capabilities(provider_id, model_name)` | returns the capabilities store's cached records for that pair              |
| `upsert_model_capability(record)`                  | writes `record` through the capabilities store                             |
| `test_provider(provider_id, model_name)`           | returns the provider registry's inference-test result for that pair        |
| `discover_models(provider_id)`                     | returns the provider registry's discovered model list for that provider    |
| `probe_all()`                                      | returns the readiness service's snapshot after probing every provider      |
| `probe_embedding()`                                | returns the readiness service's snapshot after probing the embedding model |
| `readiness_snapshot()`                             | returns the readiness service's current snapshot without probing           |

### STORY-110-AC-2

Each of the six import and export methods delegates to the import/export service and returns its value
unchanged:

| Gateway method                        | Import/export service call            |
| ------------------------------------- | ------------------------------------- |
| `build_settings_import_preview(path)` | `build_settings_import_preview(path)` |
| `apply_settings_import(preview)`      | `apply_settings_import(preview)`      |
| `build_provider_import_preview(path)` | `build_provider_import_preview(path)` |
| `apply_provider_import(preview)`      | `apply_provider_import(preview)`      |
| `export_settings()`                   | `export_settings()`                   |
| `export_providers()`                  | `export_providers()`                  |

### STORY-110-AC-3

Given a provider catalog and a settings row set already persisted, and an app-settings store whose
write raises a persistence error,
when `save_all(providers=..., settings_values=...)` is called with changes to both,
then the persistence error propagates and both the provider catalog and the settings row set still hold
their original values.

### STORY-110-AC-4

Given a configuration in which every settings key has been overridden away from its in-code default,
when `reset_to_defaults(bundled_providers=...)` is called,
then every key in the settings registry's defaults table holds its in-code default value again —
including keys the General tab does not expose — and the provider catalog holds exactly the supplied
bundled providers.

### STORY-110-AC-5

Given the settings module is imported through its package root only,
when the settings registry's defaults table is read,
then it is reachable from `backend/settings/`'s public surface without importing anything under
`backend/settings/_internal/`.

### STORY-110-AC-6

Given fake providers-store, app-settings-store, capabilities-store, settings, provider-registry,
readiness, and import/export collaborators that record every call,
when `make_settings_gateway(...)` is called,
then the factory returns a gateway and no method was invoked on any collaborator — in particular no
probe ran.

## Test plan

- STORY-110-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per method, total over all
  fourteen), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_settings_gateway.py`,
  `test_each_base_method_performs_its_backend_interaction`.
- STORY-110-AC-2 — unit, table-driven (one row per import/export method), same file,
  `test_each_import_export_method_delegates_to_the_service`.
- STORY-110-AC-3 — integration (needs a real SQLite transaction on a `tmp_path` database, so it
  cannot be a colocated unit test), `tests/integration/test_settings_gateway_atomicity.py`,
  `test_save_all_rolls_back_both_stores_when_the_settings_write_fails`.
- STORY-110-AC-4 — integration, same file,
  `test_reset_to_defaults_reseeds_every_registry_key_and_the_bundled_providers`.
- STORY-110-AC-5 — architecture, `tests/architecture/test_settings_defaults_public.py`,
  `test_settings_defaults_table_is_on_the_public_surface`.
- STORY-110-AC-6 — unit, colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_settings_gateway.py`,
  `test_constructing_the_gateway_touches_no_collaborator`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-110.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The blocking-gateway-method marshalling conflict recorded in Design constraints has its own
  accepted ADR, and this story's implementation follows it.
- [ ] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.
