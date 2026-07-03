# Import Formats

**Status:** Draft
**Owner:** architect
**Audience:** coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** 06_Settings_Dialog/description.md, 10_Domain_and_Data/02_DTOS_AND_ENUMS.md, 10_Domain_and_Data/05_EXPORT_FORMATS.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 10_Domain_and_Data/08_REDACTION_PATTERNS.md

This document defines every file the application accepts as input through the Settings dialog: the application settings import and the provider configuration import. It fixes the YAML schemas, the validation performed on import, how unknown keys, type mismatches, and missing required fields are handled, the round-trip guarantee against the matching export, and the preview-before-apply flow that lets a user review changes before they take effect.

---

## Table of Contents

1. Import surfaces
2. Common rules (encoding, parsing, validation severities)
3. Settings import — schema
4. Provider configuration import — schema
5. API key value form (environment-variable name)
6. Validation on import
7. Handling unknown keys, type mismatches, missing required fields
8. Preview-before-apply
9. Round-trip guarantee
10. Worked examples
11. Edge cases

---

## 1. Import surfaces

Two import actions exist, both in the Settings dialog (see `06_Settings_Dialog/description.md`):

| Action | Input file | Applies to |
|---|---|---|
| Import Settings | A settings YAML file | The user-scoped application settings store. |
| Import Provider Configuration | A provider-config YAML file | The provider registry: the provider list and the embedding configuration. |

Each import is a deliberate, user-initiated action. Importing never happens automatically and never happens at application startup. An import always shows a preview and requires explicit confirmation before any value is written.

Import/export is a **same-user data-portability feature** (DD-55): its purpose is backup and restore — an OS reinstall, an application reinstall, or a move to another device. An import file is treated as the user's own previously exported data. Validation therefore checks **correctness only** — schema shape, required fields, and value validity — and is not a security control; see the non-goals of `12_Quality_and_NFRs/02_SECURITY_MODEL.md` §9.

## 2. Common rules (encoding, parsing, validation severities)

| Aspect | Rule |
|---|---|
| Encoding | UTF-8; a byte-order mark is tolerated and stripped. |
| Extension | `.yaml` or `.yml`. Any other extension is rejected before parsing. |
| Parser | Standard YAML; safe-load semantics (no arbitrary object construction). |
| Malformed YAML | The import is aborted with an error modal naming the parse error and line; nothing is applied. |
| Validation severities | The same three-severity model used elsewhere in the spec: hard error (blocks the offending item or the whole import), soft warning (item is imported with a fallback), soft info (item is imported as-is, noted in the preview). |
| Secret display in the preview | The Import Preview dialog renders any credential value as the fixed `<redacted>` placeholder (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §6) plus a character count — the dialog never shows a plaintext API key. An environment-variable name is shown verbatim because a name is not a secret. This is a dialog-local masking rule and uses the same placeholder token as the redaction module; the module's three-surface scope (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1) is independent of this dialog's display rule. |

## 3. Settings import — schema

A settings file is a YAML mapping. The canonical form, which matches the settings export, is:

```yaml
schema_version: 1
kind: settings
settings:
  <setting_key>: <value>
  <setting_key>: <value>
```

| Top-level key | Type | Requirement | Notes |
|---|---|---|---|
| `schema_version` | integer | optional | Absent is treated as `1`. A value newer than this build understands aborts the import. |
| `kind` | string | optional | When present must be `settings`; a mismatch is a hard error guarding against importing the wrong file. |
| `settings` | mapping | required | Maps a setting key to its value. |

The `settings` mapping carries user-scoped keys only. Each key is validated against the settings registry: the key must be known, and the value must match the registered type and any registered constraint (range, enum, pattern). Per-run-snapshot keys and internal keys are not user-importable; if present they are reported as unknown keys (§7). The authoritative key catalog and per-key types are defined in `08_Cross_Cutting` settings hierarchy and consumed here.

A bare mapping of `key: value` pairs with neither `schema_version` nor `kind` is also accepted on import and treated as the content of `settings:` with `schema_version: 1`.

