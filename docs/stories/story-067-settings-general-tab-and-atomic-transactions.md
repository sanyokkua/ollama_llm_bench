---
id: STORY-067
title: Build the Settings General tab, cross-tab validation, and the atomic Save / Import / Reset transactions
status: ready
spec_clauses:
  - 06_Settings_Dialog/description.md#41-inference
  - 06_Settings_Dialog/description.md#46-display
  - 06_Settings_Dialog/description.md#6-save-flow-atomic
  - 06_Settings_Dialog/description.md#8-import-flow
  - 06_Settings_Dialog/description.md#9-reset-flow
  - 06_Settings_Dialog/description.md#10-close-flow
  - 06_Settings_Dialog/description.md#15-validation-rules
  - 06_Settings_Dialog/sub_dialogs/reset_confirmation.md#4-what-is-reset
  - 06_Settings_Dialog/sub_dialogs/reset_confirmation.md#6-the-bundled-default-seed
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway
  - 08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract
modules:
  - ui/settings_dialog/
acceptance_criteria:
  - STORY-067-AC-1
  - STORY-067-AC-2
  - STORY-067-AC-3
  - STORY-067-AC-4
  - STORY-067-AC-5
  - STORY-067-AC-6
edge_cases:
  - EC-SET-2
  - EC-SET-3
  - EC-SET-4
depends_on:
  - STORY-049
  - STORY-066
adrs:
  - ADR-0001
  - ADR-0008
owner: coder
estimate: L
---

# STORY-067 — Build the Settings General tab, cross-tab validation, and the atomic Save / Import / Reset transactions

## Goal

Complete the Settings dialog: the General tab as a scrollable column of sections whose every
control binds to exactly one user-saved setting key from the registry; the cross-tab validation
cascade (hard errors, soft warnings, and the cleared-numeric-field edge input); the atomic Save
transaction spanning the provider catalog and the app-settings layer; the Export and Import
flows with the Import preview sub-dialog; the Reset flow with the Reset confirmation sub-dialog;
and the dirty-guarded Close flow.

## In scope

- `_internal/general_tab/`: the section column and `field_binders.py` mapping each control to one
  `08-G` registry key (Inference, Benchmark Events, Evaluation, Judge/embedding timeouts,
  Run-level analysis, Embedding Models, Display, Logging Run/App, Storage, Task Editor).
- `_internal/validation.py`: the cross-tab cascade producing the hard-error / soft-warning
  findings and computing `save_enabled`, including the timeout-pair and cosine-threshold rules and
  the cleared-numeric-field-as-hard-error rule.
- `_internal/controller.py` transaction orchestration: the atomic Save (both stores through the
  gateway), the emitted `_provider_registry_reloaded` / `_app_settings_changed`, and the
  clean-after-save behaviour.
- The Export flow and the Import flow with `_internal/sub_dialogs/import_preview.py` (the
  Added/Changed/Unchanged/Skipped grouping and the replace-providers / merge-settings apply).
- `_internal/sub_dialogs/reset_confirmation.py` and the wipe-and-reseed Reset transaction; the
  Close flow with the Discard-changes confirmation.

## Out of scope

- The Settings shell, Providers tab, embedding selection, and Provider Edit sub-dialog — owned by
  STORY-066, which this story builds on.
- The concrete `AppSettingsStore` / `ProvidersStore` and the real SQLite transaction — consumed
  behind the gateway; the atomic-transaction integration test exercises the adapter+backend.
- Wiring the concrete `SettingsGateway` and mounting the dialog in `compose.py` — this story
  **must not touch** `compose.py` (Phase 11 owns it).

## Spec inputs

- `06_Settings_Dialog/description.md#41-inference` — the Inference-section controls and their
  registry keys (a representative binder section; the completeness rule covers every key).
- `06_Settings_Dialog/description.md#46-display` — the Theme and score-display keys.
- `06_Settings_Dialog/description.md#6-save-flow-atomic` — the single-transaction Save spanning
  both stores and the post-commit events and toast.
- `06_Settings_Dialog/description.md#8-import-flow` — the parse-validate-preview-apply sequence
  (replace providers, merge settings) and the unknown-key handling.
- `06_Settings_Dialog/description.md#9-reset-flow` — the wipe-and-reseed transaction and the
  discard-of-unsaved-edits.
