# Settings Dialog — Implementation Structure

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder
**Last Updated:** 2026-05-22
**Cross-references:**
`06_Settings_Dialog/description.md`,
`06_Settings_Dialog/state_machine.md`,
`06_Settings_Dialog/flow_diagram.md`,
`06_Settings_Dialog/sub_dialogs/provider_edit.md`,
`06_Settings_Dialog/sub_dialogs/reset_confirmation.md`,
`08_Cross_Cutting/08-E_interfaces_contracts.md`,
`08_Cross_Cutting/08-G_feature_flags.md`,
`08_Cross_Cutting/08-J_event_bus_catalog.md`,
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`,
`16_Engineering_Standards/01_PROJECT_STRUCTURE.md`,
`16_Engineering_Standards/03_CODING_STANDARDS.md`

This document specifies the implementation structure of the Settings Dialog as a
module: its package path, its public API, its internal MVC-family layout, the
view-model `msgspec.Struct` it renders, the controller and its subscriptions, the
factory wiring example, the dependency Protocols it consumes, the store-fanout
assessment, and the test boundary. It defines structure, not implementation code;
it follows the module framework fixed in
`16_Engineering_Standards/01_PROJECT_STRUCTURE.md`.

---

## Table of Contents

1. Module path
2. Public API
3. Sub-modules
4. View-model Struct
5. Controller
6. Factory wiring example
7. Dependency Protocols
8. Stores fanout assessment
9. Test boundary

---

## 1. Module path

```
src/ollama_llm_bench/ui/settings_dialog/
```

The Settings Dialog is a feature module under the PySide6 UI layer. It is large
enough to warrant sub-feature packages: it owns two tab bodies and three modal
sub-dialogs (Provider Edit, Reset confirmation, Import preview), and its
working-copy state is non-trivial. Per the module framework
(`16_Engineering_Standards/01_PROJECT_STRUCTURE.md`), a feature is split into
sub-feature packages when its public surface would exceed five files or its
`_internal/` would exceed roughly 1500 lines; the Settings Dialog crosses that
line, so the two tabs and the sub-dialog stack are organised as sub-packages
under `_internal/`.

```
src/ollama_llm_bench/ui/settings_dialog/
    __init__.py                  # re-exports the public surface; literal __all__
    api.py                       # make_settings_dialog(...) -> QDialog
    models.py                    # SettingsViewModel, ProviderRow, working-copy DTOs
    _internal/
        controller.py            # SettingsController — working copy, dirty tracking, Save/Import/Reset orchestration
        dialog.py                # the QDialog shell: title bar, tab strip, tab body host, footer
        validation.py            # cross-tab validation cascade (description.md §15)
        working_copy.py          # the mutable in-memory configuration model + dirty diff against persisted state
        providers_tab/
            __init__.py
            view.py              # the Providers tab QWidget tree
            provider_table_model.py  # QAbstractTableModel over ProviderRow tuples
            embedding_section.py # the embedding provider/model pickers + Test Embedding control
        general_tab/
            __init__.py
            view.py              # the General tab scrollable column of sections
            field_binders.py     # binds each control to one user-saved setting key from 08-G
        sub_dialogs/
            __init__.py
            provider_edit.py     # the Provider Edit modal (sub_dialogs/provider_edit.md)
            reset_confirmation.py# the Reset confirmation modal (sub_dialogs/reset_confirmation.md)
            import_preview.py    # the Import preview modal (10_Domain_and_Data/06_IMPORT_FORMATS.md §8)
    tests/
        test_controller.py
        test_working_copy_dirty.py
        test_validation.py
        test_provider_table_model.py
        test_general_field_binders.py
        test_provider_edit.py
        test_import_preview.py
```

The module is a UI-layer module: it imports the backend Protocols from
`08_Cross_Cutting/08-E_interfaces_contracts.md` and the DTOs from
`10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, and it never imports a concrete
backend implementation class.

## 2. Public API

The module's only public entry point is a modal-dialog factory in `api.py`:

