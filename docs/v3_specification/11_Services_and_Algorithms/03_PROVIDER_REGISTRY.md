# Provider Registry

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-E_interfaces_contracts.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`, `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`, `11_Services_and_Algorithms/09_READINESS_PROBE.md`, `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-C_settings_hierarchy.md`, `10_Domain_and_Data/08_REDACTION_PATTERNS.md`

This document specifies the Provider Registry — the service that holds one live `LLMClient` instance per configured provider, resolves a benchmark target's composite `(provider_id, model_name)` identity to the client that serves it, and rebuilds its client set whenever the provider catalog changes. It implements the `ProviderRegistry` Protocol declared in `08_Cross_Cutting/08-E_interfaces_contracts.md` §9.

---

## Table of Contents

1. Purpose
2. Inputs
3. Outputs
4. Preconditions
5. Postconditions
6. Algorithm
   - 6.1 The registry contract
   - 6.2 Building a client from a provider configuration
   - 6.3 Secret resolution
   - 6.4 Composite-key routing
   - 6.5 Enable and disable
   - 6.6 Rebuilding on configuration change
   - 6.7 Integration with the circuit breaker
   - 6.8 Integration with the readiness probe
7. Configuration
8. Error handling
9. Threading and concurrency
10. Examples
11. Test cases

---

## 1. Purpose

A benchmark run targets one or more models, and those models may be served by different providers — `(ollama_local, qwen2.5:7b)` and `(openai_cloud, gpt-4o-mini)` are two distinct targets in the same run. The pipeline, the judge phase, the embedding phase, and the Readiness Service all need to reach the correct provider client for a given target without knowing how that client is built or which SDK it wraps. The Provider Registry is that lookup.

The registry owns the lifecycle of every `LLMClient`: it constructs each client once, from the current provider catalog, and hands out the constructed instances on request. It is the single place where a `ProviderConfig` (or its frozen run-time copy, `BenchmarkRunProviderEntry`) becomes a live, callable client. Nothing else in the backend constructs an `LLMClient`.

The registry holds two collections:

- **The provider catalog** — the ordered set of `ProviderConfig` records, enabled and disabled, as last loaded from the `ProvidersStore`.
- **The client map** — one `LLMClient` per *enabled* provider, keyed by `provider_id`.

A disabled provider has a catalog entry but no client; routing to it raises `ConfigurationError`.

### 1.1 Provider name rendering — live vs snapshot (DD-33)

The registry is the canonical source of a provider's **current** display name. UI surfaces that render a provider in a **live** context — the Settings provider table, the inference-test panel, the in-flight Progress widget — call into the registry (`get_client(provider_id).config.name`, or equivalently a `name(provider_id)` helper on the registry) and re-look up on every paint so a rename takes effect immediately. UI surfaces that render a provider in a **historical** context — the Resume widget run list, the Result widget Summary / Details / Charts / Run Analysis tabs, every export, the per-run log file — render the SNAPSHOT name from the run-data tables (`BenchmarkRun.judge_provider_name`, `BenchmarkRun.embedding_provider_name`, `BenchmarkRun.embedding_model_name`, `BenchmarkResult.provider_name`, `benchmark_run_providers.name`) and NEVER consult the registry. The pipeline observes the same rule: at run start it captures the registry's current names into the run snapshot, and thereafter it reads names from the snapshot, not from the live registry, so a rename mid-run does not interleave new and old names in the Progress widget either.

---

## 2. Inputs

| Input | Type | Source | Notes |
|---|---|---|---|
| Provider catalog | `tuple[ProviderConfig, ...]` | `ProvidersStore.list_providers()` | The persisted, ordered set of providers; rebuilt into clients on `reload`. |
| Run provider snapshot | `tuple[BenchmarkRunProviderEntry, ...]` | the active `BenchmarkRun` | The frozen provider copies a run was created with; the run-scoped registry is built from these, not from the live catalog. |
| Target identity | `ProviderId`, or a `ModelDescriptor` | the pipeline, judge phase, embedding phase | The composite key whose `provider_id` selects a client. |
| Environment | OS environment variables | the process environment | Source of secret resolution: the variable whose NAME is stored on the provider is read here. |
| Reload trigger | a settings/provider-changed signal | Settings dialog save, import, reset | Causes the registry to discard and rebuild its client map. |

All DTOs are defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

## 3. Outputs

| Output | Type | Produced by | Notes |
|---|---|---|---|
| Enabled providers | `tuple[ProviderConfig, ...]` | `list_enabled()` | The enabled subset of the catalog, in `provider_order`. |
| Live client | `LLMClient` | `get_client(provider_id)` | The constructed client for one enabled provider. |
| Registry-reloaded event | `ProviderRegistryReloadedEvent` | `reload()` | Emitted on the `_provider_registry_reloaded` Event Bus signal after a successful rebuild. |

## 4. Preconditions

- The `ProvidersStore` is constructed and its schema is at the expected version; `list_providers()` is callable.
- The composition root has built the registry once at startup; the registry is then a long-lived singleton inside the `ApplicationContext`.
- For a run-scoped registry: the `BenchmarkRun` carries a non-empty `providers` snapshot.

## 5. Postconditions

- After construction or `reload()`, the client map contains exactly one `LLMClient` per enabled provider whose configuration is structurally valid and whose secrets resolved.
- A provider whose configuration is structurally invalid, or whose api-key env-var **name** does not resolve (the named variable is unset/empty), has **no** client in the map; `reload()` raises `ConfigurationError` naming the first structurally-invalid provider, and the previous client map is left intact (a failed reload is atomic — see §6.6).
- `get_client` returns the same client instance for the same `provider_id` until the next successful `reload()`.
- `reload()` emits `_provider_registry_reloaded` exactly once on success and never on failure.
- The registry never opens a network connection itself; constructing a client does not call the provider.

---

## 6. Algorithm

### 6.1 The registry contract

The contract is the `ProviderRegistry` Protocol from `08_Cross_Cutting/08-E_interfaces_contracts.md` §9:

| Method | Kind | Purpose |
|---|---|---|
| `list_enabled()` | `def` | Return the enabled providers in display order. Never raises. |
| `get_client(provider_id)` | `def` | Return the live client for a provider. Raises `ConfigurationError` if the provider is unknown, disabled, or has an unresolved secret. |
| `reload()` | `def` | Rebuild every client from the current catalog, then emit the registry-reloaded event. Raises `ConfigurationError` on a structurally invalid configuration. |

All three methods are synchronous. `get_client` hands back a client object; the network work happens later in that client's own blocking methods, invoked on `TaskRunner` worker threads (D-R-01).

The application uses the registry in two scopes:

- **The application-scoped registry** lives in the `ApplicationContext` for the whole session. It reflects the live provider catalog and is what the Settings dialog, the model pickers, and the Readiness Service consult. It is rebuilt by `reload()` whenever the catalog changes.
- **A run-scoped registry** is built at run start from the run's frozen `BenchmarkRunProviderEntry` snapshot. The pipeline uses the run-scoped registry so a mid-run edit to the live provider catalog cannot change the providers a started run is using. The run-scoped registry has the same Protocol and the same algorithm; only its input source differs (the run snapshot rather than `list_providers()`).

### 6.2 Building a client from a provider configuration

For each provider in the input set, the registry builds a client only if the provider is **enabled**. The build steps:

1. **Resolve the secret.** Read the environment variable whose NAME is stored in `api_key_raw` from the process environment (§6.3). The three `azure_*_raw` fields are **plain literal config values** (endpoint URL, deployment name, api version) and are used as-is — they are not resolved against the environment. An api-key name that does not resolve (the named variable is unset/empty) is a hard stop for this provider.
2. **Validate structure.** Check that the provider configuration is structurally complete for its `provider_type`:
   - `OPENAI_COMPATIBLE` requires a non-empty `base_url`, unless it is in **Azure mode** — defined as **all three** of `azure_endpoint`, `azure_deployment`, `azure_api_version` present (SPEC-114) — in which case those three are required and `base_url` is derived from the endpoint. Having **some but not all three** Azure fields set is a structural validation error (not a valid configuration).
   - `ANTHROPIC` and `GEMINI` require a resolved API key.
   - A local `OPENAI_COMPATIBLE` provider (Ollama, LM Studio, llama.cpp) typically needs no API key; the registry does not require one for these. When the SDK demands a non-empty token string, the client supplies a placeholder.
   A structural gap raises `ConfigurationError`.
3. **Select the client class.** `provider_type` selects the concrete `LLMClient` implementation: one class for `OPENAI_COMPATIBLE` (which itself selects the Azure transport when the `azure_*` fields are populated — see `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.9), one for `ANTHROPIC`, one for `GEMINI`.
4. **Construct.** Build the client with the resolved configuration and the injected `Clock`. Construction is pure object assembly; it performs no network call.
5. **Insert.** Place the client in the client map under `provider_id`.