- `06_Settings_Dialog/description.md#10-close-flow` — the clean immediate close and the dirty
  Discard-changes confirmation.
- `06_Settings_Dialog/description.md#15-validation-rules` — the hard errors, soft warnings, and
  the cleared-numeric-field edge input.
- `06_Settings_Dialog/sub_dialogs/reset_confirmation.md#4-what-is-reset` — exactly what a reset
  wipes and re-seeds.
- `06_Settings_Dialog/sub_dialogs/reset_confirmation.md#6-the-bundled-default-seed` — the three
  bundled local providers re-seeded with fresh UUID4 ids.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway` — `replace_providers`,
  `upsert_settings`, `list_settings`, `get_resolved_str`.
- `08_Cross_Cutting/08-D_color_palette_and_typography.md#16-the-theme-module-contract` — theme
  roles only.

## Design constraints

- The controller depends only on `SettingsGateway` plus the retained UI helpers; the persistence
  transaction is atomic across the provider catalog and the app-settings layer (D-R-06).
- Every General-tab control binds to exactly one `08-G` key; `field_binders.py` is the single
  place the registry-to-control mapping is declared.
- A failed Save/Import/Reset transaction writes nothing and leaves the dialog dirty; the
  post-commit `_provider_registry_reloaded` / `_app_settings_changed` events fire only on commit.
- A cleared numeric field is a hard error (treated as empty, never as zero); Save stays disabled.
- No `setStyleSheet`, no colour literal, no `asyncio`.
- The controller obtains its `structlog` logger at module scope (never inside `__init__`, per
  `logging.md`) and emits `DEBUG`-level events — static event name + keyword fields, never an
  f-string — at construction, at every Gateway call, at every `EventBus` handler invocation, and
  at every user-triggered state transition, so an anomaly is visible in `app.log` during
  development before it becomes a user-facing bug.

## Acceptance criteria

### STORY-067-AC-1

Given the General tab, when each control renders, then it binds to exactly one user-saved setting
key from the registry and round-trips its value through that key's storage text form; a control
never exists outside the registry.

### STORY-067-AC-2

For each validation input, the cross-tab cascade produces the specified severity and Save
enablement:

| Input                                                             | Severity     | Save     |
| ----------------------------------------------------------------- | ------------ | -------- |
| Two providers share a Name                                        | hard error   | disabled |
| `benchmark.max_timeout_seconds` < `benchmark.min_timeout_seconds` | hard error   | disabled |
| A numeric field cleared / out of range                            | hard error   | disabled |
| An env-var name whose variable is unset                           | soft warning | allowed  |
| No findings and the dialog is dirty                               | —            | enabled  |

### STORY-067-AC-3

Given a dirty dialog with no hard error, when the user clicks Save Changes, then the working
provider catalog and the app-settings values are written in one transaction through the gateway,
and on commit `_provider_registry_reloaded` and `_app_settings_changed` are emitted and the
dialog becomes clean.

### STORY-067-AC-4

Given an import file with keys the build does not know, when the Import preview renders, then the
unknown keys appear in the Skipped/ignored group and the recognised keys still import on confirm.

### STORY-067-AC-5

Given the user confirms Reset to Defaults, when the reset transaction runs, then every
`app_settings` and `providers` row is wiped and the three bundled local providers plus the
in-code setting defaults are re-seeded in one transaction, discarding any unsaved working edits.

### STORY-067-AC-6

Given the dialog is dirty, when the user clicks Close, then the Discard-changes confirmation is
shown and Cancel keeps the dialog open with the working copy intact; and given a clean dialog,
then Close dismisses it immediately.

## Test plan

- STORY-067-AC-1 — unit, colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_general_field_binders.py`,
  `test_each_control_binds_one_registry_key`.
- STORY-067-AC-2 — table-driven unit, colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_validation.py`,
  `test_validation_severity_and_save_enablement`. Covers EC-SET-3.
- STORY-067-AC-3 — integration, `tests/integration/test_settings_save.py`,
  `test_atomic_save_writes_both_and_emits_events`. Wrapped in `structlog.testing.capture_logs()`;
  asserts no captured entry's `log_level` is in `{"error", "critical"}`.
