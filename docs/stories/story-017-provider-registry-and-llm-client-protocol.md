---
id: STORY-017
title: Own one LLM client per provider and route composite targets through the registry
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#9-provider-registry
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#61-the-registry-contract
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#62-building-a-client-from-a-provider-configuration
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#63-secret-resolution
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#64-composite-key-routing
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#65-enable-and-disable
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#66-rebuilding-on-configuration-change
  - 11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#9-threading-and-concurrency
modules:
  - backend/provider_registry/
acceptance_criteria:
  - STORY-017-AC-1
  - STORY-017-AC-2
  - STORY-017-AC-3
  - STORY-017-AC-4
  - STORY-017-AC-5
  - STORY-017-AC-6
  - STORY-017-AC-7
  - STORY-017-AC-8
depends_on:
  - STORY-001
  - STORY-002
  - STORY-003
  - STORY-004
  - STORY-012
  - STORY-015
owner: coder
estimate: L
---

# STORY-017 — Own one LLM client per provider and route composite targets through the registry

## Goal

Give the backend one place that turns the persisted provider catalog into live, callable LLM
clients and routes a benchmark target's `(provider_id, model_name)` identity to the client that
serves it. The registry constructs exactly one `LLMClient` per enabled, valid provider; resolves
each provider's api-key from the environment variable whose name it stores; rebuilds its client set
atomically when the catalog changes; and closes superseded clients only once the single-inference
gate is idle, so an in-flight inference never has its transport closed underneath it.

## In scope

- The **canonical `LLMClient` Protocol** definition on `backend/provider_registry/protocols.py`
  (08-E §10 — "the single `LLMClient` Protocol"), the one authoritative Python declaration that
  each provider adapter (STORY-018/019/020) re-exports and implements. This story defines the
  Protocol signatures only; it implements no concrete adapter.
- The `ProviderRegistry` Protocol (08-E §9) and its concrete implementation exposing
  `list_enabled()`, `get_client(provider_id)`, and `reload()`, plus the `make_provider_registry`
  factory on `api.py` guarded by `icontract` on programmer invariants only.
- **Client construction (§6.2)** driven by an injected per-`ProviderType` client-builder callable
  (the registry selects the builder by `provider_type`; the concrete builders are wired in
  `compose.py` from the adapter factories, so the registry itself imports no concrete adapter).
- **Secret resolution (§6.3)** — reading the environment variable whose *name* is stored in
  `api_key_raw`; an empty name is allowed for keyless local providers; a named-but-unset/empty
  variable makes that one provider unusable with `MISSING_ENV` status and no client.
- **Structural validation (§6.2 step 2)** — the `OPENAI_COMPATIBLE` `base_url`/Azure-mode rule
  (all-three-or-none of `azure_endpoint`/`azure_deployment`/`azure_api_version`; any-but-not-all is
  a structural error), and the resolved-key requirement for `ANTHROPIC`/`GEMINI`.
- **Composite-key routing (§6.4)** — routing by the `provider_id` half only; the `model_name` is
  never used to pick a client and travels in the caller's `ChatRequest`.
- **Enable/disable (§6.5)** and the three distinct `get_client` failure messages (unknown /
  disabled / unusable).
- **Atomic `reload()` (§6.6)** — build a complete new client map first, swap it in with one
  reference assignment only if every enabled provider built successfully, then emit
  `_provider_registry_reloaded`; a structural failure raises `ConfigurationError` and leaves the
  previous catalog and client map untouched with no event emitted; an unresolved-secret provider is
  omitted (not a reload failure) and the reload still succeeds and emits.
- **SPEC-045 deferred close (§6.6, §9)** — the superseded client map is closed best-effort only
  when the single-inference gate is observed `IDLE`: closed at once if the gate is already `IDLE`
  at swap time, otherwise held on a pending-close list and drained on the next
  `_inference_activity_changed → IDLE` bus event.

## Out of scope

