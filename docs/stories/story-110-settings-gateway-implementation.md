---
id: STORY-110
title: Implement the concrete Settings gateway with an atomic Save, an atomic Reset, and import/export
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#7-persistence-stores
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service
  - 08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer
  - 08_Cross_Cutting/08-J_event_bus_catalog.md#57-global-and-app-readiness
  - 11_Services_and_Algorithms/09_READINESS_PROBE.md#65-aggregation-into-the-overall-verdict
  - 11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md#66a-embedding-capability-validation-d-r-11-miss-11
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#12-anti-patterns
  - 06_Settings_Dialog/implementation_structure.md#7-dependency-protocols
  - 06_Settings_Dialog/description.md#33-per-row-actions
  - 06_Settings_Dialog/description.md#6-save-flow-atomic
  - 06_Settings_Dialog/description.md#9-reset-flow
  - 06_Settings_Dialog/sub_dialogs/provider_edit.md#82-test-inference
modules:
  - ui/settings_dialog/
  - backend/settings/
  - adapters/ui_gateways/
  - backend/persistence/providers/
  - backend/persistence/app_settings/
  - backend/readiness/
acceptance_criteria:
  - STORY-110-AC-1
  - STORY-110-AC-2
  - STORY-110-AC-3
  - STORY-110-AC-4
  - STORY-110-AC-5
  - STORY-110-AC-6
  - STORY-110-AC-7
  - STORY-110-AC-8
  - STORY-110-AC-9
  - STORY-110-AC-10
  - STORY-110-AC-11
edge_cases: []
depends_on: []
adrs:
  - ADR-0014
  - ADR-0015
  - ADR-0016
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
and the import and export actions read and write the real backup files. Testing a provider no longer
freezes the window while the provider is contacted: the click starts the call and returns, the row's
health dot shows that a test is running, and the outcome paints itself when the answer arrives.

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
- **The user-interface rework ADR-0015 requires**, and only that:
  - `ui/settings_dialog/protocols.py` — the four network-bound methods change signature
    (`test_provider` and `discover_models` return `None` and gain a keyword-only `on_complete`
    callback; `probe_all` and `probe_embedding` return `None`), and the stale `blocking` docstring
    markers on the twelve store-backed methods are corrected to `fast-synchronous` per `08-E` §7.
  - `_internal/providers_tab/controller.py::on_test_clicked` — start the test, paint the row's health
    dot `TESTING`, and apply the outcome from the callback instead of from a same-line return value.
  - `_internal/sub_dialogs/provider_edit_view.py::_on_test_reachability_clicked` and
    `::_on_run_inference_clicked` — the same two-step rework; the completion handler keeps emitting
    `_provider_inference_test_completed` itself, as `08-J` §5.6 specifies.
  - `_internal/controller.py::load` — the on-open `probe_all()` call adjusts to a `None` return; it
    already discards the value and already subscribes to `_app_readiness_changed`, so this is a type
    change only.

## Out of scope

- Wiring the gateway into `make_settings_dialog` and `build_app` — owned by STORY-077.
- The dialog's own behaviour, its working copy and dirty diff, its validation model, and the layout
  and behaviour of its four sub-dialogs — already delivered by STORY-066 … STORY-068. This story
  changes only the threading and result-delivery shape of the four network-bound gateway calls listed
  above; it changes no dialog layout, no validation rule, and no other user-interface behaviour.
- **The Provider Edit live in-flight indicator** of `sub_dialogs/provider_edit.md` §8.2 — the
  two-sub-state `_inference_progress`-driven rendering between click and outcome. STORY-066 already
  records it as unimplemented, and no story owns it. ADR-0015 makes it *possible* (the graphical
  thread is now free during the call) but does not build it. This story shows only the row-level
  `TESTING` health-dot state that `description.md` §3.3 requires.
- The import file formats, the three-severity validation model, and the replace-not-merge rule —
  already delivered by `backend/import_export/`; this gateway delegates and adds no parsing.
