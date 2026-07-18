---
id: STORY-066
title: Build the Settings dialog shell, Providers tab, embedding selection, and the Provider Edit sub-dialog
status: ready
spec_clauses:
  - 06_Settings_Dialog/description.md#32-provider-table
  - 06_Settings_Dialog/description.md#33-per-row-actions
  - 06_Settings_Dialog/description.md#34-embedding-section
  - 06_Settings_Dialog/description.md#12-provider-authentication-model
  - 06_Settings_Dialog/description.md#14-auto-check-on-open-and-embedding-bootstrap
  - 06_Settings_Dialog/sub_dialogs/provider_edit.md#51-entry-validation-inline
  - 06_Settings_Dialog/sub_dialogs/provider_edit.md#82-test-inference
  - 06_Settings_Dialog/sub_dialogs/provider_edit.md#9-validation
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/settings_dialog/
acceptance_criteria:
  - STORY-066-AC-1
  - STORY-066-AC-2
  - STORY-066-AC-3
  - STORY-066-AC-4
  - STORY-066-AC-5
  - STORY-066-AC-6
  - STORY-066-AC-7
  - STORY-066-AC-8
edge_cases:
  - EC-PROV-5
  - EC-PROV-6
  - EC-PROV-7
  - EC-PROV-10
  - EC-PROV-11
  - EC-PROV-5b
  - EC-PROV-5c
depends_on:
  - STORY-049
  - STORY-051
  - STORY-052
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-066 — Build the Settings dialog shell, Providers tab, embedding selection, and the Provider Edit sub-dialog

## Goal

Deliver the Settings dialog shell (modal `QDialog`, tab strip, footer with the dirty indicator,
the in-memory working copy, and the auto-check-on-open readiness request), the Providers tab
(the provider table with health dots and auth badges, the per-row actions, and the embedding
selection section built on the shared dropdowns), and the Provider Edit sub-dialog (the
env-var-name credential card with inline entry validation, the Test reachability and Test
inference panels bound to the single-inference gate, and the duplicate-name validation). The
General tab and the Save/Import/Reset transactions are added by STORY-067.

## In scope

- `ui/settings_dialog/protocols.py`: the `SettingsGateway` Protocol declared locally with the
  exact method signatures of 08-E §7b.6.
- `ui/settings_dialog/api.py`: `make_settings_dialog(...) -> QDialog`, the `SettingsController`,
  the working-copy model with its dirty diff, and the `_app_readiness_changed` subscription and
  auto-check-on-open request.
- `_internal/providers_tab/`: the `QAbstractTableModel` over `ProviderRow` tuples (health dot,
  auth badge, enabled toggle), the per-row actions (Test connection reachability-only, Edit,
  Reset-this-provider, Delete), and the embedding section (shared provider/model dropdowns, the
  Show-all-models filter toggle, and Test Embedding).
- `_internal/sub_dialogs/provider_edit.py`: the identity/endpoint fields, the API-key secret card
  holding only an environment-variable name with inline entry validation, the Test reachability
  and Test inference panels (the latter gate-bound to `PROVIDER_TEST` with the model-required and
  cloud-billing rules), the live duplicate-name check, and the return-working-row-on-Save.

## Out of scope

- The General tab and its field binders — owned by STORY-067.
- The atomic Save / Import / Reset transactions, the Reset confirmation sub-dialog, and the
  Import preview sub-dialog — owned by STORY-067.
- The concrete `ProvidersStore` / `ProviderRegistry` / `ReadinessService` — consumed behind the
  gateway; the shared dropdowns consume `ProviderRegistry` through themselves.
- Wiring the concrete `SettingsGateway` in `compose.py` — this story **must not touch**
  `compose.py` (Phase 11 owns it).

## Spec inputs

- `06_Settings_Dialog/description.md#32-provider-table` — the columns, the health-dot statuses,
  the auth badge states, and the enabled toggle marking the dialog dirty.
- `06_Settings_Dialog/description.md#33-per-row-actions` — Test connection (reachability only),
  Edit, per-row Reset (revert to persisted), and Delete.
- `06_Settings_Dialog/description.md#34-embedding-section` — the single-pair embedding selection
  built on the shared dropdowns and the Test Embedding probe.
- `06_Settings_Dialog/description.md#12-provider-authentication-model` — credentials stored as an
  environment-variable NAME only; the auth-badge resolution.
- `06_Settings_Dialog/description.md#14-auto-check-on-open-and-embedding-bootstrap` — the
  readiness refresh on open and the first-start embedding bootstrap.
- `06_Settings_Dialog/sub_dialogs/provider_edit.md#51-entry-validation-inline` — the API-key
  field accepts only a valid env-var name or empty; a literal secret is rejected inline.
- `06_Settings_Dialog/sub_dialogs/provider_edit.md#82-test-inference` — the model-required,
  cloud-billing-warning, and gate-bound Test inference panel.
- `06_Settings_Dialog/sub_dialogs/provider_edit.md#9-validation` — the hard-error / soft-warning
  Save-validation table, including the duplicate-name rule.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway` — `list_providers`,
  `get_provider_by_name`, `test_provider`, `discover_models`, `probe_all`, `probe_embedding`,
  `readiness_snapshot`.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#13-inference-activity-store` — the gate the Test
  actions acquire as `PROVIDER_TEST` and bind their buttons to.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The controller and the sub-dialog depend only on `SettingsGateway` plus the retained UI helpers
  (`EventBus`, `NativePickers`, `Clipboard`, `FileSystemActions`, `NotificationService`) and the
  redaction functions; no backend store/service Protocol reaches the controller (D-R-06).