### 6.3 Secret resolution

A provider's `api_key_raw` field holds the **NAME of an environment variable** (e.g. `OPENAI_API_KEY`), or empty for a keyless local provider (D-R-18). Resolution:

- The stored value IS the variable name; there is no wrapper syntax to strip. Resolution reads the environment variable of that name directly.
- If the named variable is set and non-empty, the resolved value is its content. If the variable is unset or empty, resolution **fails** for that provider.
- An empty `api_key_raw` is allowed for keyless local providers and is not a resolution failure.
- A failed resolution makes the provider unusable: it gets no client, its `ProviderTestStatus` is `MISSING_ENV`, and `get_client` for it raises `ConfigurationError`.

The registry stores only the env-var **name** (or empty) in the catalog; the resolved value lives only inside the constructed client and is never persisted, never logged, and never emitted on an event. The `azure_endpoint`, `azure_deployment`, and `azure_api_version` config values are plain literals stored as-is (not secrets, not resolved). Any diagnostic string the registry writes to the `app.*` log passes through the `redact_for_log` structlog processor (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §7.2) as it does for every other log record on that namespace. Resolution happens once, at client build time; the registry does not re-read the environment on every call.

### 6.4 Composite-key routing

A benchmark target is the pair `(provider_id, model_name)` — the `ModelDescriptor` of `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §6.1. The registry routes by the `provider_id` half of that key only:

```
function resolve(descriptor):
    client = get_client(descriptor.provider_id)   # ConfigurationError if unknown/disabled/unresolved
    return client                                  # the model_name is passed in the ChatRequest
