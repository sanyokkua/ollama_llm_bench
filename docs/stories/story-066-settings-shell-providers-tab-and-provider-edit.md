---
id: STORY-066
title: Build the Settings dialog shell, Providers tab, embedding selection, and the Provider Edit sub-dialog
status: done
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

For each `ProviderTestStatus`, the provider row renders the specified health dot:

| Signal                    | Health dot |
| ------------------------- | ---------- |
| READY                     | success    |
| ZERO_MODELS               | warning    |
| UNREACHABLE / MISSING_ENV | error      |
| UNTESTED                  | muted      |

Independently of the health dot — never derived from `ProviderTestStatus` — the Auth badge is a
pure function of the row's credential-resolution state alone (`description.md` §3.2, §12):

| Auth-field state                                                    | Auth badge |
| ------------------------------------------------------------------- | ---------- |
| No env-var name configured (e.g. the three bundled local providers) | none       |
| An env-var name is configured and resolves to a non-empty value     | env ✓      |
| An env-var name is configured but is unset or empty                 | env ✗      |

A `READY` provider with no key field still shows `none`; an `UNREACHABLE` provider whose key
resolves still shows `env ✓`. The two axes never influence one another.

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

## Notes

Recorded during a post-implementation spec-conformance fix pass (four fixes applied: the
Auth-badge derivation, the Test Embedding control, the embedding-dropdown bootstrap, and this
Notes section). The following are known, deliberately accepted limitations of this story's
implementation, out of scope to fix here:

- **AC-6's "probes the in-memory working copy, never the persisted value" guarantee cannot be
  structurally proven.** `SettingsGateway.test_provider(provider_id, model_name)` (08-E §7b.6,
  cited verbatim in `protocols.py`) takes only a `provider_id` — there is no channel to pass
  working-copy field values (an edited-but-unsaved `base_url`, API-key env-var name, etc.)
  through to the probe. The dialog can call `test_provider` with the right `provider_id` at
  the right moment, but whether the *concrete* Gateway implementation actually probes the
  edited-in-memory fields or silently re-reads the last-persisted row for that id is entirely
  up to that implementation — nothing in this Protocol's signature lets the UI layer prove or
  even influence which one happens. This is a tension in the spec-cited Gateway contract
  itself, not a UI-layer bug. Flag it for whoever wires the concrete `SettingsGateway` in
  Phase 11: either add a working-copy-aware overload/parameter, or make Save-before-Test the
  documented contract for an edited-but-unsaved field. This story does not invent an unspec'd
  method signature to route around it.
- **The same class of tension applies to `SettingsGateway.probe_embedding()`.** Its 08-E §7b.6
  signature takes no arguments, so the Test Embedding button cannot pass it the in-memory
  working-copy `(provider, model)` pair the dropdowns currently show — the concrete
  implementation decides on its own which pair it actually probes. Flag this alongside the
  `test_provider` tension above for whoever wires the concrete `SettingsGateway` in Phase 11.
- **Provider Edit's §8.2 live in-flight progress sub-state is not implemented.** Only the
  settled probe outcome renders in the result label; the two-line "testing — waiting for
  response" / "testing — receiving tokens" indicator, the amber gate-busy strip, and the
  footer note described in §8.2 are absent. No AC/EC this story cites requires the live
  indicator, so this is an accepted scope deferral, not a defect.
- **Azure-specific secret-card fields are out of scope for this story.** `provider_edit.md`
  §6.2 (the Azure endpoint/deployment/API-version fields) is not a cited anchor for this
  story, so the corresponding §9 Azure-config-field validation rows are also unimplemented.
  Noted explicitly here so a later story (STORY-067 or beyond) does not silently skip them too.

### Spec-conformance fix pass (this session)

- The Auth badge (`env ✓` / `env ✗` / `none`) was corrected to derive purely from
  credential-resolution state (`ProviderConfig.api_key_raw` plus whether that named
  environment variable resolves) — never from `ProviderTestStatus`. `provider_auth_badge` in
  `_internal/view_model_select.py` is now the single source of truth for the badge; the Health
  Dot (`provider_test_status_to_health`) is a separate, independent pure function of
  `ProviderTestStatus` alone. `ProvidersTabController` resolves each row's credential via
  `os.environ.get(config.api_key_raw)` at rebuild time, matching the same pattern already used
  by `sub_dialogs/provider_edit_view.py`'s API-key diagnostic and
  `backend.provider_registry`'s client builder — `SettingsGateway.get_resolved_str` was not
  used for this, because its declared contract (08-E §7b.6) is "resolve the current effective
  value of a general-tab key", not an arbitrary per-provider environment-variable name.
- The embedding section (`_internal/providers_tab/embedding_section.py`) gained a Test
  Embedding button, gated on the single-inference activity store exactly like the Provider
  Edit Test buttons, calling `SettingsGateway.probe_embedding()` (which takes no arguments —
  it is not possible to pass it the in-memory working-copy pair the dropdowns currently show,
  the same class of Gateway-signature limitation noted above for `test_provider`) and
  rendering the result via the same `embedding_diagnostic_text` function the auto-check-on-open
  probe already uses.
- The embedding provider/model dropdowns now initialise from
  `embedding.selected_provider_name` / `embedding.selected_model_name` at construction time,
  falling back to a first-start bootstrap search (`resolve_embedding_bootstrap_pair`) that
  walks every enabled provider in catalog order and selects the first embedding-likely model
  found, leaving the pair empty when no enabled provider offers one.
