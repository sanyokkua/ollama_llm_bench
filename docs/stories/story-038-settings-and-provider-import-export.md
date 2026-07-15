---
id: STORY-038
title: Parse, validate, preview, and apply settings and provider-config import/export
status: done
spec_clauses:
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#2-common-rules-encoding-parsing-validation-severities
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#5-api-key-value-form-environment-variable-name
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#6-validation-on-import
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#7-handling-unknown-keys-type-mismatches-missing-required-fields
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#8-preview-before-apply
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#9-round-trip-guarantee
  - 10_Domain_and_Data/06_IMPORT_FORMATS.md#11-edge-cases
modules:
  - backend/import_export/
acceptance_criteria:
  - STORY-038-AC-1
  - STORY-038-AC-2
  - STORY-038-AC-3
  - STORY-038-AC-4
  - STORY-038-AC-5
  - STORY-038-AC-6
  - STORY-038-AC-7
edge_cases:
  - EC-IMP-1
  - EC-IMP-2
  - EC-IMP-3
  - EC-IMP-6
  - EC-IMP-7
  - EC-IMP-8
  - EC-IMP-9
  - EC-IMP-10
  - EC-IMP-13
depends_on:
  - STORY-001
  - STORY-002
  - STORY-003
  - STORY-008
  - STORY-012
owner: coder
estimate: L
---

# STORY-038 — Parse, validate, preview, and apply settings and provider-config import/export

## Goal

Give the Settings dialog its data-exchange backend: an `ImportExportService` that parses a
settings or provider-config YAML file in safe-load mode, validates it in full under the
three-severity model before anything is written, builds a preview of Added / Changed / Unchanged /
Skipped items, and applies the confirmed result through the persistence stores — merging settings
keys but replacing the provider registry wholesale — while enforcing the environment-variable-name-only
credential rule so a literal secret is never persisted.

## In scope

- `backend/import_export/`: the `ImportExportService` Protocol, `make_import_export_service`
  factory, and a `backend/import_export/testing.py` fake.
- Settings import: schema validation against the settings registry, the merge-only apply, and the
  unknown-key / type-mismatch / constraint-violation soft-warning handling.
- Provider-config import: schema validation, the `name`-based (never `id`) matching, the D-R-18
  env-var-name-only `api_key` rule (a literal secret is a hard error for that entry), the
  replace-not-merge apply (DD-55), and the retired-field soft-info handling.
- The full pre-apply validation producing the preview finding set (hard error / soft warning /
  soft info), and the matching export producing a value-preserving round-trip file.

## Out of scope

- The Settings dialog's Import/Export actions, the native file picker, and the Import Preview
  dialog UI (with its `<redacted>` secret masking) — owned by `ui/settings_dialog/` in a later
  phase; this service returns the validated preview data and applies on confirmation, but renders
  no dialog.
- `provider_id` generation and the `UNIQUE(name)` DB constraint — owned by
  `backend/persistence/providers/` (STORY-012); this service applies through the `ProvidersStore`
  Protocol and pre-checks via `get_by_name`.
- The settings registry key catalog and per-key type/constraint definitions — consumed from
  `backend/settings/` / the settings hierarchy; this service validates against them.
- Resolving an `api_key` environment variable to a live secret value — done lazily at
  provider-client build time, never at import time.

## Spec inputs

- `10_Domain_and_Data/06_IMPORT_FORMATS.md#2-common-rules-encoding-parsing-validation-severities` —
  UTF-8/BOM handling, the `.yaml`/`.yml` extension gate, safe-load parsing, and the three-severity
  model.
- `10_Domain_and_Data/06_IMPORT_FORMATS.md#5-api-key-value-form-environment-variable-name` — the
  D-R-18 env-var-name-only rule and the literal-secret hard error.
- `10_Domain_and_Data/06_IMPORT_FORMATS.md#6-validation-on-import` — the file-level, settings, and
  provider-config validation checks and their severities.
- `10_Domain_and_Data/06_IMPORT_FORMATS.md#7-handling-unknown-keys-type-mismatches-missing-required-fields` —
  the item-degrades-vs-file-aborts rule.
- `10_Domain_and_Data/06_IMPORT_FORMATS.md#8-preview-before-apply` — the preview grouping and the
  merge-settings / replace-providers apply semantics.
- `10_Domain_and_Data/06_IMPORT_FORMATS.md#9-round-trip-guarantee` — the value-preserving
  export→import contract and the `provider_id`-not-round-tripped rule.
- `10_Domain_and_Data/06_IMPORT_FORMATS.md#11-edge-cases` — EC-IMP-1..EC-IMP-13.

## Design constraints

- `backend/import_export/` is Qt-free and asyncio-free; it imports only `ruamel.yaml`,
  `backend/domain`, `backend/errors`, `backend/events`, and the `ProvidersStore` /
  `AppSettingsStore` Protocols (`01_MODULE_INVENTORY.md` §4.5). No PySide6.
- File parsing is the **external-file boundary**: files are parsed in safe-load mode (no arbitrary
  object construction) and schema-validated for correctness only, per DD-55 — validation is not a
  security control. File parsing runs as a blocking unit on a `TaskRunner` worker.