- STORY-067-AC-4 — unit (`pytest-qt`, fake `SettingsGateway`), colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_import_preview.py`,
  `test_unknown_keys_skipped_known_keys_import`. Covers EC-SET-2.
- STORY-067-AC-5 — integration, `tests/integration/test_settings_reset.py`,
  `test_reset_wipes_and_reseeds_atomically`. Covers EC-SET-4.
- STORY-067-AC-6 — unit (`pytest-qt`), colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_controller.py`,
  `test_close_flow_dirty_vs_clean`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-067.
- [ ] EC-SET-2, EC-SET-3, and EC-SET-4 each have a passing test.
- [ ] The `pytest-qt` suite reaches ≥60% branch coverage and exercises the Loaded / Dirty /
  Saving states and the Import-preview and Reset-confirmation sub-dialog states of
  `06_Settings_Dialog/state_machine.md`.
- [ ] An architecture test confirms the controller depends only on `SettingsGateway`, that every
  General-tab control maps to a single `08-G` key, and that the module references no
  `setStyleSheet`, embeds no colour literal, and imports no `asyncio`.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `ui/settings_dialog/`.
- [ ] `just trace` resolves this story's spec clauses; the record validates with no orphan clause
  and no orphan test for STORY-067.
- [ ] The module inventory is unchanged.
- [ ] The construction/interaction smoke test passes with zero ERROR/CRITICAL-level `structlog`
  records, and DEBUG-level lifecycle events are emitted per the design constraint above.

## Notes

- **SettingsGateway extension (confirmed with the user before implementation).** 08-E §7b.6's
  `SettingsGateway` listing has zero Import/Export methods; `backend/import_export`'s
  `ImportExportService` already implements exactly what's needed but is never listed among the
  seven 08-E §7b UI gateways. This story extends the locally-declared `SettingsGateway` in
  `ui/settings_dialog/protocols.py` with six methods shaped after `ImportExportService`'s real
  signatures (`build_settings_import_preview`, `apply_settings_import`,
  `build_provider_import_preview`, `apply_provider_import`, `export_settings`,
  `export_providers`), with locally-redeclared DTOs in `models.py` (never importing
  `backend.import_export` directly, per the `ui/*` import boundary). The DTOs use `TYPE_CHECKING`
  imports to avoid a `models.py` \<-> `protocols.py` import cycle (`models.py` needs
  `SettingsGateway` as a real runtime type for its own `msgspec.Struct` bundle fields, so
  `protocols.py` cannot import `models.py` eagerly). Flagged here for whoever wires the concrete
  `SettingsGateway` in Phase 11: route these six methods to the real `ImportExportService`, and
  consider amending 08-E §7b.6's own text to list them.