## 4. Provider configuration import — schema

A provider-config file is a YAML mapping describing the provider registry and the embedding configuration.

```yaml
schema_version: 1
kind: provider_config
embedding:
  provider_name: Ollama (local)
  model_name: bge-m3:567m
providers:
  - name: Ollama (local)
    type: openai_compatible
    base_url: http://localhost:11434/v1
    api_key: ""
    enabled: true
    default_models:
      - llama3.2:3b
      - mistral:7b
```

### 4.1 Top-level keys

| Key | Type | Requirement | Notes |
|---|---|---|---|
| `schema_version` | integer | optional | Absent is treated as `1`; newer-than-build aborts the import. |
| `kind` | string | optional | When present must be `provider_config`; a mismatch is a hard error. |
| `embedding` | mapping | required | The embedding-configuration selection. |
| `providers` | sequence | required | One mapping per provider. Must contain at least one entry. |

### 4.2 The `embedding` mapping

The `embedding` mapping carries the selected `(provider name, embedding model)` pair (D-R-13). On import, it sets the two `app_settings` keys `embedding.selected_provider_name` and `embedding.selected_model_name`; there is no embedding id and no embedding catalog row.

| Field | Type | Requirement | Notes |
|---|---|---|---|
| `provider_name` | string | required | The display `name` of the provider that hosts the embedding model. Must match the `name` of one entry in `providers`. Stored as `embedding.selected_provider_name`. |
| `model_name` | string | required | The embedding model name on that provider. Stored as `embedding.selected_model_name`. |

### 4.3 Each `providers` entry

The provider entry carries a **`name`**, never an `id`. The internal `provider_id` is auto-generated by `ProvidersStore.add` on insert (or matched on update by `name`). An `id:` key in an imported file is **retired** as of DD-33: when present, it is silently ignored and listed in the preview's Skipped / ignored group with the reason "Field retired — provider_id is now auto-generated". This keeps older exports importable without forcing the user to edit the file.

| Field | Type | Requirement | Default | Notes |
|---|---|---|---|---|
| `name` | string | required | none | The user-entered display name. Must be unique within the file AND not collide with an existing row's `name` in `ProvidersStore` unless the import action is the full-replace `replace_providers` flow (see §8). The importer pre-checks via `ProvidersStore.get_by_name(entry.name)`. |
| `id` | string | **retired (DD-33)** | — | Silently ignored if present; listed in the preview's Skipped / ignored group. Older exports may carry it; new exports do not. The internal `provider_id` is auto-generated on insert and never round-trips through the file. |
| `type` | enum | required | none | One of `openai_compatible`, `anthropic`, `gemini`. |
| `base_url` | string | conditional | none | Required for `openai_compatible`; ignored for `anthropic` and `gemini`. |
| `api_key` | string | optional | `""` | The NAME of an environment variable (e.g. `OPENAI_API_KEY`), or empty for a keyless local provider; never a literal secret. See §5. |
| `enabled` | boolean | optional | `false` | Whether the provider is active. |
| `default_models` | sequence of strings | optional | empty | Models pre-selected for this provider in the run config. |
| `azure_deployment` | string | conditional | none | Required only when `type` is `openai_compatible` and the provider is an Azure endpoint. |
| `azure_api_version` | string | conditional | none | Same condition as `azure_deployment`. |

Provider entries also carry last-test diagnostic fields in the export. There are two independent column sets, each corresponding to a distinct user-initiated action: the **last reachability probe** (`last_probe_status`, `last_probe_at`, `last_probe_reachable`, `last_probe_model_count`, `last_probe_message`) and the **last end-to-end inference test** (`last_inference_test_at`, `last_inference_test_outcome`, `last_inference_test_model`, `last_inference_test_message`). On import all of these are accepted but ignored — connection and inference diagnostics are runtime state, not configuration, and are recomputed by the application as the user reruns the actions in the Provider Edit sub-dialog. The two sets replace the previous single conflated `last_test_status` / `last_test_at` / `last_test_message` triplet; the older field names, if present in an imported file, are also accepted-and-ignored for backward compatibility with files exported by older builds.