- The import **never partially applies**: full validation precedes the preview, and no value is
  written until the user confirms. A literal secret in an `api_key` field is a hard error for that
  entry — a literal is never persisted (D-R-18).
- Settings import **merges** (only present, valid keys written); provider-config import
  **replaces** the registry wholesale (DD-55). The apply writes through the single DB writer
  (DD-41).
- `icontract` on any `api.py` symbol guards programmer invariants only — never file content or an
  env-var value.

## Acceptance criteria

### STORY-038-AC-1

Each file-level condition resolves to its fixed severity per this table, and any hard error
aborts the whole import before the preview:

| Condition                               | Severity     | Effect         |
| --------------------------------------- | ------------ | -------------- |
| Extension not `.yaml`/`.yml`            | hard error   | import aborted |
| Malformed YAML                          | hard error   | import aborted |
| Root not a mapping                      | hard error   | import aborted |
| `kind` present and wrong for the action | hard error   | import aborted |
| `schema_version` newer than this build  | hard error   | import aborted |
| `schema_version` non-integer or `< 1`   | soft warning | treated as `1` |

### STORY-038-AC-2

Given a provider entry whose `api_key` value is a literal secret (not an environment-variable
name), when the file is validated, then that entry raises a hard error, the entry is not applied,
and no literal secret value is persisted (D-R-18).

### STORY-038-AC-3

Given a provider-config import, each item-scoped and file-scoped condition resolves per this
table:

| Condition                                                        | Scope | Severity     | Effect                                           |
| ---------------------------------------------------------------- | ----- | ------------ | ------------------------------------------------ |
| Provider entry missing `name` or `type`                          | item  | hard error   | entry dropped; aborts if it drops the last entry |
| `type` not one of the three allowed values                       | item  | hard error   | entry dropped                                    |
| `openai_compatible` entry missing `base_url`                     | item  | hard error   | entry dropped                                    |
| Two entries share a `name` within the file                       | file  | hard error   | import aborted                                   |
| `embedding.provider_name` matches no entry `name`                | file  | hard error   | import aborted                                   |
| Entry `name` matches an existing `ProvidersStore` row (add path) | item  | soft warning | entry skipped                                    |
| An `id:` field present on an entry                               | item  | soft info    | ignored, listed skipped                          |

### STORY-038-AC-4

Given a settings import with an unknown key, a wrong-typed value, and a constraint-violating
value alongside valid keys, when it is validated, then each offending key is skipped with a soft
warning or soft info, the valid keys remain applicable, and no offending key aborts the import.

### STORY-038-AC-5

Given a confirmed provider-config import, when it is applied, then the provider registry is
replaced wholesale by the imported set (replace, not merge, DD-55); and given a confirmed
settings import, only the present valid keys are written and every other setting keeps its
current value.

### STORY-038-AC-6

For a settings store and a provider registry, exporting then importing the resulting file leaves
every exported setting at its exported value and reproduces the same provider list by `name`,
`type`, `base_url`, `enabled`, `default_models`, Azure fields, and `api_key` value form, and the
same embedding selection by provider name plus model, while `provider_id` is regenerated fresh
(not round-tripped).

### STORY-038-AC-7

Given any import, when a file-level hard error is present, then no store write occurs; and given
the user does not confirm the preview, then nothing is applied and the current state is unchanged.

## Test plan

- STORY-038-AC-1 — unit (table-driven over file-level conditions), colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_file_level_validation.py`,
  `test_file_level_condition_severity`. Covers EC-IMP-1, EC-IMP-2, EC-IMP-3.
- STORY-038-AC-2 — unit, colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_api_key_rule.py`,
  `test_literal_secret_is_hard_error_and_not_persisted`. Covers EC-IMP-9.
- STORY-038-AC-3 — unit (table-driven over provider conditions), colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_provider_validation.py`,
  `test_provider_condition_severity`. Covers EC-IMP-6, EC-IMP-7, EC-IMP-8, EC-IMP-10, EC-IMP-13.
- STORY-038-AC-4 — unit (table-driven over settings conditions), colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_settings_validation.py`,
  `test_settings_offending_key_skipped_valid_kept`.
- STORY-038-AC-5 — unit (against the `ProvidersStore`/`AppSettingsStore` fakes), colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_apply.py`,
  `test_providers_replace_settings_merge`.
- STORY-038-AC-6 — property (Hypothesis over registries/settings), colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_round_trip.py`,
  `test_export_import_is_value_preserving`.
- STORY-038-AC-7 — unit (against store fakes asserting zero writes), colocated
  `src/ollama_llm_bench/backend/import_export/tests/test_no_partial_apply.py`,
  `test_hard_error_or_cancel_writes_nothing`. Covers EC-IMP-11 at the service boundary (no apply
  on non-confirmation).

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-038.
- [ ] EC-IMP-1, EC-IMP-2, EC-IMP-3, EC-IMP-6, EC-IMP-7, EC-IMP-8, EC-IMP-9, EC-IMP-10, and
  EC-IMP-13 have passing tests.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/import_export/`.
- [ ] An architecture test confirms the module imports no Qt and no `asyncio`.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-038.
- [ ] The module inventory is unchanged.