```python
def make_settings_dialog(
    *,
    bus: EventBus,
    gateway: SettingsGateway,
    native_pickers: NativePickers,
    clipboard: Clipboard,
    file_system_actions: FileSystemActions,
    notifications: NotificationService,
    parent: QWidget,
) -> QDialog:
    """Build the Settings Dialog as a modal QDialog parented to the main
    window, fully wired to its controller, and return it ready to exec.
    All dependencies are passed by keyword.
    """
```

The factory constructs the controller, the dialog shell, the two tab views, and
the provider table model; it wires the controller's Event Bus subscription with
owner-binding to the returned dialog; and it returns the dialog. The three modal
sub-dialogs (Provider Edit, Reset confirmation, Import preview) are constructed
on demand by the controller from the `_internal/sub_dialogs/` package and are not
part of this module's public API.
The dialog is opened by the Main Window's Settings menu action, which is itself
gated by the run-state policy in `08_Cross_Cutting/08-H_app_modes.md` §10.

## 3. Sub-modules

The module splits into three sub-feature packages plus a flat set of shared
`_internal/` files. The split is by surface, not by file count alone: each tab
and the sub-dialog stack are independently testable and have no compile-time
dependency on one another.

| Package / file | Responsibility |
|---|---|
| `controller.py` | Owns the `SettingsViewModel` and the `working_copy`, tracks the dirty diff, orchestrates the Save / Import / Reset transactions, opens sub-dialogs, and emits the post-commit Event Bus signals. |
| `dialog.py` | Builds and owns the `QDialog` shell — the tab strip, the tab body host, and the footer — and renders a view-model into it. Holds no domain logic. |
| `validation.py` | The cross-tab validation cascade: hard errors, soft warnings, and the edge inputs of `description.md` §15. Pure functions over the working copy. |
| `working_copy.py` | The mutable in-memory configuration: the provider catalog, the embedding selection, and the general-tab setting values, plus the diff against the last-persisted state that defines the dirty flag. |
| `providers_tab/` | The Providers tab — the provider table model, the per-row actions, and the embedding section with the Test Embedding probe. |
| `general_tab/` | The General tab — the scrollable section column and the binders that map each control to exactly one user-saved key from `08_Cross_Cutting/08-G_feature_flags.md`. |
| `sub_dialogs/` | The three modal sub-dialogs, each its own file. Only one is ever open at a time (`state_machine.md` §5). |

No control in `general_tab/` exists outside the `08-G` registry; the
`field_binders.py` file is the single place the registry-to-control mapping is
declared, so adding a setting key means editing the registry and this one file.

## 4. View-model Struct

The displayed state is one immutable view-model the controller rebuilds on every
change and pushes into the dialog shell.

```python
class SettingsViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    active_tab: SettingsTab               # PROVIDERS | GENERAL
    dirty: bool                           # any field differs from the persisted value
    save_enabled: bool                    # dirty and no hard validation error
    saving: bool                          # the atomic transaction is committing
    provider_rows: tuple[ProviderRow, ...]
    embedding_provider_id: str | None
    embedding_model: str | None
    embedding_diagnostic: str | None      # last Test Embedding result, redacted for display
    general_values: tuple[GeneralFieldState, ...]
    validation_errors: tuple[ValidationFinding, ...]
    app_data_path: str                    # resolved app-data root for the Storage section


class ProviderRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    provider_id: str
    label: str
    provider_type: ProviderType           # OPENAI_COMPATIBLE | ANTHROPIC | GEMINI
    base_url_display: str                 # resolved URL, "(default)", or the resolved Azure endpoint URL
    auth_badge: ProviderAuthBadge         # ENV_OK | ENV_MISSING | NONE
    health: ProviderTestStatus            # READY | ZERO_MODELS | UNREACHABLE | MISSING_ENV | UNTESTED | TESTING
    enabled: bool
    has_unsaved_edits: bool               # row carries a working diff against the persisted value
    is_session_added: bool                # row added this session, never persisted


class GeneralFieldState(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    setting_key: str                      # a key from 08-G_feature_flags.md
    value: str                            # text form, per the 08-G storage convention
    has_error: bool


class ValidationFinding(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    severity: Severity                    # HARD_ERROR | SOFT_WARNING
    target: str                           # the control or row the finding attaches to
    message: str
```

