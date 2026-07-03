# Readiness Probe

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-E_interfaces_contracts.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`, `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`, `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`, `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`, `08_Cross_Cutting/08-J_event_bus_catalog.md`, `08_Cross_Cutting/08-C_settings_hierarchy.md`, `10_Domain_and_Data/08_REDACTION_PATTERNS.md`

This document specifies the Readiness Probe — the algorithm by which the Readiness Service checks every enabled provider and the configured embedding model for reachability, coalesces overlapping probe requests, applies a probe timeout, and aggregates the per-provider results into a single application-readiness verdict of `READY`, `DEGRADED`, `NOT_READY`, or `CHECKING`. It implements the `ReadinessService` Protocol declared in `08_Cross_Cutting/08-E_interfaces_contracts.md` §12.

---

## Table of Contents

1. Purpose
2. Inputs
3. Outputs
4. Preconditions
5. Postconditions
6. Algorithm
   - 6.1 The readiness contract
   - 6.2 The probe of one provider
   - 6.3 The embedding-model probe
   - 6.4 `probe_all` — probing every provider concurrently
   - 6.5 Aggregation into the overall verdict
   - 6.6 Coalescing overlapping probe requests
   - 6.7 Probe frequency and triggers
7. Configuration
8. Error handling
9. Threading and concurrency
10. Examples
11. Test cases

---

## 1. Purpose

Before a user starts a benchmark run, the Readiness Probe answers a deliberately **narrow** question: is each enabled provider **reachable and responding**, and does its endpoint **advertise models**? A run whose only provider is unreachable, or a `GRADED` run whose embedding endpoint cannot be reached, will fail slowly — the probe catches that up front and keeps the answer current.

**What `READY` does and does not mean (SPEC-048).** `READY` means the application connected to the provider, the provider responded, and (where the endpoint supports discovery) it advertised one or more models. It is **not** a guarantee that any advertised model will actually *load and run*: a model can be registered at an endpoint yet fail to load (insufficient memory, a model not currently resident, a backend that lists more than it can serve). The application is also **backend-agnostic** — a provider is just a base URL and a model name, and the application does not and cannot know what software serves it (Ollama, LM Studio, llama.cpp, a proxy, or anything else; those are only examples). Whether a specific model loads and runs is confirmed at **use time**, never assumed from the listing: the pipeline's **warmup** pre-loads each model at its switch boundary (`benchmark.warmup_enabled`; a warmup timeout is treated as a provider failure — `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`), and the user can confirm a model on demand with **Provider Edit → Test inference**. An advertised-but-unloadable model therefore fails fast at run start (its first warmup/inference), not silently mid-run.

The Readiness Service maintains one `AppReadinessSnapshot` — the application's live view of whether it is ready to run. The snapshot is built by probing each enabled provider with the same lightweight reachability check the `LLMClient` exposes as `probe_health`, probing the configured embedding model, and folding every per-provider `ProviderHealth` plus the embedding result into a single `ReadinessState`. The snapshot drives the status-bar health dot, the readiness section of the Settings dialog, and — most importantly — the New Benchmark widget's gating logic, which decides whether the Start button is enabled for the chosen run mode.

The Readiness Probe does no network work of its own; it orchestrates `LLMClient.probe_health` calls obtained through the Provider Registry, and it never raises — an unreachable provider is reported as data, not as an exception.

---

## 2. Inputs

| Input | Type | Source | Notes |
|---|---|---|---|
| Enabled providers | `tuple[ProviderConfig, ...]` | Provider Registry `list_enabled()` | The probe work list. |
| Provider clients | `LLMClient` per provider | Provider Registry `get_client()` | The probe targets; a provider with no client (unresolved secret) is reported `MISSING_ENV` without a network call. |
| Embedding selection | `EmbeddingSelection \| None` | `SettingsService.resolve_embedding_selection()` | The selected `(provider, embedding model)` to probe for embedding reachability; `None` means no embedding model is selected. |
| Clock | `Clock` | composition root | `monotonic_ms()` for probe latency. |
| Probe trigger | startup, an explicit refresh, or a `_provider_registry_reloaded` event | app lifecycle, Settings dialog, Provider Registry | Causes `probe_all` to run; see §6.7. |
| Run settings | `tuple[BenchmarkRunSettingEntry, ...]` / user-saved settings | Settings Service | Source of the probe timeout (§7). |

All DTOs are defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`.