## 5. API key value form (environment-variable name)

An `api_key` value is the **NAME of an environment variable** (for example `OPENAI_API_KEY`), matching `[A-Za-z_][A-Za-z0-9_]*`, or empty for a keyless local provider. It is **not** a literal secret and **not** a wrapped reference; the bare variable name is the stored value (D-R-18, superseding D-R-09). The Azure `azure_endpoint`, `azure_deployment`, and `azure_api_version` fields import as **plain literal configuration values** (endpoint URL, deployment name, api version) — they are not secrets and are stored as-is.

Rules:

- The named variable is resolved lazily, each time the provider client is built, not at import time. Import does not require the variable to be set.
- If, at import time, the imported `api_key` names a variable that is not currently set, the preview shows a soft warning ("Environment variable `<NAME>` is not currently set"). The name is still imported.
- A literal secret value in the `api_key` field of an import file is a **hard error** for that entry (see EC-IMP-9): a literal is never persisted. The field must carry an environment-variable name. There is no conversion offer — the file must be corrected to a name.
- The env-var name is shown verbatim in the preview (a name is not a secret). The Azure config values are shown verbatim as well.

## 6. Validation on import

Validation runs in full before the preview is shown. The import never partially applies; the user sees every finding first.

### 6.1 File-level checks

| Check | Severity |
|---|---|
| Extension not `.yaml`/`.yml` | Hard error — import aborted. |
| Malformed YAML | Hard error — import aborted. |
| Root is not a mapping | Hard error — import aborted. |
| `kind` present and wrong for the chosen import action | Hard error — import aborted. |
| `schema_version` newer than this build supports | Hard error — import aborted. |
| `schema_version` non-integer or less than 1 | Soft warning — treated as `1`. |

### 6.2 Settings import checks

| Check | Severity |
|---|---|
| `settings` key missing or not a mapping | Hard error — import aborted. |
| A setting key is not in the registry | Soft warning — that key is skipped; see §7. |
| A setting value's type does not match the registered type | Soft warning — that key is skipped; see §7. |
| A setting value violates a registered constraint (range, enum, pattern) | Soft warning — that key is skipped. |
| Zero importable keys remain after validation | Soft warning — import is allowed but a no-op; preview states this. |

### 6.3 Provider configuration import checks

| Check | Severity |
|---|---|
| `providers` missing, not a sequence, or empty | Hard error — import aborted. |
| `embedding` missing or not a mapping | Hard error — import aborted. |
| A provider entry missing `name` or `type` | Hard error for that entry — entry dropped; if it drops the last entry, the import is aborted. (Per DD-33, `id` is retired/ignored — §"provider entry"; missing-`id` is never an error.) |
| Two provider entries share a `name` | Hard error — import aborted (an ambiguous registry cannot be applied). See EC-IMP-7. (The retired "duplicate `id`" rule no longer applies — `id` is ignored on import.) |
| `type` not one of the three allowed values | Hard error for that entry — entry dropped. |
| `openai_compatible` provider missing `base_url` | Hard error for that entry — entry dropped. |
| `base_url` present but not a syntactically valid URL | Hard error for that entry — entry dropped (value-validity check; the same syntactic rule the provider-edit dialog applies). |
| `embedding.provider_name` does not match the `name` of any entry in the `providers` sequence | Hard error — import aborted. |
| `id` field present on a provider entry (retired in DD-33) | Soft info — field ignored and listed in the preview's Skipped / ignored group with reason "Field retired — provider_id is now auto-generated". |
| `name` missing on a provider entry | Hard error for that entry — entry dropped. |
| Two provider entries share a `name` (case-sensitive) | Hard error — import aborted (DD-33, EC-PROV-13). |
| A provider entry's `name` matches an existing row in `ProvidersStore.get_by_name` AND the import action is not the full-replace flow | Soft warning — entry skipped with reason "Duplicate name — already in catalog"; the rest of the import proceeds (EC-PROV-13). |
| `enabled` missing | Soft info — defaults to `false`. |
| `label` field present (retired — replaced by `name` per DD-33) | Soft info — when `name` is also present, `label` is ignored. When only `label` is present (an older export), it is promoted to `name` for backward compatibility and a soft info note is emitted. |
| `api_key` is a literal secret value | **Hard error for that entry (D-R-18):** literal secrets are not accepted. The preview flags the entry as needing an environment-variable name; the user must edit the file before that provider imports. A literal is never persisted. |
| `api_key` is an environment-variable name for an unset variable | Soft warning — imported as-is. |
| `name` field present on the `embedding` mapping (retired — embeddings have no user-facing name, D-R-13) | Soft info — field ignored and listed in the preview's Skipped / ignored group with reason "Field retired — embeddings have no name". |
| An unknown field on a provider entry or on `embedding` | Soft info — field ignored; see §7. |