The view-model carries no `LLMClient`, no persistence-store handle, and no mutable
collection — it is a pure render target. The `ProviderType`, `ProviderTestStatus`,
and `Severity` enums are defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`;
`SettingsTab` and `ProviderAuthBadge` are module-owned view enums declared in
`models.py`.

## 5. Controller

`SettingsController` owns the working copy and the view-model. Its
responsibilities:

- **Working-copy ownership.** On `Opening` it reads the provider catalog and
  the embedding selection (`gateway.list_providers`), the user-saved settings
  (`gateway.list_settings`, with `gateway.get_resolved_str` for typed effective
  values), and the observed model-capability cache (`gateway.list_model_capabilities`)
  into `working_copy` — all through the `SettingsGateway`. Every editable change
  mutates the working copy and triggers a dirty-diff recompute.
- **Dirty tracking.** The dirty flag is the diff between `working_copy` and the
  last-persisted snapshot; reverting every change manually re-cleans the dialog
  without a Save (`state_machine.md` §4).
- **Validation.** It runs `validation.py` over the working copy before every
  Save and computes `save_enabled`.
- **Transaction orchestration.** It drives the atomic Save, Import, and Reset
  transactions (`flow_diagram.md` §A, §C, §D). Every provider credential field
  holds only an environment-variable name (entry validation in Provider Edit
  guarantees this), so there is no secret-handling step before a transaction.
- **Sub-dialog control.** It opens exactly one sub-dialog at a time and folds the
  result back into the working copy.
- **Event emission.** After a committed Save, Import, or Reset it emits
  `_provider_registry_reloaded` and `_app_settings_changed`.

**Event Bus subscription.** The controller subscribes to one signal:

| Signal | Handler effect |
|---|---|
| `_app_readiness_changed` | Repaints each `ProviderRow.health` Health Dot and the embedding diagnostic from the new `AppReadinessSnapshot`. |

The subscription is owner-bound to the dialog so it is released when the dialog
closes. The auto-check on open is a `gateway.probe_all()` request the
controller issues during `Opening`; its result arrives through the same
`_app_readiness_changed` handler (`11_Services_and_Algorithms/09_READINESS_PROBE.md`
§6.6).

## 6. Factory wiring example

The composition root invokes the factory when the Main Window's Settings action
fires:

```python
# in the Main Window's settings-action handler
dialog = make_settings_dialog(
    bus=container.event_bus,
    gateway=container.settings_gateway,
    native_pickers=container.native_pickers,
    clipboard=container.clipboard,
    file_system_actions=container.file_system_actions,
    notifications=container.notification_service,
    parent=main_window,
)
dialog.exec()      # modal; blocks until the dialog closes
```

The factory itself wires the internals:

```python
def make_settings_dialog(*, bus, gateway,
                         native_pickers, clipboard, file_system_actions,
                         notifications, parent) -> QDialog:
    controller = SettingsController(
        gateway=gateway,
        native_pickers=native_pickers, clipboard=clipboard,
        file_system_actions=file_system_actions,
        bus=bus, notifications=notifications,
    )
    dialog = SettingsDialogShell(controller=controller, parent=parent)
    controller.bind_view(dialog)
    bus.subscribe("_app_readiness_changed",
                  controller.on_readiness_changed, owner=dialog)
    controller.load()      # enters the Opening state; requests the readiness refresh
    return dialog