```

The `model_name` is not used to pick a client — it is carried inside the `ChatRequest` the caller then builds. This is the meaning of composite identity: the same `model_name` served by two different providers resolves to two different clients, because the `provider_id` differs. The registry never guesses a provider from a model name; the caller always supplies the full pair.

`get_client` itself:

```
function get_client(provider_id):
    if provider_id not in catalog:        raise ConfigurationError("unknown provider")
    if catalog[provider_id].enabled is False:  raise ConfigurationError("provider disabled")
    if provider_id not in client_map:     raise ConfigurationError("provider unusable (unresolved secret / invalid config)")
    return client_map[provider_id]
```

The three failure messages are distinct so the caller can tell an unknown provider from a disabled one from a misconfigured one.

### 6.5 Enable and disable

`ProviderConfig.enabled` controls whether a provider participates:

- An **enabled** provider has a catalog entry and, if its configuration is valid, a client. It is returned by `list_enabled()`, probed by the Readiness Service, and offered in the model pickers.
- A **disabled** provider has a catalog entry but no client. It is excluded from `list_enabled()`, never probed, and never offered as a benchmark target. `get_client` for it raises `ConfigurationError`.

Enabling or disabling a provider is a catalog edit made through the Settings dialog; it is persisted by `ProvidersStore.replace_providers()` and takes effect when the registry is reloaded (§6.6). The registry does not toggle `enabled` itself.

A run that was started with a now-disabled provider in its snapshot is unaffected: the run-scoped registry was built from the frozen `BenchmarkRunProviderEntry` set and keeps its clients regardless of later catalog edits.

### 6.6 Rebuilding on configuration change

The provider catalog changes when the user saves the Settings dialog, imports a provider configuration, or resets to defaults. Each of these persists the new catalog through `ProvidersStore.replace_providers()` and then calls `registry.reload()`.

`reload()` is **atomic** — it never leaves the registry in a half-rebuilt state:

```
function reload():
    new_catalog = providers_store.list_providers()
    new_client_map = {}
    for provider in new_catalog where provider.enabled:
        try:
            new_client_map[provider.provider_id] = build_client(provider)   # 6.2
        except ConfigurationError as e:
            # remember the first failure but keep going so the report is complete
            record_failure(provider.provider_id, e)
    if any structural failure was recorded:
        raise ConfigurationError(first recorded failure)   # the OLD catalog and OLD client map stay in place
    old_client_map  = self.client_map
    self.catalog    = new_catalog
    self.client_map = new_client_map
    schedule_close_when_idle(old_client_map)               # SPEC-045: defer close until the single-inference gate is IDLE
    event_bus.emit("_provider_registry_reloaded", ProviderRegistryReloadedEvent(...))