## 7. Handling unknown keys, type mismatches, missing required fields

The import is deliberately lenient where leniency is safe and strict where ambiguity would corrupt state.

| Situation | Behaviour |
|---|---|
| Unknown top-level key | Ignored. Listed in the preview as a soft info ("Unrecognised key — ignored"). |
| Unknown nested key (under `settings`, `embedding`, or a provider entry) | Ignored. Listed in the preview as soft info. Never aborts the import. |
| Type mismatch on a settings value | The key is skipped (not applied) and reported as a soft warning. The remaining keys still import. |
| Type mismatch on a required provider field | Treated as if the field were missing — hard error for that entry. |
| Missing required field, item-scoped (a provider entry) | The entry is dropped with a hard error; the rest of the import proceeds, unless dropping leaves the registry empty, which aborts the import. |
| Missing required field, file-scoped (`settings`, `providers`, `embedding`) | The whole import is aborted with a hard error. |
| Constraint violation on a settings value | The key is skipped and reported as a soft warning. |

The guiding rule: a problem confined to one item degrades that item only; a problem that makes the file structurally unusable aborts the whole import.

## 8. Preview-before-apply

No import writes anything until the user confirms. The flow:

1. The user picks a file through a native file picker.
2. The application parses and fully validates the file (§6).
3. If a file-level hard error occurred, an error modal explains it and the flow ends; nothing is applied.
4. Otherwise a **preview dialog** opens. It shows, per imported item, the proposed change against the current value, in three groups: **Added**, **Changed**, and **Unchanged**. It also shows a **Skipped / ignored** group listing every soft warning and soft info with its reason.
5. For settings, each changed key shows `current value → imported value`. For providers, each provider shows whether it is added, replaces an existing provider of the same `id`, or is unchanged.
6. Every secret value in the preview is redacted (§2).
7. The user confirms or cancels. Cancelling applies nothing.
8. On confirmation:
   - Provider configuration import **replaces** the registry wholesale with the imported set — this is a replace, not a merge, so that the imported file is an exact description of the resulting registry. The preview's "Unchanged" group makes the replacement transparent.
   - Settings import **merges** — only the keys present and valid in the file are written; every other setting keeps its current value. Skipped keys are not written.
9. After a successful apply, an in-app confirmation states how many items were applied and how many were skipped.

A literal secret value in an `api_key` field is rejected on import as a hard error for that entry (EC-IMP-9, D-R-18); the file must carry an environment-variable name. There is no conversion dialog — the user corrects the file.

## 9. Round-trip guarantee

Export followed by import is value-preserving for the data the format carries.

- **Settings:** exporting the settings store, then importing the resulting file into a store with the same setting registry, leaves every exported setting at its exported value. Keys that are not user-importable are not in the export and so are unaffected.
- **Provider configuration:** exporting the provider registry, then importing the resulting file, reproduces the same provider list (same `name`, `type`, `base_url`, `enabled`, `default_models`, Azure fields, and `api_key` value form) and the same embedding selection (by provider name + model). The internal `provider_id` is intentionally NOT round-tripped (DD-33) — it is auto-generated on insert, so a round trip via import produces fresh UUID4 values. The embedding selection is by-name and so DOES round-trip. Historical run rows that reference an old id continue to render the snapshotted name from the run-data tables, so the import does not retroactively relabel completed runs. Runtime-only diagnostic fields (`last_test_*`) are exported for human reference but are not part of the round-trip contract; they are recomputed by the application.
- **API keys:** the value is the environment-variable name and round-trips as the identical name string. Literal secrets are not accepted (D-R-18), so only env-var names (or empty) exist to round-trip.
- **Field order and comments** are not part of the round-trip guarantee; the import consumes values, not layout.