```

## 7. Dependency Protocols

The controller is constructed with these interfaces; full contracts are in
`08_Cross_Cutting/08-E_interfaces_contracts.md`.

| Protocol | Used for |
|---|---|
| `SettingsGateway` | The adapter gateway (08-E §7b.6) exposing the dialog's provider-catalog / settings / capability / probe surface: `list_providers`, `get_provider_by_name` (live duplicate-name check), `replace_providers` (provider half of the atomic Save / Import / Reset), `get_setting` / `list_settings` (incl. the embedding-selection keys) / `upsert_settings` (settings half of Save / Reset), `get_resolved_str` (effective general-tab values), `list_model_capabilities` / `upsert_model_capability`, `test_provider` (per-row Test connection), `discover_models` (embedding-section model discovery), `probe_all` (auto-check on open), `probe_embedding` (Test Embedding), and `readiness_snapshot` (Health Dots); wraps `ProvidersStore`, `AppSettingsStore`, `ModelCapabilitiesStore`, `SettingsService`, `ProviderRegistry`, and `ReadinessService` (D-R-06). |
| `EventBus` | Emitting `_provider_registry_reloaded` / `_app_settings_changed`; subscribing to `_app_readiness_changed`. |
| `NotificationService` | The save / export / import / reset toasts and the blocking error notification. |
| `NativePickers` | The Export save picker (`save_file`), the Import file picker (`open_file`), the Task Editor folder picker (`open_folder`). |
| `Clipboard` | The Copy-path action (`copy_text`). |
| `FileSystemActions` | The three Open-folder buttons (`open_in_file_manager`). |

**Adapter boundary (D-R-06).** The `SettingsController` depends only on `SettingsGateway` for every persistence-store and backend domain/compute interaction (provider catalog, settings, capabilities, registry probes, readiness), never on a backend Protocol — no `ProvidersStore`, `AppSettingsStore`, `ModelCapabilitiesStore`, `SettingsService`, `ProviderRegistry`, or `ReadinessService` reaches the controller (08-A §5/§6); the adapter holds those behind the gateway. The retained direct params are the Event Bus and the OS-adapter helpers `NativePickers`, `Clipboard`, `FileSystemActions`, and `NotificationService`.

The module also calls the redaction functions of
`10_Domain_and_Data/08_REDACTION_PATTERNS.md` to redact every secret shown in the
Import preview and every probe error string; these are module-level functions,
not an injected Protocol.

## 8. Stores fanout assessment

The Settings Dialog subscribes to **one** Event Bus signal
(`_app_readiness_changed`) and reads from its single `SettingsGateway` (the
provider-catalog, settings, capability, registry-probe, and readiness surface).
This is well under the soft fan-out limit at
which a controller split is recommended; the single `SettingsController` carries
the whole dialog, and no sub-controller split is warranted.

The dialog's complexity is in its working-copy model and its sub-dialog stack,
not in subscription fan-out. That complexity is absorbed structurally by the
`providers_tab/`, `general_tab/`, and `sub_dialogs/` sub-packages of §3, each
independently testable, rather than by splitting the controller.

## 9. Test boundary

| Scope | What is tested | Where |
|---|---|---|
| Unit — controller | Working-copy dirty diff, `save_enabled` computation, Save / Import / Reset orchestration with a fake `SettingsGateway`, the auto-check request on open. | `tests/test_controller.py`, `tests/test_working_copy_dirty.py` |
| Unit — validation | Every hard error and soft warning of `description.md` §15, including the cleared-numeric-field edge input (EC-SET-3). | `tests/test_validation.py` |
| Unit — Providers tab | The `QAbstractTableModel` adapter, sort by Label / Type / Health, per-row action gating, the embedding section. | `tests/test_provider_table_model.py` |
| Unit — General tab | Each binder maps its control to exactly one `08-G` key and round-trips the value through the storage text form. | `tests/test_general_field_binders.py` |
| Unit — sub-dialogs | Provider Edit API-key env-var-name input and inline entry validation (`sub_dialogs/provider_edit.md` §5.1); Import preview grouping and redaction. | `tests/test_provider_edit.py`, `tests/test_import_preview.py` |
| Integration | The atomic Save / Import / Reset transactions against the adapter wired over real SQLite-backed `ProvidersStore` and `AppSettingsStore` instances (sharing one connection so the transaction is genuinely atomic), asserting all-or-nothing commit and the post-commit events. This integration test deliberately exercises the adapter+backend together — the gateway is NOT faked here. | top-level `tests/` integration suite |

The Settings Dialog UNIT tests fake the `SettingsGateway` (plus the Event Bus and the
OS-adapter helper fakes from each module's `testing.py`); the controller is never tested
against a raw backend store or service. The Test connection and Test Embedding probes are
driven through the fake gateway in unit tests so no unit test performs network I/O; the
real stores and registry behind the gateway appear only in the atomic-transaction
integration test above.