```

Properties of the rebuild:

- **Commit-or-rollback.** The new catalog and client map are swapped in only after every enabled provider built successfully. If any enabled provider is structurally invalid, `reload()` raises `ConfigurationError` and the previous, working registry is untouched — the Settings dialog then shows the error and the user fixes the configuration before retrying.
- **An unresolved-secret provider is not a reload failure by itself.** A provider whose api-key env-var name is unset/empty is *expected* to be unusable until the user sets the variable; the registry records it with `MISSING_ENV` status and simply omits it from the new client map. `reload()` still succeeds. Only a *structural* problem (a missing `base_url`, contradictory Azure fields) aborts the reload. This distinction lets a user save a valid catalog that includes a cloud provider whose key they have not yet exported.
- **Old clients are released safely (SPEC-045).** After the swap, the superseded client map is **not** closed immediately. The registry closes it best-effort **only when the single-inference gate is observed `IDLE`** (`InferenceActivityStore`, `08_Cross_Cutting/08-E_interfaces_contracts.md` §13): if the gate is already `IDLE` at swap time, the old clients are closed at once; otherwise the old map is held on a small **pending-close list** and drained on the next `_inference_activity_changed → IDLE` event. This guarantees no `httpx` transport is closed while a worker thread is mid-read on it, while still preventing connection leaks. Because inference activities are serial and short (one at a time, gated), the deferred close happens almost immediately in practice.
- **The event fires once, after success.** `_provider_registry_reloaded` is emitted only after the swap; every widget that lists providers or models refreshes from it. A failed reload emits nothing.

The registry does not itself watch the `ProvidersStore`; the caller that persisted the change calls `reload()`. This keeps the trigger explicit and testable.

### 6.7 Integration with the circuit breaker

The Provider Circuit Breaker (`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`) tracks per-provider failures and trips a failing provider out of a run for a cooldown window. The registry and the breaker are deliberately separate concerns:

- **The registry decides whether a provider is *configured* and *usable*.** A provider with an invalid configuration or unresolved secret has no client at all.
- **The breaker decides whether a usable provider should be *skipped right now*.** A provider that is correctly configured but currently failing is `TRIPPED`.

The pipeline consults both, in order: before routing a target it asks the breaker `should_skip(provider_id)`; only if the breaker says no does it call `registry.get_client(provider_id)`. The registry never calls the breaker and the breaker never calls the registry — the pipeline orchestrates the two. The breaker keys its state by `provider_id`, the same key the registry routes on, so the two views of a provider always line up.

When `reload()` rebuilds the registry, the circuit-breaker state is **not** reset by the registry; breaker state is run-scoped and is owned by the pipeline. A catalog edit mid-run is in any case invisible to the run-scoped registry (§6.5), so the question does not arise during a run.

### 6.8 Integration with the readiness probe

The Readiness Service (`11_Services_and_Algorithms/09_READINESS_PROBE.md`) calls `list_enabled()` to learn which providers to probe and `get_client(provider_id)` to obtain each client, then calls `probe_health()` on the client. The registry's role is purely to enumerate and to route:

- `list_enabled()` gives the readiness probe its work list.
- `get_client()` gives it the client to probe; a provider with no client (unresolved secret) is reported by the readiness probe as `MISSING_ENV` without a network call, because `get_client` raised `ConfigurationError` for it.
- After a `reload()`, the readiness probe re-runs because `_provider_registry_reloaded` is one of the signals that triggers a fresh `probe_all()`.

The registry holds no health state; `ProviderHealth` is owned by the Readiness Service. The registry's only health-adjacent output is the implicit one: a provider it could not build a client for is, by definition, not ready.

---

## 7. Configuration

The registry reads no tunable settings of its own. It consumes:

- The provider catalog, from `ProvidersStore.list_providers()`.
- The process environment, for secret resolution by env-var name (§6.3).

The client-side timeout budgets (`provider.probe_timeout_ms`, `provider.connect_timeout_ms`, `provider.embedding_timeout_ms`) are read by the `LLMClient`, not by the registry; see `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §7. Those keys are resolved through the Settings Service hierarchy (`08_Cross_Cutting/08-C_settings_hierarchy.md`).