- Writing an export payload to disk — owned by the native pickers and file-system-actions adapters at
  the dialog level; the export methods return the payload only.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b6-settingsgateway` — the fourteen base method
  signatures, verbatim, and the statement that this gateway wraps the providers store, the
  app-settings store (including the embedding selection keys), the model-capabilities store,
  `SettingsService`, `ProviderRegistry` (test probes and model discovery), and `ReadinessService`.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7b-ui-adapter-gateways-d-r-06` — the gateway is
  method-only, carries stdlib and `msgspec` types only, no `psygnal` and no Qt symbol, and is scoped
  to the methods its controller actually calls (SPEC-074).
- `08_Cross_Cutting/08-E_interfaces_contracts.md#4-the-threading-contract` — a *blocking* method is
  invoked only on a `TaskRunner` worker thread (or the dispatcher thread), never directly on the
  graphical thread; a *fast-synchronous* method returns quickly and may be called from either.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#7-persistence-stores` — all six persistence stores
  are **fast-synchronous**: SQLite under WAL returns quickly and every write runs synchronously on the
  calling thread. This is what puts the twelve store-backed gateway methods outside ADR-0015's scope.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client` — `list_models`, `probe_health` and
  `test_inference` are *blocking* network calls invoked only on a worker thread; this is what makes
  `test_provider` and `discover_models` network-bound.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#12-readiness-service` — `snapshot` is
  fast-synchronous; `probe_all` is *blocking* and orchestrated on the dispatcher thread, and emits
  the readiness-changed signal itself.
- `08_Cross_Cutting/08-A_architecture_principles.md#6-the-adapter-layer` — the adapter holds the
  backend Protocols and decides how to satisfy each gateway method.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#4a-the-dispatcher-thread-dd-38` — the readiness
  `probe_all` batch is one of only two operations orchestrated on the dispatcher thread; a pool worker
  never submits-and-waits on the pool.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#12-anti-patterns` — a blocking call on the
  graphical thread freezes the user interface; a worker result reaches the interface as a returned
  value or a published event, marshalled by the adapter.
- `06_Settings_Dialog/implementation_structure.md#7-dependency-protocols` — the dialog's dependency
  set, read as the capabilities the adapter wires behind this gateway.
- `06_Settings_Dialog/description.md#33-per-row-actions` — the row Test-connection action shows the
  health dot as `TESTING` while in flight, then the final status.
- `06_Settings_Dialog/description.md#6-save-flow-atomic` — Save is one atomic transaction across the
  provider catalog and the settings values; a failure leaves the prior configuration wholly intact.
- `06_Settings_Dialog/description.md#9-reset-flow` — Reset wipes the configuration and re-seeds the
  bundled providers and the in-code setting defaults, as one atomic step.
- `06_Settings_Dialog/sub_dialogs/provider_edit.md#82-test-inference` — the test call is expected to
  be in flight while the dialog keeps rendering, which is why the graphical thread cannot block on it.

## Design constraints

- **Where the code lands.** The implementation lands in `adapters/ui_gateways/`. ADR-0014 is
  accepted and its inventory row now exists, so `modules:` names that path directly.