## 3. Outputs

| Output | Type | Produced by | Notes |
|---|---|---|---|
| Readiness snapshot | `AppReadinessSnapshot` | `snapshot()`, `probe_all()` | Carries the `overall` `ReadinessState`, the per-provider `ProviderHealth` tuple, and `embedding_reachable`. |
| One provider's health | `ProviderHealth` | `probe()` | Reachability, model count, latency, optional error. |
| Readiness-changed event | `AppReadinessChangedEvent` | after a `probe_all` recompute | Emitted on the `_app_readiness_changed` Event Bus signal; coalesced to at most twice per second. |

## 4. Preconditions

- The Provider Registry is constructed; `list_enabled()` and `get_client()` are callable.
- `probe(provider_id)` runs as a single blocking call on a `TaskRunner` worker thread.
  `probe_all` is **orchestrated on the dispatcher thread** (DD-38/DD-40): the dispatcher
  fans the per-provider reachability probes out to `TaskRunner` workers and is the only
  thread that blocks awaiting their `Future`s — a pool worker never submits-and-waits on
  the pool (no event loop).
- The `SettingsService` can resolve the embedding selection via `resolve_embedding_selection()`.

## 5. Postconditions

- After `probe_all` completes, the service holds a fresh `AppReadinessSnapshot` whose `overall` reflects every enabled provider's reachability and the embedding model's reachability.
- `probe_all` emits exactly one `_app_readiness_changed` event when the recomputed snapshot differs from the previous one; it emits none when the snapshot is unchanged.
- Before the first probe completes, `snapshot()` returns a snapshot whose `overall` is `CHECKING`.
- Neither `probe_all`, `probe`, nor `snapshot` ever raises; an unreachable provider, an unresolved secret, and a missing embedding model are all reported as data.
- The probe mutates no persistent state — `ProviderHealth` and `AppReadinessSnapshot` are never written to the database.

---

## 6. Algorithm

### 6.1 The readiness contract

The contract is the `ReadinessService` Protocol from `08_Cross_Cutting/08-E_interfaces_contracts.md` §12:

| Method | Kind | Purpose |
|---|---|---|
| `snapshot()` | `def` | Return the most recent `AppReadinessSnapshot`. Returns a `CHECKING` snapshot before the first probe. Never raises. |
| `probe_all()` | blocking | Probe every enabled provider and the embedding model, recompute the aggregate, emit `_app_readiness_changed`, and return the new snapshot. Never raises. |
| `probe(provider_id)` | blocking | Probe one provider and return its `ProviderHealth`. Never raises. |

`snapshot()` is a synchronous read of the cached snapshot — it never itself probes. The cached snapshot is the source of truth that the New Benchmark widget and the status-bar dot read; `probe_all` is what refreshes it.

### 6.2 The probe of one provider