- `provider_id` is never displayed, entered, or copied; the Name is the sole unique-identifier
  input; historical run references stay valid across a rename.
- The API-key field can only ever hold an environment-variable name or be empty; a literal secret
  never reaches the working copy or the database.
- The Test actions run against the in-memory working copy, never the persisted value.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-066-AC-1

For each `ProviderTestStatus`, the provider row renders the specified health dot and, for the
auth field, the specified badge:

| Signal                    | Health dot | Auth badge                       |
| ------------------------- | ---------- | -------------------------------- |
| READY                     | success    | env ✓ (name set and resolves)    |
| ZERO_MODELS               | warning    | env ✓                            |
| UNREACHABLE / MISSING_ENV | error      | env ✗ (name set, variable unset) |
| UNTESTED                  | muted      | none (no name set)               |

### STORY-066-AC-2

Given the Provider Edit API-key field, when the user types a value that is not a valid
environment-variable name (`[A-Za-z_][A-Za-z0-9_]*`) and is non-empty, then the field shows the
inline "enter the NAME of an environment variable" error and Save is blocked; and when the value
is a valid name or empty, then the field is accepted.

### STORY-066-AC-3

Given the Provider Edit dialog, when the user types a Name that duplicates another working row's
Name or a persisted Name returned by `SettingsGateway.get_provider_by_name`, then the Name field
shows "A provider with this name already exists." and Save is disabled.

### STORY-066-AC-4

Given the Test inference panel, when no model is selected in the dropdown and the manual-entry
toggle is off (or its typed text is empty after trim), then the Run inference test button is
disabled; and when a model is named, then it is enabled (subject to the gate).

### STORY-066-AC-5

Given the single-inference gate is held by an activity other than `PROVIDER_TEST`, when the Test
reachability and Test inference buttons render, then both are disabled with the in-flight
tooltip; and when `_inference_activity_changed` reports the gate `IDLE`, then they re-enable.

### STORY-066-AC-6

Given the user clicks Test connection on a provider row, when the probe runs, then it calls
`SettingsGateway.test_provider` against the row's in-memory working copy (never the persisted
value) and paints the resulting status onto the row's health dot.

### STORY-066-AC-7

Given the Settings dialog opens, when it enters its Opening state, then it issues a
`SettingsGateway.probe_all()` request and repaints each provider health dot and the embedding
diagnostic from the resulting `_app_readiness_changed` snapshot.

### STORY-066-AC-8

Given the dialog is constructed via its own factory function (`make_settings_dialog`) with a
fake `SettingsGateway` (and fakes for the declared collaborators `EventBus`, `NativePickers`,
`Clipboard`, `FileSystemActions`, and `NotificationService`) and mounted under `qtbot`, when it
is shown (`qtbot.addWidget(...)`, `.show()`, one `qtbot.wait(0)`/event-loop pump), then no
exception is raised, the dialog reports `isVisible()`, and no `error`/`critical`-level
`structlog` record is captured — verified by wrapping construction+show in
`structlog.testing.capture_logs()` and asserting no captured entry's `log_level` is in
`{"error", "critical"}`.

## Test plan

- STORY-066-AC-1 — table-driven unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_provider_table_model.py`,
  `test_health_dot_and_auth_badge_per_status`. Covers EC-PROV-6.
- STORY-066-AC-2 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_provider_edit.py`,
  `test_api_key_field_rejects_non_env_var_name`. Covers EC-PROV-7.
- STORY-066-AC-3 — unit (`pytest-qt`, fake `SettingsGateway`), same file,
  `test_duplicate_name_blocks_save`. Covers EC-PROV-10, EC-PROV-11.
- STORY-066-AC-4 — unit (`pytest-qt`), same file,
  `test_run_inference_disabled_until_model_named`. Covers EC-PROV-5c.
- STORY-066-AC-5 — unit (`pytest-qt`), same file,
  `test_test_buttons_gated_on_inference_activity`. Covers EC-PROV-5b.
- STORY-066-AC-6 — unit (`pytest-qt`, fake `SettingsGateway`), colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_controller.py`,
  `test_test_connection_probes_working_copy`. Covers EC-PROV-5.
- STORY-066-AC-7 — unit (`pytest-qt`), same file,
  `test_auto_check_on_open_requests_probe_all`.
- STORY-066-AC-8 — unit (`pytest-qt`, fake `SettingsGateway`), colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_controller.py`,
  `test_settings_dialog_constructs_and_shows_with_no_error_logs`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-066.
- [ ] EC-PROV-5, EC-PROV-5b, EC-PROV-5c, EC-PROV-6, EC-PROV-7, EC-PROV-10, and EC-PROV-11 each
  have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Providers-tab and
  Provider Edit states of `06_Settings_Dialog/state_machine.md` and
  `06_Settings_Dialog/sub_dialogs/provider_edit.md`; the provider table model passes
  `QAbstractItemModelTester`.
- [ ] An architecture test confirms the controller and sub-dialog depend only on `SettingsGateway`
  (no backend store/service Protocol), that a literal secret can never reach the working copy,
  and that the module references no `setStyleSheet`, embeds no colour literal, and imports no
  `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/settings_dialog/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-066.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.