---

## 8. Error handling

| Situation | Registry behaviour |
|---|---|
| `get_client` for an unknown `provider_id` | Raise `ConfigurationError("unknown provider")`. |
| `get_client` for a disabled provider | Raise `ConfigurationError("provider disabled")`. |
| `get_client` for an enabled provider whose secret did not resolve | Raise `ConfigurationError("provider unusable")`; the provider has no client. |
| `reload()` finds an enabled provider with a structurally invalid configuration | Raise `ConfigurationError` naming the first such provider; the previous registry stays in place; no event is emitted. |
| `reload()` finds an enabled provider whose api-key env-var name is unset/empty | Not a reload failure; the provider is omitted from the client map with `MISSING_ENV` status; `reload()` still succeeds. |
| `ProvidersStore.list_providers()` raises `PersistenceError` during `reload()` | The `PersistenceError` propagates to the caller; the registry is unchanged. |
| Building one client raises an unexpected exception | Treated as a structural failure for that provider; the same commit-or-rollback rule applies. |

The registry never opens a network connection, so it never raises `ProviderError` or `TimeoutError` — those belong to the `LLMClient`. The registry's only error category is `ConfigurationError` (and the `PersistenceError` it passes through from the `ProvidersStore`). Every diagnostic string the registry produces is redacted before it is logged or surfaced.

---

## 9. Threading and concurrency