- **Reset's settings wipe is achieved via `upsert_settings` with the full defaults map**, not a
  dedicated "wipe" method — consistent with that method's own docstring ("the settings half of
  Save / Reset"). The concrete `AppSettingsStore.upsert_settings` implementation (Phase 11, out of
  scope here) is expected to actually delete-then-reinsert internally when serving Reset, matching
  `reset_confirmation.md` §7's literal wipe-and-reseed wording; this UI story cannot observe or
  enforce that internal behavior, only that the correct full-defaults map is passed. Verified
  against the real `SqliteProvidersStore.replace_providers` implementation
  (`backend/persistence/providers/_internal/store_impl.py`): it deletes every `providers` row and
  re-inserts each `ProviderConfig` verbatim by whatever `provider_id` it already carries — it does
  **not** generate a fresh UUID4 for an id-less row (there is no id-less row; `ProviderConfig`
  requires `provider_id`). The three bundled Reset rows and a session-added Add-Provider row alike
  carry a fresh `uuid.uuid4()` placeholder assigned at construction time (mirroring
  `provider_edit_view._blank_draft`'s established pattern), not a store-side generation step —
  08-E's own text describing `replace_providers` as generating ids for absent-id rows describes
  the *conceptual* contract, not this store implementation's literal mechanism.
- **Cross-store atomicity is validate-first, not 2PC.** Save/Reset/Import validate everything
  before either store write runs, then call `replace_providers` followed by `upsert_settings` in
  sequence with no rollback if the second call fails after the first succeeds. The real
  cross-store transaction (spanning both SQLite tables in one commit) is the concrete
  `SettingsGateway`/store implementation's responsibility (Phase 11) — out of scope here, per the
  story's own "Out of scope" section.
- **Storage-section paths derive from `FileSystemActions.exports_folder_path()`'s parent**, not a
  new Protocol method — `<app_data>/` is that call's parent directory; `<app_data>/logs/run/` and
  `<app_data>/logs/app/` are fixed relative subpaths per `description.md` §11. This resolution is
  wired lazily (only inside the four Storage/Logging action handlers, never at dialog-open/reload
  time) so an unconfigured `FileSystemActions` test double never has `exports_folder_path()`
  called against it unless a test actually exercises Copy/Open-folder — the read-only path label
  itself (`GeneralTabView.set_app_data_path`) is therefore not yet auto-populated at dialog open;
  wiring that render call is left for the Phase 11 concrete-adapter story to pair with the real
  `FileSystemActions` adapter's `exports_folder_path()`.
- **`SettingsDialogCollaborators` relocated from `api.py` to `models.py`** (STORY-066 originally
  declared it in `api.py`). `_internal/controller.py` needs the whole collaborator bundle as a
  single constructor parameter to respect coding-style.md's 4-parameter hard maximum
  (`collaborators`, `providers_controller`, `general_tab_controller`), and `_internal/` may never
  import `..api` (a cycle) — so the bundle now lives in `models.py`, and `api.py` re-imports and
  re-exports it unchanged; no external caller-visible change.
- **`ProvidersTabController.working_configs`** — a new public read-only property added to the
  STORY-066 file `_internal/providers_tab/controller.py`, exposing the in-memory provider catalog
  STORY-067's Save/Reset/validation cascade needs to read. An in-scope, additive change to an
  existing STORY-066 file, not new scope creep.
- **Import-provider-configuration** (`on_import_provider_config_clicked`) is implemented on the
  controller (§8's provider-config import path, using `build_provider_import_preview`/
  `apply_provider_import`), but the footer's `Import…` button (STORY-067-AC-4's own AC text) wires
  only to the settings-import path (`on_import_clicked`); the mockup shows a single `Import…`
  footer action per dialog, and this story's acceptance criteria describe only the settings-import
  preview flow. Wiring a second entry point (e.g. a Providers-tab-local "Import provider config…"
  action) for the already-implemented `on_import_provider_config_clicked` method is left for a
  follow-up story if the mockup's single `Import…` button is meant to detect file kind and branch,
  which `10_Domain_and_Data/06_IMPORT_FORMATS.md` does not resolve explicitly.

### Spec-conformance review fixes (post-implementation amendment)

An independent spec-conformance review returned "CONFORMS WITH CONCERNS" — four real gaps,
fixed in place in this same story (not split into a new story):

- **`SettingsGateway.save_all`/`reset_to_defaults` replace the two-call Save/Reset sequence.**
  The original implementation called `replace_providers` then `upsert_settings` (Save), and
  `replace_providers` then `upsert_settings` with no error handling at all (Reset), as two
  independent void Gateway calls with no rollback — a failure after the first call committed
  left the two stores inconsistent, and a Reset failure crashed instead of leaving the prior
  configuration intact (`sub_dialogs/reset_confirmation.md` §7). `protocols.py` now declares
  `save_all(*, providers, settings_values)` and `reset_to_defaults(*, bundled_providers)`; both
  are documented as all-or-nothing, giving the concrete Phase 11 adapter a single call to wrap
  in one real database transaction (something two independent void calls cannot express).
  `on_save_clicked`/`on_reset_clicked` now call only these two methods, each in its own
  `try/except PersistenceError` (Reset previously had none). `FakeSettingsGateway` models the
  atomicity a fake can guarantee: a scripted `raise_on_next_save_all`/
  `raise_on_next_reset_to_defaults` raises *before* mutating `_providers`/`_settings`, so a test
  can assert nothing was recorded on failure (`test_fake_gateway.py`). The original
  `replace_providers`/`upsert_settings` methods are kept — `apply_settings_import` still calls
  `upsert_settings` and Import needs them untouched.
  - **On the "full settings defaults" map**: `backend.settings._internal.registry.DEFAULTS` is
    exactly this exhaustive in-code defaults table (confirmed by reading the file), but it lives
    in `_internal/` and is not part of `backend.settings`'s public `api.py`/`__init__.py`
    surface, and `ui/settings_dialog` cannot import a sibling `_internal` package regardless.
    `reset_to_defaults`'s docstring names this table explicitly so Phase 11's implementer knows
    what the concrete adapter should reseed against (promoting it to a public export, or
    duplicating its shape the same way `backend/import_export/_internal/settings_key_catalog.py`
    already duplicates the same spec section) — covering every opaque key
    (`ui.window_geometry`, `benchmark.last_mode`, `ui.splitter_sizes`, etc.) the General tab's own
    `_DEFAULT_STORAGE_TEXT` map in `_internal/general_tab/controller.py` never claimed to cover.