- Every concrete `LLMClient` implementation and its exception translation, streaming, and
  `probe_health`/`test_inference` behaviour — owned by STORY-018 (`OPENAI_COMPATIBLE`), STORY-019
  (`ANTHROPIC`), and STORY-020 (`GEMINI`). This story defines the Protocol they satisfy and routes
  to them via injected builders and `testing.py` fakes.
- The circuit breaker and readiness probe — separate services the pipeline orchestrates alongside
  the registry (`08_CIRCUIT_BREAKER.md`, `09_READINESS_PROBE.md`); the registry never calls either
  (§6.7, §6.8).
- The `ProvidersStore` and `provider_id` generation — owned by STORY-012; this story consumes its
  `list_providers()` read.
- The single-inference gate store itself — owned by STORY-015; this story subscribes to its
  `_inference_activity_changed` publications for the deferred close.
- Persisting or mutating the catalog — the caller (Settings dialog) persists through
  `ProvidersStore.replace_providers()` and then calls `reload()`; the registry never writes.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#9-provider-registry` — the three
  `ProviderRegistry` method signatures, their fast-synchronous threading kind, and the
  `ConfigurationError`-only error surface.
- `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client` — the authoritative `LLMClient`
  Protocol method signatures this story defines canonically on `provider_registry/protocols.py`.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#61-the-registry-contract` — the two scopes
  (app-scoped vs run-scoped) and the "network work happens later, in the client" rule.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#62-building-a-client-from-a-provider-configuration`
  — the five build steps, the Azure-mode structural rule, and the "construction performs no network
  call" rule.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#63-secret-resolution` — the env-var-name
  resolution rule, the empty-name-allowed case, and the never-persist/never-log-unredacted rule.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#64-composite-key-routing` — routing by
  `provider_id` only and the `get_client` unknown/disabled/unusable branch order and messages.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#65-enable-and-disable` — which state
  `list_enabled()`/`get_client` exposes for enabled vs disabled providers.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#66-rebuilding-on-configuration-change` — the
  commit-or-rollback rule, the unresolved-secret-is-not-a-failure rule, the emit-once-on-success
  rule, and the SPEC-045 gate-aware deferred close.
- `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md#9-threading-and-concurrency` — the atomic
  single-reference map swap and the "close only when the gate is IDLE" safety guarantee.

## Design constraints

- `backend/provider_registry/` is Qt-free and asyncio-free; it imports only `backend/settings`,
  `backend/events`, `backend/domain`, `backend/errors`, `backend/stores/inference_activity`, and
  its own `protocols.py` (`01_MODULE_INVENTORY.md` §4.3). No PySide6, no `asyncio`.
- The registry imports **no concrete provider adapter** — provider adapters are wired in only via
  the per-`ProviderType` builder callables passed at construction from `compose.py`; the
  "Provider adapters are independent / only `compose.py` wires concretes" import-linter contracts
  must hold.
- The registry never opens a network connection: it raises only `ConfigurationError` (and passes
  through `PersistenceError` from `ProvidersStore`), never `ProviderError` or `TimeoutError`.
- `reload()` swaps in the new map with exactly one reference assignment (atomic under the GIL) so a
  reader on any thread sees the whole old map or the whole new map, never a partial one.
- The resolved api-key value lives only inside the constructed client — never persisted, never
  logged, never emitted on an event; every diagnostic string the registry logs passes through
  `redact_for_log`.
- `icontract` on the `api.py` factory guards programmer invariants only, never user input or
  provider-config content.

## Acceptance criteria

### STORY-017-AC-1

Given a catalog of three enabled, structurally valid providers whose secrets resolve, when the
registry is constructed, then `list_enabled()` returns all three in `provider_order` and
`get_client(provider_id)` returns a distinct client instance for each.

### STORY-017-AC-2

Given two enabled providers with different `provider_id` that both expose the model name `model_x`,
when `get_client` is called for each, then each returns a distinct client and the model name is
never consulted to select the client — routing is by `provider_id` alone.

### STORY-017-AC-3

Each `get_client(provider_id)` outcome is determined by the provider's catalog state per this table:

| Provider state                                   | `get_client` result                                                                                   |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `provider_id` not in the catalog                 | raises `ConfigurationError("unknown provider")`                                                       |
| in the catalog, `enabled` is `False`             | raises `ConfigurationError("provider disabled")`                                                      |
| enabled, structurally valid, secret resolved     | returns the live client                                                                               |
| enabled, valid, api-key env-var name unset/empty | raises `ConfigurationError` (provider unusable); the provider has no client and carries `MISSING_ENV` |

### STORY-017-AC-4

Each provider configuration maps to a build outcome per this table (§6.2 / §6.3):

| Provider configuration                                                                         | Build outcome                                       |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `OPENAI_COMPATIBLE` with a non-empty `base_url`, no Azure fields                               | client built (plain OpenAI-compatible mode)         |
| `OPENAI_COMPATIBLE` with all three `azure_endpoint`/`azure_deployment`/`azure_api_version` set | client built (Azure mode)                           |
| `OPENAI_COMPATIBLE` with one or two Azure fields set (any-but-not-all)                         | structural `ConfigurationError`                     |
| `OPENAI_COMPATIBLE` with empty `base_url` and no Azure fields                                  | structural `ConfigurationError`                     |
| local `OPENAI_COMPATIBLE` with empty `api_key_raw`                                             | client built (keyless local; no resolution failure) |
| `ANTHROPIC`/`GEMINI` whose api-key env-var name is set and non-empty                           | client built                                        |
| `ANTHROPIC`/`GEMINI` whose api-key env-var name is unset/empty                                 | no client; provider omitted with `MISSING_ENV`      |

### STORY-017-AC-5

Given the environment variable named by an enabled provider's `api_key_raw` is set to a non-empty
value, when the registry builds that provider's client, then the variable is read and its resolved
value is passed to the client builder, and no log record or emitted event contains the resolved
value in cleartext.

### STORY-017-AC-6

Given `ProvidersStore` returns a new catalog in which one enabled `OPENAI_COMPATIBLE` provider has
an empty `base_url` and no Azure fields, when `reload()` runs, then it raises `ConfigurationError`
naming that provider, the previous catalog and client map remain exactly as they were, and no
`_provider_registry_reloaded` event is emitted.

### STORY-017-AC-7

Given `ProvidersStore` returns a new catalog that is structurally valid but includes one enabled
cloud provider whose api-key env-var name is unset, when `reload()` runs, then it succeeds, the new
client map contains a client for every resolvable provider and omits the unresolved provider with
`MISSING_ENV`, and `_provider_registry_reloaded` is emitted exactly once.

### STORY-017-AC-8

Given a successful `reload()` that supersedes a prior client map, the superseded clients are closed
per this table (SPEC-045, §6.6):

| Single-inference gate state at swap time | Superseded-client close behaviour                                                                                                                           |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `IDLE`                                   | every superseded client is closed immediately during `reload()`                                                                                             |
| held by any activity                     | no superseded client is closed during `reload()`; the map is held pending and every client is closed on the next `_inference_activity_changed → IDLE` event |

## Test plan

- STORY-017-AC-1 — unit, colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_construction.py`,
  `test_registry_lists_enabled_and_routes_each_provider`. Covers PR-01.
- STORY-017-AC-2 — unit, same file, `test_routing_is_by_provider_id_not_model_name`. Covers PR-05.
- STORY-017-AC-3 — unit (table-driven over the `get_client` states), colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_get_client.py`,
  `test_get_client_outcome_per_provider_state`. Covers PR-02/PR-03/PR-04/PR-15.
- STORY-017-AC-4 — unit (table-driven over the build outcomes), colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_build_client.py`,
  `test_build_outcome_per_provider_configuration`. Covers PR-10/PR-11.
- STORY-017-AC-5 — unit (env patched + a spy on the log/event surfaces), colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_secret_resolution.py`,
  `test_resolved_key_is_used_but_never_logged_or_emitted`. Covers PR-09.