- `list_enabled`, `get_client`, and `reload` are synchronous and are called on the Qt main thread, per `08_Cross_Cutting/08-E_interfaces_contracts.md` §9. They touch only in-memory maps and (for `reload`) a fast `ProvidersStore` read; none blocks the event loop perceptibly.
- The registry's client map is read from the dispatcher thread and from `TaskRunner` worker threads (the pipeline's units, the readiness probes). Because `reload()` rebuilds a complete new map first and then swaps it in with **one atomic reference assignment** (atomic under CPython's GIL), a reader on any thread either sees the entire old map or the entire new map — never a partial one. A reader that captured a client reference before a `reload()` keeps using that (now superseded) client until its current call ends. The superseded clients are **not** closed at swap time; they are closed only once the single-inference gate is observed `IDLE` (SPEC-045, §6.6), so an in-flight inference always finishes on its captured client before that client's transport is closed — `close_quietly` never runs against a transport a worker is mid-read on.
- `reload()` is expected to be called only between runs (the Settings action is disabled while a `BENCHMARK_RUN` is active). A reload that nonetheless overlaps a shorter inference activity — a `READINESS_PROBE` or `PROVIDER_TEST` on a worker — is made safe by **both** the atomic map swap (readers see a whole map) **and** the gate-aware deferred close (the worker's captured client is closed only after the gate returns to `IDLE`, SPEC-045).
- The registry constructs no threads and owns no executor.

**Provider Test Connection and the single-inference gate.** The Provider Edit Test Connection probe (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8) is run by a ProviderTester runner that calls `InferenceActivityStore.try_acquire(InferenceActivity.PROVIDER_TEST, ctx)` for the duration of the test and `release(PROVIDER_TEST)` in `finally`. A failed acquire returns a UI-visible `Test in flight elsewhere - please wait` callout instead of issuing the call; the Test button in the dialog is bound to the gate's state and is disabled with a tooltip whenever the gate is held by an activity other than `PROVIDER_TEST`. The watchdog auto-release timeout for `PROVIDER_TEST` is 60 seconds (`08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-14).

---

## 10. Examples

### 10.1 Happy path — routing a multi-provider run

A `TASKS` run has `test_models = ((ollama_local, qwen2.5:7b), (openai_cloud, gpt-4o-mini))`.

1. At run start the run-creation use case freezes the two providers into the run's `BenchmarkRunProviderEntry` snapshot and a run-scoped registry is built from that snapshot — two clients, `ollama_local` and `openai_cloud`.
2. The pipeline runs a task against `(ollama_local, qwen2.5:7b)`: it checks the circuit breaker (`CLOSED`), calls `registry.get_client("ollama_local")`, gets the `OPENAI_COMPATIBLE` client, builds a `ChatRequest` with `model="qwen2.5:7b"`, and calls `chat`.
3. The pipeline runs the next task against `(openai_cloud, gpt-4o-mini)`: `get_client("openai_cloud")` returns a different `OPENAI_COMPATIBLE` client (different `base_url`, different key), `ChatRequest` carries `model="gpt-4o-mini"`.
4. The same `model_name` would route to whichever provider's `provider_id` was given; identity is the pair, never the model alone.

### 10.2 Edge case — a reload that includes a cloud provider with no exported key

1. The user opens Settings, adds an `ANTHROPIC` provider with `api_key_raw = "ANTHROPIC_API_KEY"` (the bare env-var name), leaves it enabled, and saves. `ANTHROPIC_API_KEY` is not set in the environment.
2. `ProvidersStore.replace_providers()` persists the new catalog; the caller calls `registry.reload()`.
3. `reload()` builds clients for every enabled provider. The Anthropic provider's secret does not resolve — this is *not* a structural failure, so the reload is not aborted. The Anthropic provider is omitted from the client map and recorded with `ProviderTestStatus.MISSING_ENV`.
4. `reload()` succeeds, swaps in the new catalog and client map, and emits `_provider_registry_reloaded`.
5. The Settings dialog readiness section shows the Anthropic provider as `MISSING_ENV`. A later `get_client("anthropic_cloud")` raises `ConfigurationError`. Once the user exports the variable and reloads, the client is built.

### 10.3 Edge case — a reload aborted by a structural error

1. The user edits an `OPENAI_COMPATIBLE` provider, clears its `base_url`, and saves.
2. The caller calls `registry.reload()`. Building that provider's client fails structurally — an OpenAI-compatible provider with no `base_url` and no Azure fields is invalid.
3. `reload()` raises `ConfigurationError` naming the provider; the previous, working catalog and client map are left exactly as they were; no `_provider_registry_reloaded` event is emitted.
4. The Settings dialog surfaces the error; the application keeps running on the prior, valid registry until the user supplies a `base_url` and saves again.

---

## 11. Test cases

| ID | Scenario | Expected outcome |
|---|---|---|
| PR-01 | Construct the registry from a catalog of three enabled, valid providers | `list_enabled()` returns all three in `provider_order`; `get_client` returns a client for each. |
| PR-02 | `get_client` for a `provider_id` not in the catalog | Raises `ConfigurationError("unknown provider")`. |
| PR-03 | `get_client` for a provider whose `enabled` is `False` | Raises `ConfigurationError("provider disabled")`; the provider is also absent from `list_enabled()`. |
| PR-04 | `get_client` for an enabled provider whose api-key env-var name is unset/empty | Raises `ConfigurationError`; the provider has no client and carries `MISSING_ENV`. |
| PR-05 | Two providers with different `provider_id` both exposing `model_x` | `get_client` on each returns a distinct client; routing is by `provider_id`, not by model name. |
| PR-06 | `reload()` after `replace_providers()` persisted a valid new catalog | The client map is rebuilt; `_provider_registry_reloaded` is emitted exactly once; superseded clients are closed. |
| PR-07 | `reload()` where one enabled provider has a cleared `base_url` | Raises `ConfigurationError`; the previous registry is unchanged; no event emitted. |
| PR-08 | `reload()` where one enabled cloud provider's api-key env-var name is unset/empty but every structure is valid | Succeeds; the cloud provider is omitted with `MISSING_ENV`; the event is emitted. |
| PR-09 | A valid env-var name in `api_key_raw` naming a set variable | The named variable is read and the client is built; the resolved value is never logged unredacted. |
| PR-10 | An `OPENAI_COMPATIBLE` provider with the `azure_*` fields populated | The built client selects the Azure transport. |
| PR-11 | A local `OPENAI_COMPATIBLE` provider (Ollama) with no API key | The client is built without error; a placeholder token is supplied to the SDK if required. |
| PR-12 | A run-scoped registry built from a `BenchmarkRun` snapshot, then the live catalog is edited and the app registry reloaded | The run-scoped registry's clients are unchanged; the running run still uses its frozen providers. |
| PR-13 | The Readiness Service calls `list_enabled()` then `get_client()` per provider | It receives the enabled set and a client for each usable provider; a `MISSING_ENV` provider raises `ConfigurationError` and is reported without a network call. |
| PR-14 | `ProvidersStore.list_providers()` raises `PersistenceError` during `reload()` | The `PersistenceError` propagates; the registry's catalog and client map are unchanged. |
| PR-15 | `get_client` called twice for the same provider with no reload between | Returns the identical client instance both times. |