- **Export now writes the provider catalog, not just settings.** `description.md` §7 states the
  export carries "the provider catalog, the embedding selection, and every user-saved setting
  key" as a single action, but `08-E`/`backend.import_export` define `export_settings`/
  `export_providers` as two independent, self-contained YAML documents (`kind: settings` /
  `kind: provider_config`) — there is no combined-export shape anywhere in
  `backend/import_export/_internal/service.py` to mirror (verified by reading it: it exposes
  only the two separate bytes-producing methods, contradicting this fix's original assumption
  that a combined shape already existed). `on_export_clicked` now calls both
  `export_settings()` and `export_providers()` and writes two sibling files from the one Export
  action (the user-chosen path, plus a `*_providers.yaml` path derived from it) — one user
  action still produces the full configuration on disk without inventing a third combined
  schema or touching `backend/import_export`.
- **`ProvidersTabController` now notifies the parent controller after every mutation.** Its
  mutation handlers (`on_test_clicked`, `on_enabled_toggled`, `on_add_clicked`, `on_edit_clicked`,
  `on_reset_clicked`, `on_delete_clicked`, `apply_readiness_refresh`) all funnel through the
  single shared `_rebuild()` tail call; `_rebuild()` now also invokes a `set_on_changed`
  callback (a plain `Callable[[], None]`, not a Qt `Signal` — `ProvidersTabController` is not a
  `QObject` and no other feature controller in this codebase uses a Qt Signal for
  inter-controller notification, so a plain callback matches the established idiom more closely
  than introducing one). `api.py` wires `providers_controller.set_on_changed(controller. on_providers_changed)`, a new public `SettingsController` method that calls the existing
  private `_push_chrome()`. Previously the dialog chrome (dirty asterisk, save-state text,
  Save-button enablement) went stale after a Providers-tab-only change until an unrelated
  General-tab edit happened to trigger the next `_push_chrome()`.
- **The Reset button now carries the theme's new `destructive-button` role.**
  `08-D_color_palette_and_typography.md` explicitly documents `error.base`/`text.on-error` as
  backing "destructive action"/"destructive button label", so `ui/theme/_internal/ stylesheet_builder.py` gained a `QPushButton[role="destructive-button"]` rule using exactly
  those two existing color tokens (no new token fields added — `ColorTokens` has no
  `error_hover`/`error_pressed`/`error_disabled` fields to draw a multi-state role from, unlike
  `primary-button`). `reset_confirmation_view.py`'s Reset button now sets this role instead of
  `primary-button`, satisfying `reset_confirmation.md` §3's "Styled as the destructive action".
- **EC-SET-4 citation verified, not removed.** The review flagged a possible misattribution, but
  `14_Process_and_Traceability/06_EDGE_CASE_TO_TEST_MAPPING.md` (the canonical mapping) scopes
  `EC-SET-4` to `ui/settings_dialog/` as "Reset to Defaults with unsaved edits shows a
  confirmation" — exactly what this story's `test_reset_wipes_and_reseeds_atomically` already
  covers. A *different* "EC-SET-4" (Settings blocked mid-run) exists in
  `06_Settings_Dialog/description.md`/`state_machine.md` and `01_Main_Window/*` — an apparent
  duplicate-ID reuse across unrelated features in the vendored spec, out of this story's scope
  to fix (it would mean editing the read-only vendored spec). This story's own citation is
  correct per the authoritative mapping table and is left unchanged.
- Deferred per explicit instruction, not fixed here: EC-SET-3's "cleared numeric field is only
  testable at the pure-function level, not through a real `QSpinBox`" limitation (a genuine Qt
  widget constraint — `QSpinBox` cannot be blanked).