## 10. Worked examples

### 10.1 Settings import file

```yaml
schema_version: 1
kind: settings
settings:
  ui.theme: dark
  ui.last_tab: charts
  ui.export_save_directly: true
  benchmark.default_run_mode: graded
  benchmark.judge_max_retries: 2
  task_editor.auto_format_on_save: true
```

### 10.2 Provider configuration import file

```yaml
schema_version: 1
kind: provider_config
embedding:
  provider_name: Ollama (local)
  model_name: bge-m3:567m
providers:
  - name: Ollama (local)
    type: openai_compatible
    base_url: http://localhost:11434/v1
    api_key: ""
    enabled: true
    default_models:
      - llama3.2:3b
      - mistral:7b
      - qwen2.5:7b
  - name: OpenAI
    type: openai_compatible
    base_url: https://api.openai.com/v1
    api_key: OPENAI_API_KEY
    enabled: false
    default_models:
      - gpt-4o-mini
  - name: Anthropic
    type: anthropic
    api_key: ANTHROPIC_API_KEY
    enabled: false
    default_models:
      - claude-sonnet-4-5
```

### 10.3 Provider configuration with an Azure endpoint

```yaml
schema_version: 1
kind: provider_config
embedding:
  provider_name: Ollama (local)
  model_name: bge-m3:567m
providers:
  - name: Ollama (local)
    type: openai_compatible
    base_url: http://localhost:11434/v1
    api_key: ""
    enabled: true
    default_models:
      - llama3.2:3b
  - name: Azure OpenAI
    type: openai_compatible
    base_url: https://my-resource.openai.azure.com
    api_key: AZURE_OPENAI_KEY
    azure_deployment: gpt-4o-deployment
    azure_api_version: "2024-10-21"
    enabled: false
    default_models:
      - gpt-4o
```

## 11. Edge cases

| ID | Description | Handling |
|---|---|---|
| EC-IMP-1 | Import file is malformed YAML | Hard error; modal names the parse error; nothing applied. |
| EC-IMP-2 | `kind` mismatches the chosen import action | Hard error; import aborted before the preview. |
| EC-IMP-3 | `schema_version` newer than this build | Hard error; import aborted. |
| EC-IMP-4 | Settings file has unknown keys | Unknown keys ignored and listed in the preview's skipped group; known keys still import. |
| EC-IMP-5 | Settings value has the wrong type | That key is skipped with a soft warning; other keys import. |
| EC-IMP-6 | Provider entry missing `type` | That entry is dropped with a hard error; if it was the last entry, the import aborts. |
| EC-IMP-7 | Two provider entries share a `name` | Hard error; import aborted (DD-33; replaces the prior "duplicate id" handling). |
| EC-IMP-8 | `embedding.provider_name` does not match any provider entry's `name` | Hard error; import aborted. |
| EC-IMP-13 | A provider entry's `name` matches an existing row in `ProvidersStore.get_by_name` (add path, not full-replace) | Soft warning; entry skipped with reason "Duplicate name — already in catalog"; the rest of the import proceeds (DD-33, EC-PROV-13). |
| EC-IMP-9 | Literal secret value in an `api_key` field | Hard error for that entry (D-R-18): literal secrets are rejected; the entry must carry an environment-variable name; nothing literal is persisted. |
| EC-IMP-10 | Environment-variable name for an unset variable | Soft warning; imported as-is; resolved lazily at use time. |
| EC-IMP-11 | User cancels the preview dialog | Nothing is applied; current state unchanged. |
| EC-IMP-12 | Settings file with zero valid keys | Import allowed but a no-op; the preview states this. |