- STORY-017-AC-6 — unit, colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_reload_atomicity.py`,
  `test_reload_structural_failure_rolls_back_and_emits_nothing`. Covers PR-07.
- STORY-017-AC-7 — unit, same file,
  `test_reload_omits_missing_env_provider_and_still_succeeds`. Covers PR-08.
- STORY-017-AC-8 — unit (table-driven over the gate state; a fake `InferenceActivityStore` and a
  spy on the clients' `close`), colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_deferred_close.py`,
  `test_superseded_clients_close_only_when_gate_idle`. Covers PR-06 and SPEC-045.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-017.
- [ ] Table-driven tests cover every `get_client` state (AC-3), every build outcome (AC-4), and
  both gate states for deferred close (AC-8).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/provider_registry/`.
- [ ] An architecture test confirms `backend/provider_registry/` imports no Qt, no `asyncio`, and
  no concrete provider adapter.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-017.
- [ ] The module inventory is unchanged.

## Notes

- **Ambiguity #1 (canonical `LLMClient` location) — resolved here.** `08-E §10` names "the single
  `LLMClient` Protocol"; `01_MODULE_INVENTORY.md` §4.3 lists `LLMClient` Protocol as the public API
  entry point for the registry and for each adapter. Resolution: the one authoritative Python
  declaration lives on `backend/provider_registry/protocols.py` (the registry owns client
  lifecycle and already depends on the Protocol per §4.3's dependencies column), and each provider
  adapter re-exports that same symbol from its own `__init__.py` so the module inventory's
  "public API entry point" column holds for every provider package without a second definition.
  This removes any build-order cycle: adapters depend on this story only for the Protocol symbol,
  and this story routes to adapters through injected builder callables and their `testing.py`
  fakes, so the registry compiles and is fully tested without importing a concrete adapter.
- **Ambiguity #4 (secret-resolution boundary) — resolved here.** Per §6.2/§6.3 the *registry*
  resolves the api-key env-var name at client-build time and passes the already-resolved value into
  the per-`ProviderType` builder. The `make_*_client` factories therefore receive a resolved
  secret value and never touch the environment themselves; the "the api-key secret has already
  been resolved by the registry before a client is ever built" precondition in
  `02_LLM_CLIENT_PROTOCOL.md` §4 is the adapter-side contract of this decision.
- **Ambiguity #6 (SPEC-045 deferred-close mechanism) — resolved here.** The registry couples to
  `InferenceActivityStore` (STORY-015) by **subscribing to the `_inference_activity_changed` bus
  event** (not a direct callback), matching the store's method-only, event-publishing contract
  (D-R-06). On swap it checks the current gate state via the store; if not `IDLE`, it holds the old
  map on a pending-close list and drains it in the `IDLE` event handler. This keeps the registry's
  only inbound coupling to the store an event subscription, consistent with the rest of the
  backend.
- The circuit-breaker and readiness integrations (§6.7, §6.8) are consumer-side orchestration by
  the pipeline and the Readiness Service; nothing in this story calls those services, so they are
  not restated as ACs here — only the registry's enumerate-and-route surface those consumers rely
  on is proven.

## Notes (fix-it pass addendum)

- **Known limitation — keyless carve-out is not local-vs-cloud-aware.** §6.2/§6.3 scope the
  keyless-provider carve-out to a *local* `OPENAI_COMPATIBLE` provider; `ProviderConfig` has no
  field distinguishing local from cloud `OPENAI_COMPATIBLE` providers, so `client_builder.py`'s
  `resolve_secret` currently applies the carve-out to any `OPENAI_COMPATIBLE` provider with an
  empty `api_key_raw`, local or not. No acceptance criterion in this story exercises a cloud
  `OPENAI_COMPATIBLE` provider with an empty key, so this is not a proven defect, but it is a real
  gap. Fixing it requires a domain-model change (a discriminator field) and is out of scope here —
  flagged for whichever future story (likely STORY-018, the `OPENAI_COMPATIBLE` adapter) needs to
  decide whether that distinction matters.