- **ADR-0015 settles the blocking-method question; do not re-derive it.** Exactly four methods change
  shape — `test_provider`, `discover_models`, `probe_all`, `probe_embedding` — because only those four
  have a collaborator the specification marks *blocking*. Every other method keeps its direct return
  value. `probe_all` is submitted to the **pipeline-dispatcher thread** (a fan-out batch that joins on
  the pool must not itself run on the pool — `04_CONCURRENCY_STANDARD.md` §4a, the same reasoning as
  `MainWindowGateway.reprobe()` in STORY-105); the three leaf calls are submitted to a `TaskRunner`
  worker. `probe_all` needs no callback: `ReadinessService` emits `_app_readiness_changed` itself
  through its own batch-then-aggregate path and the dialog already subscribes to it. `probe_embedding`
  reports its outcome through `ReadinessService` the same way — handing its billable `embed("probe")`
  outcome to `ReadinessService.record_embedding_capability_result(reachable=…)` (added to
  `backend/readiness/` by this story's first spec-conformance fix pass), which updates the held
  snapshot and emits the event itself only on a real change, keeping `ReadinessService` the sole
  emitter named by `08-J` §5.7; the gateway holds no `EventBus` of its own. **Second
  spec-conformance fix pass correction (ADR-0016):** `probe_embedding` ALSO gains its own
  keyword-only `on_complete` callback, delivered alongside (never instead of) the
  `ReadinessService` call, because a one-shot user click needs a guaranteed completion signal even
  on the common case where the check reproduces an already-known value and `ReadinessService`'s
  own emit-only-on-change rule produces no event — see AC-11 and ADR-0016 for why this corrects
  ADR-0015's original "`probe_embedding` needs no callback" claim without reopening it. `test_provider`
  and `discover_models` deliver through an `on_complete` callback invoked on the graphical thread — no
  new bus channel, because `08-J` §6 rule 2 keeps single-widget data off the bus and because
  `_provider_inference_test_completed` must keep its catalogued emitter (the controller that ran the
  test). Follow `ResultGateway.regenerate_run_analysis` (STORY-108) for the callback relay, including
  its tolerance of a callback that settles after its widget is gone.
- **The single-inference gate travels with the call.** `description.md` §13 requires both test actions
  to hold `PROVIDER_TEST` for the call's full duration and release it in `finally`, and to yield
  `InferenceTestResult(outcome=GATE_BUSY, …)` without issuing a call when the gate is held elsewhere.
  Because the call now runs on a worker, the acquire/release must run there too, so the gate reflects
  the real in-flight window. `GATE_BUSY` reaches the controller through the same `on_complete`
  callback as any other outcome — the existing "gate busy" warning path in the Providers tab keeps
  working unchanged.
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
- The gateway holds no Qt symbol on its public surface. `adapters/ui_gateways/` must not import `ui`
  (`import-linter`); the Protocol is satisfied structurally, so the four changed signatures must be
  mirrored identically in `adapters/ui_gateways/protocols.py` and `ui/settings_dialog/protocols.py`.
  Each changed docstring cites ADR-0015 so a later reader comparing against `08-E` §7b.6 finds the
  reason for the divergence.

## Acceptance criteria

### STORY-110-AC-1

Each fast-synchronous `SettingsGateway` method performs exactly the stated backend interaction
against its injected collaborators and returns that collaborator's value unchanged:

| Gateway method                                     | Backend interaction                                                |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `list_providers()`                                 | returns the providers store's full catalog                         |
| `get_provider_by_name(name)`                       | returns the providers store's row for that display name, or `None` |
| `replace_providers(configs)`                       | replaces the whole catalog through the providers store             |
| `get_setting(key)`                                 | reads `key` from the app-settings store; returns `None` when unset |
| `list_settings()`                                  | returns the app-settings store's full user-saved row set           |
| `upsert_settings(values)`                          | writes `values` atomically through the app-settings store          |
| `get_resolved_str(key)`                            | returns the settings service's resolved effective value for `key`  |
| `list_model_capabilities(provider_id, model_name)` | returns the capabilities store's cached records for that pair      |
| `upsert_model_capability(record)`                  | writes `record` through the capabilities store                     |
| `readiness_snapshot()`                             | returns the readiness service's current snapshot without probing   |

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

### STORY-110-AC-7

Each network-bound method returns `None` to its caller before its backend call has completed, and runs
that call in the stated execution context — never on the calling thread:

| Gateway method                                | Backend call submitted                                                                                                                       | Execution context it runs on |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| `test_provider(provider_id, model_name, ...)` | the provider registry's inference-test probe                                                                                                 | a `TaskRunner` worker thread |
| `discover_models(provider_id, ...)`           | the provider registry's model discovery                                                                                                      | a `TaskRunner` worker thread |
| `probe_all()`                                 | the readiness service's full probe batch                                                                                                     | the dispatcher thread        |
| `probe_embedding()`                           | the billable `embed("probe")` capability check (`06_EMBEDDING_SERVICE.md` §6.6a) — not the readiness service's own free handshake-only check | a `TaskRunner` worker thread |

### STORY-110-AC-8

Each callback-bearing method invokes its `on_complete` callback exactly once, on the calling
(graphical) thread, with the value its backend call produced:

| Gateway method    | Value passed to `on_complete`                       |
| ----------------- | --------------------------------------------------- |
| `test_provider`   | the provider registry's `InferenceTestResult`       |
| `discover_models` | the provider registry's discovered model-name tuple |

### STORY-110-AC-9

For each Settings-dialog test action, clicking it applies no outcome to the widget until the gateway's
completion callback runs:

| Click target                        | State immediately after the click returns | State after the callback delivers a result |
| ----------------------------------- | ----------------------------------------- | ------------------------------------------ |
| Providers-tab row `Test connection` | the row's health dot reads `TESTING`      | the row's health dot reads the outcome     |
| Provider Edit `Test reachability`   | the inline result strip is unchanged      | the strip reads the outcome                |
| Provider Edit `Run inference test`  | the inline result strip is unchanged      | the strip reads the outcome and the model  |

### STORY-110-AC-10

Given a collaborator call inside `test_provider`'s, `discover_models`'s, or `probe_embedding`'s worker
body raises (`ProviderRegistry.get_client` raising `ConfigurationError` for an ordinary
misconfiguration, or `LLMClient.list_models` raising a `ProviderError`-marked `AppError` when the
listing call itself fails), when the worker runs, then the failure is caught and translated into a
failure-shaped result delivered exactly once, instead of silently discarding the delivery the way an
uncaught exception on a `Future` done-callback does:

| Method            | Failure-shaped result delivered                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `test_provider`   | `on_complete` receives an `InferenceTestResult(outcome=PROVIDER_ERROR, …)`, redacted                                              |
| `discover_models` | `on_complete` receives an empty `tuple[ModelName, ...]`                                                                           |
| `probe_embedding` | `ReadinessService.record_embedding_capability_result(reachable=False)` is called once, and its own `on_complete` receives `False` |

`probe_embedding`'s single-inference gate being busy (`try_acquire` returning `None`) is a
**different** case from a genuine collaborator failure (spec-conformance fix, ADR-0016): gate
contention is not a capability fact, so on that path `ReadinessService` is never called at all — the
cached snapshot's `embedding_reachable`/`overall` fields, and therefore the app-wide `GRADED`
run-start gate that reads them (`08-J` §5.7), are left exactly as they were, mirroring
`ReadinessService._probe_all_once`'s own gate-refusal branch, which likewise returns the existing
cached snapshot rather than recording a fact it never observed. `on_complete` still receives `False`
on this path (see AC-11) so the click that triggered it gets a definite terminal repaint — a
widget-local signal that is allowed to diverge from the untouched readiness state, because the two
serve different purposes: "did this specific click resolve" versus "is the app's cached embedding
capability fact still valid". On a genuine collaborator failure (the gate was acquired but the check
itself raised), `ReadinessService.record_embedding_capability_result(reachable=…)` still updates the
held snapshot's `embedding_reachable` field and recomputes `overall` through the same aggregation fold
`probe_all` uses, then emits `_app_readiness_changed` through the same conditional-on-change path
`probe_all` uses — so a later `snapshot()`/`readiness_snapshot()` read (e.g. the New Benchmark
widget's `GRADED` gate) reflects the billable check's outcome, not just the free handshake `probe_all`
runs on its own.

### STORY-110-AC-11

Given `probe_embedding(on_complete=...)` is called (ADR-0016), when its worker settles — on a
successful check, a caught collaborator failure, or a gate-busy refusal — then `on_complete` is
invoked exactly once, on the calling (graphical) thread, with the check's definite boolean outcome,
independently of whether `ReadinessService.record_embedding_capability_result` also emits
`_app_readiness_changed` for that same call; and the embedding-section widget repaints its diagnostic
label directly from that callback's delivered value, so the label never sticks on "Testing…"
indefinitely — including the common case where the billable check reproduces an already-known
`embedding_reachable` value and `ReadinessService`'s own emit-only-on-change rule produces no event at
all.

## Test plan

- STORY-110-AC-1 — unit, table-driven (one `@pytest.mark.parametrize` row per method, total over all
  ten), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_settings_gateway.py`,
  `test_each_fast_synchronous_method_performs_its_backend_interaction`.
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
- STORY-110-AC-7 — unit, table-driven (one row per network-bound method), same file,
  `test_each_network_bound_method_returns_before_its_call_runs_off_thread`. Each fake collaborator
  records `threading.get_ident()` on entry and then blocks on an event the test releases after
  asserting the gateway method already returned, following STORY-105-AC-2's
  `test_reprobe_runs_the_probe_on_the_dispatcher_thread`.
- STORY-110-AC-8 — unit, table-driven (one row per callback-bearing method), same file,
  `test_each_callback_bearing_method_delivers_its_result_once_on_the_calling_thread`.
- STORY-110-AC-9 — widget (`pytest-qt`), table-driven, colocated
  `src/ollama_llm_bench/ui/settings_dialog/tests/test_test_actions_are_deferred.py`,
  `test_each_test_action_applies_its_outcome_only_from_the_callback`. Uses a fake gateway that
  captures the `on_complete` callback without invoking it, so the test drives completion itself.
- STORY-110-AC-10 — unit, table-driven (one row per method plus the `probe_embedding` gate-busy
  case, which now asserts `record_embedding_capability_result` is NOT called), colocated
  `src/ollama_llm_bench/adapters/ui_gateways/tests/test_settings_gateway.py`,
  `test_each_network_bound_method_translates_a_worker_failure_into_a_delivered_result`; plus two
  unit tests over `ReadinessService.record_embedding_capability_result` directly, colocated
  `src/ollama_llm_bench/backend/readiness/tests/test_record_embedding_capability_result.py`,
  `test_record_embedding_capability_result_updates_the_cached_snapshot` and
  `test_record_embedding_capability_result_emits_only_on_a_real_change`.
- STORY-110-AC-11 — unit, table-driven (one row per `probe_embedding` outcome: success,
  gate-busy), colocated `src/ollama_llm_bench/adapters/ui_gateways/tests/test_settings_gateway.py`,
  `test_probe_embedding_delivers_on_complete_exactly_once_on_the_calling_thread`; plus widget
  (`pytest-qt`), colocated `src/ollama_llm_bench/ui/settings_dialog/tests/test_embedding_section.py`,
  `test_test_embedding_click_shows_testing_state_until_callback_fires` and
  `test_test_embedding_click_repaints_even_when_the_check_reproduces_a_known_value`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-110.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules — in particular
  `mypy --strict` accepts the concrete gateway against both the `ui/settings_dialog/protocols.py` and
  the `adapters/ui_gateways/protocols.py` copies of `SettingsGateway`, which must stay identical.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The four signatures ADR-0015 changes are mirrored in both Protocol copies, and each changed
  docstring cites ADR-0015 as the reason it diverges from `08-E` §7b.6; `probe_embedding`'s
  docstring additionally cites ADR-0016 for its `on_complete` parameter.
- [ ] The module inventory lists `adapters/ui_gateways/` (ADR-0014) and this story's
  `modules:` names it.

## Notes

- `save_all`/`reset_to_defaults` need real cross-store atomicity spanning `ProvidersStore` and
  `AppSettingsStore`. Rather than spinning off a prerequisite story, this story adds one small,
  purely additive "write inside an already-open transaction" method to each store
  (`replace_providers_in_open_transaction`, `upsert_settings_in_open_transaction`,
  `replace_all_settings_in_open_transaction`) plus a new `SettingsAtomicWriter` swap point in
  `backend/settings/`. This is why `modules:` lists `backend/persistence/providers/` and
  `backend/persistence/app_settings/` in addition to the three modules the estimate implied —
  five modules at planning time (see the module-count correction note below for the sixth,
  `backend/readiness/`, added during the spec-conformance fix pass).
- `ui/settings_dialog/_internal/providers_tab/embedding_section.py` is not named in this
  story's "In scope" list, but its two call sites (`_DiscoverModelsFetcher.fetch_models` and
  `_on_test_embedding_clicked`) call `discover_models`/`probe_embedding` directly and break
  under ADR-0015's signature change; this story's implementation therefore also touches that
  file as an unavoidable, in-scope consequence of the protocol change.
- **Module count correction (spec-conformance fix, 2026-08-01).** The estimate paragraph above
  says "still five modules total" — that became six once `backend/readiness/` was added. A
  spec-conformance review of the first implementation pass found that `probe_embedding` was
  publishing `_app_readiness_changed` directly from the gateway via its own `EventBus` reference,
  rather than through `ReadinessService`, so a genuinely broken embedding endpoint the billable
  `embed("probe")` check caught never updated `ReadinessService`'s own held snapshot — a later
  `readiness_snapshot()`/`snapshot()` read (the New Benchmark widget's `GRADED`-mode gate,
  `08-J` §5.7) stayed stale, and the gateway publishing a domain event directly contradicted
  `08-J` §5.7's rule that `ReadinessService` is the sole emitter. The only correct fix was
  extending `ReadinessService` itself with `record_embedding_capability_result(reachable=…)`
  (STORY-110-AC-10) — not something foreseeable at planning time, since the original plan
  assumed `ReadinessService` had "no method for this billable check" and treated the gateway
  publishing the event as the deliberate workaround. `modules:` now names `backend/readiness/`
  as a sixth module; the `L` estimate's five-module guideline is a target, not a hard ceiling
  each story must fit after a review-driven fix, and no other module was newly touched.
- **`probe_embedding` builds its `EmbeddingService` at call time, not at composition.** Every
  other backend service this gateway wraps is constructed once in `compose.py` and injected.
  `EmbeddingService` cannot follow that pattern here: per `06_EMBEDDING_SERVICE.md` §9, one
  instance is bound to a single fixed `(provider_id, model_name)` pair for its whole lifetime,
  but the Settings dialog's embedding-model selection can change at any time the dialog is open
  (the user can switch the provider/model dropdowns and click Test Embedding again against the
  new pair). `compose.py` has no way to know that pair in advance, so
  `_SettingsGateway._run_embedding_capability_check_impl` calls
  `backend.embedding.make_embedding_service(...)` directly, once per `probe_embedding()` call,
  over whatever pair is currently persisted in `AppSettingsStore`. This is a deliberate,
  narrowly-scoped exception to the "construct once at compose time" convention, not an oversight
  — recorded here per the project owner's decision that this one item belongs in the story's
  Notes rather than a full ADR. (Whether that persisted pair is actually honored by the
  underlying `embed()` call today is a separate, unresolved question — see the "Second
  spec-conformance fix pass" bullet below, item (3).)
- **Second spec-conformance fix pass (2026-08-01).** A second independent review found three more
  defects. (1) `probe_embedding`'s gate-busy branch was incorrectly calling
  `ReadinessService.record_embedding_capability_result(reachable=False)` — gate contention is not a
  capability fact, and doing so could spuriously downgrade the app-wide `GRADED` gate over mere
  contention; fixed by leaving `ReadinessService` untouched on that path (AC-10). (2) The embedding
  diagnostic label could stick on "Testing…" forever, because
  `ReadinessService.record_embedding_capability_result` only emits `_app_readiness_changed` on a real
  change and the embedding-section widget had no other way to learn a click-triggered check settled;
  fixed by giving `probe_embedding()` a keyword-only `on_complete` callback (ADR-0016, AC-11),
  delivered alongside the unchanged `ReadinessService` state update. (3) An investigation into whether
  the billable `embed("probe")` call genuinely targets the user's selected `(provider, model)` pair
  confirmed a real, deeper, **unfixed** gap: `LLMClient.embed(text)` takes no model parameter (`08-E`
  §10, verbatim), and the only mechanism that could bind a specific embedding model to a client —
  `OpenAICompatibleClientSettings.embedding_model`/`GeminiClientSettings.embedding_model`, set once by
  a `ClientBuilder` at `ProviderRegistry` build time — has no live wiring anywhere in the codebase yet
  (`compose.py` is still an empty Phase-11 stub; no `ClientBuilder` call site sets a non-default
  `embedding_model`). This gap is identical for the real benchmark pipeline's own embedding wiring
  (`backend/benchmark_pipeline/_internal/lifecycle.py`'s `_embedding_service`) and for the readiness
  handshake (`backend/readiness/_internal/embedding_probe.py`, which never calls `embed()` at all and
  so never exercises this either) — it is not specific to this gateway, and fixing it would mean
  extending `backend/provider_registry`'s `ClientBuilder`/`ProviderRegistry` contract and
  `compose.py`'s wiring, neither of which this story's `modules:` list names; `adapters/ui_gateways/`
  is also forbidden by `import-linter` from importing a concrete provider adapter to work around it
  directly. Left unfixed and documented in
  `_SettingsGateway._run_embedding_capability_check_impl`'s docstring; a follow-up story is needed to
  give `ProviderRegistry`/`ClientBuilder` a way to target a specific embedding model per call (or per
  provider) and wire it from the live `embedding.selected_model_name` setting, consumed by both this
  gateway's probe and the pipeline's real embedding-service construction.