Probing a single provider reuses the `LLMClient.probe_health` algorithm (`11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.8). The Readiness Service adds the registry lookup and the no-client case:

```
function probe(provider_id):
    try:
        client = provider_registry.get_client(provider_id)
    except ConfigurationError:
        # the provider is enabled but its api-key env-var name is unset/empty
        return ProviderHealth(provider_id, reachable=False, discovery_supported=False,
                              model_count=None, last_probe_ms=0,
                              last_error="missing environment variable", probed_at=clock.now_ms())
    return client.probe_health()            # never raises; under the probe timeout
```

`client.probe_health()` itself performs a reachability handshake and (when the per-provider implementation supports it) a model-discovery call under the probe timeout, turning any failure into a `ProviderHealth(reachable=False, ...)`. The Readiness Service therefore receives a `ProviderHealth` in every case.

**Readiness probes do NOT emit `_inference_progress` events.** A readiness probe is an invisible background check — neither this service nor `LLMClient.probe_health()` invokes the shared progress-emitter helper (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9), and the `InferenceContext` enum (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §4.19a) deliberately omits any `READINESS_PROBE` member to forbid such a path by construction. The user sees readiness changes through the status-bar health dot and the Settings readiness section, never through a live progress indicator.

| Provider condition | Resulting `ProviderHealth` | Maps to `ProviderTestStatus` |
|---|---|---|
| Reachable, discovery supported, lists one or more models | `reachable=True, discovery_supported=True, model_count>0` | `READY` |
| Reachable, **discovery NOT supported** (e.g. Anthropic) | `reachable=True, discovery_supported=False, model_count=None` | `READY` — the missing discovery endpoint is informational, not unhealthy. |
| Reachable, discovery supported, lists zero models | `reachable=True, discovery_supported=True, model_count=0` | `ZERO_MODELS` (informational) |
| Reachable, discovery supported, listing call failed | `reachable=True, discovery_supported=True, model_count=None`, `last_error` set | `READY` — reachability was observed; the failed listing is informational and surfaces to the Settings dialog as a soft warning. |
| Not reachable (connection refused, auth rejected, probe deadline expired) | `reachable=False, model_count=None`, `last_error` set | `UNREACHABLE` |
| Enabled but the api-key env-var **name** does not resolve (named variable unset/empty) — no client built | `reachable=False, model_count=None`, `last_error="missing environment variable"` | `MISSING_ENV` |

The `last_error` string is redacted by the client before it reaches the Readiness Service (`10_Domain_and_Data/08_REDACTION_PATTERNS.md`); the Readiness Service surfaces it verbatim.

### 6.3 The embedding-model probe

The embedding model is checked separately because the cosine evaluation phase of `GRADED` cannot run without it. The resolved embedding selection (a `(provider, model)` pair, or `None`) names the embedding provider and model.

**The automatic check is handshake-only — it never calls `embed()` (DD-48).** An `embed()`
call is model compute (an inference-class call under DD-40) and is billable on paid
providers; the cost-safety invariant — *billable calls are never run automatically* —
applies to embeddings exactly as it applies to chat. The automatic readiness check
therefore verifies only free signals:

```
function probe_embedding():                          # handshake-only — no model compute (DD-48)
    selection = settings.resolve_embedding_selection()
    if selection is None:
        return False                         # no embedding model selected
    try:
        client = provider_registry.get_client(selection.provider.provider_id)
    except ConfigurationError:
        return False                         # embedding provider not usable
    if client does not implement the embedding surface:
        return False
    if provider's reachability handshake in this batch failed:
        return False                         # provider down ⇒ embedding unreachable
    if client.supports_discovery() and selection.model not in discovered models:
        return False                         # selected model not listed
    return True
```

`embedding_reachable` therefore means: *an embedding selection exists, its provider is
reachable, the client has an embedding surface, and (where discovery is supported) the
selected model is listed.* It deliberately does **not** prove the endpoint can actually
embed — a model can be listed yet fail to embed (wrong model kind, chat-only endpoint).
That stronger verification happens on exactly two paths, both user-initiated:

1. **The embedding test** — the Settings *Test Embedding* action, also fired when the user
   changes the embedding selection (`11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md`
   §6.6a; gate activity `PROVIDER_TEST`); and
2. **The run-start fail-fast probe (DD-48)** — when the user starts or resumes a run that
   needs embeddings, the pipeline issues one `embed()` before any inference begins
   (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §4), so a broken embedding
   endpoint fails the run immediately instead of at the cosine stage.

An absent embedding selection yields `embedding_reachable = False`; this is not an error — it simply means `GRADED` is unavailable until the user configures an embedding model, exactly as `10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §5.2 states.

### 6.4 `probe_all` — probing every provider concurrently

`probe_all` probes every enabled provider and the embedding model, then aggregates:

```
function probe_all():                                     # orchestrated ON the dispatcher thread (DD-40)
    if a probe_all is already in flight:
        return coalesce_with_running_probe()              # see 6.6
    set cached snapshot.overall = CHECKING; emit if changed
    providers = provider_registry.list_enabled()
    # Reachability handshakes are NOT inferences (DD-40): they may run concurrently.
    # The dispatcher submits the leaf probes to the shared TaskRunner and is the only
    # thread that blocks on their Futures (DD-38); leaf probes never submit work themselves.
    futures        = [runner.submit(lambda p=p: probe(p.provider_id)) for p in providers]
    health_results = [f.result() for f in futures]        # legal: this loop runs on the dispatcher thread
    # The embedding probe is the batch's ONLY inference-class call: it runs once,
    # serially, after the reachability fan-out, under the READINESS_PROBE gate hold.
    embedding_ok   = runner.submit(probe_embedding).result()
    new_snapshot   = aggregate(health_results, embedding_ok)     # see 6.5
    if new_snapshot != cached snapshot:
        cached snapshot = new_snapshot
        emit "_app_readiness_changed" (coalesced, <= 2/s)
    return new_snapshot
```

The per-provider probes run concurrently — they are reachability handshakes, not inferences
(DD-40), so the serial-inference restriction does not apply to them, and probing eight
providers strictly serially would make startup readiness needlessly slower. Each individual
probe is bounded by the probe timeout, and the pool's fixed size
(`maxThreadCount = 4`, DD-40) bounds the batch: N providers complete in at most
`ceil(N / 4)` probe-timeout windows (e.g. 8 providers ≈ 2 windows ≈ 10 s worst case),
comfortably inside the 30 s `READINESS_PROBE` watchdog. The embedding probe — the only
inference-class call in the batch — runs once, serially, after the reachability fan-out.

`probe_all` never raises: every individual probe already collapses its own failures into a `ProviderHealth` or a boolean, so the join only ever yields data.

### 6.5 Aggregation into the overall verdict

The `overall` `ReadinessState` folds every per-provider `ProviderHealth` and the embedding result into one value. **A provider counts as healthy when it is reachable, regardless of whether discovery is supported and regardless of the discovered model count.** The discovery information is informational metadata that flows to the New Benchmark widget's model pickers but does not gate readiness:

```
function aggregate(health_results, embedding_ok):
    enabled_count = len(health_results)
    # A provider is healthy when it is reachable. discovery_supported=False
    # (e.g. Anthropic) is informational, not unhealthy. model_count is metadata.
    healthy_count = count of health where reachable == True
    if enabled_count == 0:
        overall = NOT_READY                # no enabled provider at all
    elif healthy_count == 0:
        overall = NOT_READY                # every enabled provider is unreachable
    elif healthy_count == enabled_count and embedding_ok:
        overall = READY                    # every provider reachable; embedding fine
    elif healthy_count == enabled_count and not embedding_ok:
        overall = DEGRADED                 # providers fine, embedding model not reachable
    else:
        overall = DEGRADED                 # at least one provider reachable, at least one not
    return AppReadinessSnapshot(overall, tuple(health_results), embedding_ok)
```

The four states mean:

| `ReadinessState` | Meaning | What the New Benchmark widget allows |
|---|---|---|
| `READY` | Every enabled provider is reachable, and the embedding model is reachable. A reachable provider is healthy regardless of whether it reports a discovered model count — a provider type that does not expose discovery (Anthropic) and one that lists zero models are both still reachable. | Every run mode may start. |
| `DEGRADED` | Some — but not all — capability is available: at least one provider works, but either another provider is down or the embedding model is unreachable. | `SYNTHETIC` and `TASKS` may start using the reachable providers. `GRADED` may start only if the embedding model is reachable; if `embedding_reachable` is `False`, `GRADED` is blocked with an explanatory message. |
| `NOT_READY` | No enabled provider is usable. | No run mode may start. |
| `CHECKING` | A probe is in flight and no result is in yet. | The Start button is held disabled until the probe resolves. |

The gating logic itself lives in the New Benchmark widget; the Readiness Service supplies the snapshot it gates on. The widget also reads the per-provider `ProviderHealth` tuple directly so it can, for example, offer only the reachable providers in the model picker even while `overall` is `DEGRADED`.

The embedding state matters only for `GRADED`: a run that does not grade (`SYNTHETIC`, `TASKS`) is unaffected by `embedding_reachable`, which is why an unreachable embedding model produces `DEGRADED` rather than `NOT_READY`.

### 6.6 Coalescing overlapping probe requests

Several triggers can ask for a probe at almost the same moment — startup runs one, the Settings dialog opens and requests one, a `_provider_registry_reloaded` event fires another. Probing the same providers three times over is wasteful and floods the readiness event.

The service coalesces overlapping requests:

- The service keeps a handle to the in-flight `probe_all` task, if any.
- A `probe_all` call made while a probe is already running does **not** start a second probe. It waits on the running probe (a shared `Future`) and returns the same resulting snapshot. Every concurrent caller therefore observes the one shared result.
- Once the running probe finishes, the next `probe_all` call starts a genuinely fresh probe.

This guarantees at most one provider-probe batch is in flight at a time. A request that arrives the instant after a probe finished still starts a new probe — coalescing collapses *concurrent* requests, it does not debounce *sequential* ones; sequential rate limiting is handled by §6.7.

The `_app_readiness_changed` event is additionally coalesced at the Event Bus layer to at most twice per second (`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.7), so even rapid back-to-back snapshot changes do not repaint the status-bar dot faster than is useful.

### 6.7 Probe frequency and triggers

The Readiness Probe is **event-driven, not polled**. There is no periodic timer continuously probing providers in the background — that would generate constant network traffic against the user's local Ollama host and any configured cloud providers for no benefit. A probe runs only when something could have changed the answer:

| Trigger | When | Coalesced |
|---|---|---|
| Application startup | Once, as part of the startup sequence, so the first window already shows a real readiness state. | n/a (first probe) |
| Provider registry reloaded | On every `_provider_registry_reloaded` event — a Settings save, import, or reset changed the provider catalog, so readiness must be re-evaluated. | yes (§6.6) |
| Explicit user refresh | The user clicks the refresh control in the Settings dialog readiness section, or in the status-bar health dot's context action. | yes |
| New Benchmark widget shown | When the user opens the New Benchmark widget, if the cached snapshot is older than the staleness window (§7), a refresh is requested so the gating decision is current. | yes |

Between triggers the cached snapshot is served as-is by `snapshot()`. A run that is already executing does not trigger readiness probes — the run uses its frozen provider snapshot and the circuit breaker handles in-run provider failure (`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`); readiness probing is a pre-run and configuration-time concern.

The Readiness Probe and the circuit breaker are deliberately distinct: the readiness probe answers "can a run start?" before a run; the circuit breaker answers "should this provider be skipped right now?" during a run. They use the same `provider_id` key and the same `probe_health`-style reachability notion, but neither calls the other.

---

## 7. Configuration

The probe reads its tuning from the Settings Service three-layer hierarchy (`08_Cross_Cutting/08-C_settings_hierarchy.md`).

| Setting key | Default | Meaning |
|---|---|---|
| `provider.probe_timeout_ms` | `5000` | Deadline for each individual provider probe and for the embedding probe. The same key the `LLMClient` uses for `probe_health` (`11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §7) — readiness and the client agree on one probe budget. |
| `readiness.snapshot_staleness_ms` | `30000` | How old the cached snapshot may be before opening the New Benchmark widget triggers a refresh. |

The probe defines no frequency setting because it is event-driven, not polled (§6.7). Outside a run these keys resolve through the user-saved and default layers; the probe is not run-scoped and reads no run snapshot.

---

## 8. Error handling

The Readiness Probe never raises. Every failure mode is collapsed into the readiness data:

| Situation | Probe behaviour |
|---|---|
| A provider's host is unreachable | `client.probe_health` returns `ProviderHealth(reachable=False, last_error=<redacted>)`; the provider counts toward `DEGRADED`/`NOT_READY`. |
| A provider's probe exceeds `provider.probe_timeout_ms` | The deadline collapses inside `probe_health` into `reachable=False`; no exception escapes. |
| A provider is enabled but its api-key env-var name is unset/empty | `get_client` raises `ConfigurationError`; `probe` catches it and returns `reachable=False` with a `MISSING_ENV`-style error; no network call is made. |
| No enabled providers exist | `aggregate` yields `overall = NOT_READY`; not an error. |
| No embedding model is configured | `probe_embedding` returns `False`; `embedding_reachable` is `False`; not an error. |
| The embedding selection's model is absent from the provider's discovered list (discovery supported) | `probe_embedding` returns `False`; not an error. A listed-but-cannot-embed endpoint is NOT detected automatically (DD-48) — it is caught by the user-initiated embedding test or the run-start fail-fast probe. |
| `resolve_embedding_selection()` raises `PersistenceError` | The probe treats the embedding result as unknown-and-unreachable (`False`) and proceeds; the provider probes are unaffected. The `PersistenceError` is logged, not raised to the caller, so a transient storage hiccup never breaks readiness. |

Every error string that reaches a snapshot has already passed through redaction at the `LLMClient` boundary. The Readiness Service adds none of its own un-redacted text.

---

## 9. Threading and concurrency

- `snapshot()` is synchronous: it returns the cached `AppReadinessSnapshot` immediately and is callable on the Qt main thread by the status-bar dot and the New Benchmark widget without blocking.
- `probe(provider_id)` is blocking and runs as a single leaf unit on a `TaskRunner` worker thread, per `08_Cross_Cutting/08-E_interfaces_contracts.md` §12. It is network-bound; running off the GUI thread keeps the UI responsive while readiness is being checked. A leaf probe never submits work to the `TaskRunner` and never blocks on a `Future`.
- `probe_all()` is **orchestrated on the dispatcher thread** (DD-38/DD-40) — the one thread sanctioned to block on unit `Future`s, and by construction idle whenever a probe batch can run (the single-inference gate guarantees no benchmark is active). The dispatcher submits the per-provider leaf probes concurrently to the shared `TaskRunner` (§6.4) and joins them; with the pool's fixed `maxThreadCount = 4`, N providers complete in at most `ceil(N / 4)` probe-timeout windows. Pool-starvation deadlock is impossible: the only blocker is the dispatcher, never a pool worker.
- The per-provider reachability handshakes are **not inferences** (DD-40), so running them concurrently does not touch the serial-inference restriction. The embedding probe is the batch's only inference-class call and runs once, serially, after the fan-out.
- Coalescing (§6.6) guarantees at most one `probe_all` batch is in flight at a time; concurrent callers all wait on the same shared `Future` and receive the same snapshot.
- `probe_all` emits `_app_readiness_changed` from the dispatcher thread; the Event Bus marshals delivery to the UI thread and coalesces it to at most twice per second.
- The probe owns no threads of its own: orchestration runs on the dispatcher thread, leaf probes on the shared `TaskRunner`.

**Single-inference gate.** Both `probe_all()` and `probe()` call `InferenceActivityStore.try_acquire(InferenceActivity.READINESS_PROBE, ctx)` before issuing any network call, and `release(lease)` in `finally` once the probe (or batch) completes (DD-50). If `try_acquire` returns `None` — for example a benchmark run holds `BENCHMARK_RUN`, or a provider test holds `PROVIDER_TEST` — the probe is **deferred, not queued**: the service records the deferred request and the readiness widget displays `Checking deferred — run in progress`; the probe is re-attempted once the gate is `IDLE` again. The coalescing rule in §6.6 still applies: overlapping deferred requests collapse into one. The watchdog auto-release timeout for `READINESS_PROBE` is 30 seconds (`08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-14). See also EC-RUN-13.

---

## 10. Examples

### 10.1 Happy path — startup readiness, everything works

The application starts with one enabled provider, `ollama_local`, and an embedding model configured on it.

1. The startup sequence calls `probe_all()`. The cached snapshot's `overall` is set to `CHECKING` and the status-bar dot shows the checking state.
2. `probe("ollama_local")` runs: `get_client` returns the client, `probe_health` lists three models in 210 ms → `ProviderHealth(reachable=True, discovery_supported=True, model_count=3, last_probe_ms=210)`.
3. `probe_embedding()` runs handshake-only (DD-48): a selection exists, the provider is reachable, the client has an embedding surface, and the selected model is listed → `embedding_reachable = True`. No `embed()` call is made.
4. `aggregate` sees `reachable_count == enabled_count == 1` and `embedding_ok == True` → `overall = READY`.
5. The snapshot changed from `CHECKING` to `READY`; `_app_readiness_changed` is emitted; the status-bar dot turns to the ready state; the New Benchmark widget allows every run mode.

### 10.2 Edge case — embedding model down, `GRADED` blocked

The same provider is reachable, but the configured embedding model is not loaded.

1. `probe_all()` probes `ollama_local` → reachable with three models.
2. `probe_embedding()` runs handshake-only (DD-48); the configured embedding model is not in the provider's discovered list → `embedding_reachable = False`. (A subtler failure — the model is *listed* but cannot embed — is not visible to the automatic check; it is caught by the user-initiated Test Embedding action or, at the latest, by the run-start fail-fast probe.)
3. `aggregate` sees `reachable_count == enabled_count` but `embedding_ok == False` → `overall = DEGRADED`.
4. `_app_readiness_changed` is emitted. The status-bar dot shows degraded.
5. The New Benchmark widget allows `SYNTHETIC` and `TASKS` — they do not need embeddings — but disables `GRADED` with a message that the embedding model is unreachable. The user loads the model, clicks refresh, a fresh `probe_all` resolves to `READY`, and `GRADED` becomes available.

### 10.3 Edge case — coalesced startup-plus-settings probe

1. At startup `probe_all()` begins; its provider-probe batch is in flight.
2. Before it finishes, the user opens the Settings dialog, which requests a readiness refresh — a second `probe_all()` call.
3. The service finds a `probe_all` already running. The second call does not start a new probe batch; it waits on the running probe's shared `Future`.
4. The running probe finishes; both the startup caller and the Settings caller receive the same `AppReadinessSnapshot`. Exactly one `_app_readiness_changed` event is emitted; the provider was probed once, not twice.

### 10.4 Edge case — an enabled cloud provider with no exported key

1. `probe_all()` runs with two enabled providers: `ollama_local` (reachable) and `openai_cloud` (`api_key_raw = "OPENAI_API_KEY"`, the bare env-var name, variable unset).
2. `probe("openai_cloud")` calls `get_client`, which raises `ConfigurationError` — the named variable did not resolve, so no client exists. `probe` catches it and returns `ProviderHealth(reachable=False, last_error="missing environment variable")` with no network call.
3. `probe("ollama_local")` returns reachable with models.
4. `aggregate` sees `reachable_count (1) < enabled_count (2)` → `overall = DEGRADED`.
5. The Settings readiness section shows `openai_cloud` as `MISSING_ENV`; the New Benchmark widget offers only `ollama_local` models as targets while readiness is `DEGRADED`.

---

## 11. Test cases

| ID | Scenario | Expected outcome |
|---|---|---|
| RP-01 | `snapshot()` before any probe has run | Returns an `AppReadinessSnapshot` whose `overall` is `CHECKING`. |
| RP-02 | `probe_all()` with one reachable provider (models > 0) and an embedding selection whose model is listed | `overall == READY`; `embedding_reachable == True`; one `_app_readiness_changed` emitted; **no `embed()` call was issued** (DD-48). |
| RP-03 | `probe_all()` with one reachable provider but the embedding selection's model not listed (or its provider down) | `overall == DEGRADED`; `embedding_reachable == False`. |
| RP-04 | `probe_all()` with two providers, one reachable and one unreachable | `overall == DEGRADED`; the per-provider `ProviderHealth` tuple reflects both. |
| RP-05 | `probe_all()` with every enabled provider unreachable | `overall == NOT_READY`. |
| RP-06 | `probe_all()` with no enabled providers | `overall == NOT_READY`; no provider probe is attempted. |
| RP-07 | `probe_all()` with no embedding selection configured | `embedding_reachable == False`; `overall` reflects the providers only; no error. |
| RP-08 | A provider whose probe exceeds `provider.probe_timeout_ms` | The provider is reported `reachable=False`; `probe_all` still completes within at most `ceil(N / 4)` probe-timeout windows (pool `maxThreadCount = 4`, DD-40); no exception. |
| RP-09 | An enabled provider whose api-key env-var name is unset/empty | `probe` returns `reachable=False` with a `MISSING_ENV`-style error and makes no network call. |
| RP-10 | Two `probe_all()` calls issued while the first batch is still in flight | Only one provider-probe batch runs; both callers receive the same snapshot; one `_app_readiness_changed` emitted. |
| RP-11 | `probe_all()` recompute yields a snapshot identical to the cached one | No `_app_readiness_changed` event is emitted. |
| RP-12 | A `_provider_registry_reloaded` event fires | A fresh `probe_all()` is triggered and the snapshot updates. |
| RP-13 | The automatic check never issues model compute (DD-48) | A spy on the `LLMClient` fake asserts zero `embed()` (and zero `chat`) calls across `probe_all`/`probe`, at startup and on registry reload. A listed-but-cannot-embed endpoint passes the automatic check and is caught by the user-initiated test (06 §6.6a tests) or the run-start fail-fast probe (04 §4). |
| RP-14 | `resolve_embedding_selection()` raises `PersistenceError` during `probe_all` | The embedding result is `False`; the provider probes still complete; no exception escapes `probe_all`. |
| RP-15 | A reachable `OPENAI_COMPATIBLE` provider whose discovery call returned zero models | Its `ProviderHealth` has `reachable=True, discovery_supported=True, model_count=0`; **it counts as healthy** for the aggregator (`overall == READY` when it is the only enabled provider and the embedding model is reachable); the zero count is informational metadata only. The New Benchmark widget's model picker shows an empty list for this provider. |
| RP-16 | A reachable Anthropic-style provider whose implementation reports `discovery_supported=False` | Its `ProviderHealth` has `reachable=True, discovery_supported=False, model_count=None`; the aggregator yields `overall = READY` (assuming embedding is reachable); the missing models-list endpoint is informational and never gates readiness. |
| RP-17 | A reachable provider whose listing call itself failed (5xx on `GET /v1/models`) | Its `ProviderHealth` has `reachable=True, discovery_supported=True, model_count=None, last_error=<redacted>`; the aggregator still counts it as healthy; the Settings dialog renders the listing error as a soft warning beside the row. |
| RP-18 | Thread-affinity of the batch (DD-38/DD-40) | `probe_all`'s orchestration (submitting leaf probes, joining their `Future`s, the embedding probe, aggregation, the event emit) runs on the dispatcher thread; no leaf probe ever submits work to the `TaskRunner` or blocks on a `Future`; the batch never deadlocks even with the pool saturated. |
| RP-19 | Serial-inference scope within a batch (DD-40) | The N reachability handshakes run concurrently while the single `embed` probe runs exactly once, serially, after the fan-out — at no instant are two inference-class calls in flight. |
