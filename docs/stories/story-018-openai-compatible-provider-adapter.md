---
id: STORY-018
title: Implement the OpenAI-compatible LLM client adapter with exception translation
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#62-transport-streaming-and-time-to-first-token
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#64-the-chat_stream-surface
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65-token-usage-capture
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#67-the-embedding-surface
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#681-probe_health--reachability--conditional-discovery
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#682-test_inferencemodel_name--manual-end-to-end-check
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#691-per-provider-type-discovery-support-matrix
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#610-exception-translation
modules:
  - backend/provider_openai_compatible/
acceptance_criteria:
  - STORY-018-AC-1
  - STORY-018-AC-2
  - STORY-018-AC-3
  - STORY-018-AC-4
  - STORY-018-AC-5
  - STORY-018-AC-6
  - STORY-018-AC-7
  - STORY-018-AC-8
  - STORY-018-AC-9
  - STORY-018-AC-10
depends_on:
  - STORY-001
  - STORY-002
  - STORY-003
  - STORY-004
  - STORY-006
  - STORY-015
  - STORY-017
owner: coder
estimate: L
---

# STORY-018 — Implement the OpenAI-compatible LLM client adapter with exception translation

## Goal

Provide the one concrete `LLMClient` that speaks the OpenAI-compatible dialect for Ollama, LM
Studio, llama.cpp, OpenAI, and Azure. It opens every chat call in streaming mode to measure
time-to-first-token, captures the provider's own token usage, honours two-level cancellation,
probes reachability with `GET /v1/models` discovery, runs the user-initiated inference test behind
the single-inference gate, embeds text through `/v1/embeddings`, and — above all — translates every
provider SDK exception into the application error taxonomy so no raw SDK exception ever escapes and
every re-raised message is redacted at the boundary.

## In scope

- The concrete `OPENAI_COMPATIBLE` `LLMClient` and the `make_openai_client` factory on `api.py`,
  re-exporting the canonical `LLMClient` Protocol from `backend/provider_registry` (STORY-017) and
  guarded by `icontract` on programmer invariants only.
- **`chat_stream` / `chat` (§6.2–§6.4)** — streaming transport, TTFT from the first non-empty
  `delta.content` chunk, the internal-consume `chat` sugar over `chat_stream`, the finite-deadline
  wrap on the stream (SPEC-015), and the DD-51 non-streaming fallback behind the same iterator
  contract.
- **Token-usage capture (§6.5)** — sending `stream_options={"include_usage": true}` on every
  streaming request and reading `prompt_tokens`/`completion_tokens` from the final chunk or the
  post-stream response object; leaving both `None` when the provider reports no usage.
- **Mid-stream cancellation (§6.6, DD-39)** — the chunk-boundary hard-cancel poll plus the
  registered idempotent abort hook that closes the in-flight stream, raising `TaskCancelledError`
  within `provider.hard_cancel_max_ms`; the soft flag is never polled mid-call.
- **`embed(text)` (§6.7)** — one `/v1/embeddings` call returning a `tuple[float, ...]`, wrapped in
  the embedding timeout.
- **`probe_health()` (§6.8.1, §6.9.1)** — reachability handshake then `GET /v1/models` discovery
  with `discovery_supported=True`; never raises; zero models is healthy; a failed listing call
  returns `reachable=True, model_count=None, last_error=<redacted>`.
- **`list_models()`** — returns the advertised catalog and, distinct from `probe_health`, raises
  `ProviderError` when the listing call itself fails.
- **`test_inference(model_name)` (§6.8.2)** — acquire `PROVIDER_TEST` on the single-inference gate
  (returning `GATE_BUSY` without a call when the gate is held), issue the canned-prompt chat, and
  classify the outcome into the `InferenceTestResult` outcome enum; never raises; release the gate
  in `finally`.
- **Azure mode selection (SPEC-114)** — selecting the Azure transport when all three `azure_*`
  fields are populated, using the same call shape as plain OpenAI-compatible mode.
- **Exception translation and redaction (§6.10)** — the single boundary block catching
  `openai.APITimeoutError`/`APIConnectionError` → `TimeoutError`, `openai.AuthenticationError` and
  every other `openai.APIError` subclass and untyped `httpx` transport failure → `ProviderError`,
  with the attached message passed through `redact(text)` and an SDK type the client did not
  enumerate still caught by the catch-all.
- The `testing.py` fake implementing the `LLMClient` Protocol with no network or SDK.

## Out of scope

- The canonical `LLMClient` Protocol declaration and provider-registry routing — owned by
  STORY-017; this story re-exports and implements that Protocol.
- The `ANTHROPIC` and `GEMINI` adapters — owned by STORY-019 and STORY-020; provider adapters never
  import one another.
- The provider wire stub itself (`tests/integration/provider_stub/`, §7a) — a shared test fixture,
  authored by the tester alongside this story's integration tests, not a shipped module.
- `tokens_per_second` estimation, the `char/4` heuristic, and reasoning-block stripping for
  `sanitized_response` — inference-phase concerns in `backend/benchmark_pipeline`, not the client;
  the client returns `text` verbatim and leaves `completion_tokens` untouched.
- The adaptive-timeout budget and retry — the client receives a fully-formed `ChatRequest` with the
  deadline already set and performs exactly one call.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client` — the Protocol surface this adapter
  implements: return shapes, the never-raises rules for `probe_health`/`test_inference`, and the
  soft-failure-in-`ChatResponse.error` contract.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#62-transport-streaming-and-time-to-first-token`
  — the six-step TTFT measurement and the DD-51 non-streaming fallback behind the iterator.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm` — the one-call rule,
  the given-not-computed deadline, the finite-deadline invariant (SPEC-015), and the hard-vs-soft
  failure split.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#64-the-chat_stream-surface` — yielding each
  content chunk then the identical trailing `ChatResponse`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65-token-usage-capture` — the
  `stream_options.include_usage` requirement and leaving counts `None` when usage is absent.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation` — the two
  hard-cancel mechanisms, the idempotent abort hook, and the `hard_cancel_max_ms` bound.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#67-the-embedding-surface` — the
  `/v1/embeddings`-only dialect and the timeout budget.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#681-probe_health--reachability--conditional-discovery`
  — the reachability-then-discovery algorithm and the never-raise, zero-models-is-healthy rules.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#682-test_inferencemodel_name--manual-end-to-end-check`
  — the gate acquire/release, the canned prompt, the outcome-classification table, and never-raise.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#691-per-provider-type-discovery-support-matrix`
  — `OPENAI_COMPATIBLE` discovery via `GET /v1/models` with `discovery_supported=True`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#610-exception-translation` — the SDK-type →
  taxonomy mapping and the mandatory boundary redaction of the attached message.

## Design constraints

- `backend/provider_openai_compatible/` is Qt-free and asyncio-free; it imports only the `openai`
  SDK, `backend/domain`, `backend/errors`, `backend/infra`, `backend/events`, and the canonical
  `LLMClient` Protocol re-exported from `backend/provider_registry` (`01_MODULE_INVENTORY.md`
  §4.3). No PySide6.
- Provider adapters never import one another (`import-linter` "Provider adapters are independent").
- `chat`, `chat_stream`, `embed`, `list_models`, `probe_health`, and `test_inference` are blocking
  synchronous methods invoked only on `TaskRunner` worker threads (D-R-01); the client holds no
  per-call mutable state — every call carries its own accumulator, timing, and deadline.
- Every call path passes a **finite** deadline to the transport (SPEC-015); no infinite or absent
  transport timeout exists anywhere in the client.
- No provider SDK exception type ever escapes any method; every re-raised message is passed through
  `redact(text)` at the boundary; user-machine model responses (`ChatResponse.text`,
  `InferenceTestResult.response_excerpt`) are stored verbatim, never redacted.
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-018-AC-1

Given a fake OpenAI-compatible endpoint that streams three content chunks then a usage chunk, when
`chat` is called, then it returns one `ChatResponse` whose `text` is the concatenation of the three
chunks, whose `ttft_ms` equals the interval to the first content chunk, and whose `prompt_tokens`
and `completion_tokens` come from the usage chunk.

### STORY-018-AC-2

Given the endpoint emits a role-only leading chunk before the first content chunk, when `chat`
streams the response, then `ttft_ms` is measured from the first content-bearing chunk, not the
role-only chunk.

### STORY-018-AC-3

Given the endpoint completes the stream with no content chunk, when `chat` is called, then
`ChatResponse.text` is empty, `ttft_ms` is `None`, `ChatResponse.error` carries the empty-response
classification, and no exception is raised.

### STORY-018-AC-4

Given the endpoint stalls past `ChatRequest.timeout_ms`, when `chat` is called, then it raises
`TimeoutError`, closes the streaming connection, and returns no `ChatResponse`.

### STORY-018-AC-5

Each provider-side failure translates to a taxonomy exception per this table, and in every case no
`openai`/`httpx` exception type escapes and the message attached to the raised error has been passed
through `redact(text)`:

| Observed SDK/transport condition                              | Re-raised as                        |
| ------------------------------------------------------------- | ----------------------------------- |
| `openai.APITimeoutError` / provider connection-timeout        | `TimeoutError`                      |
| `openai.AuthenticationError`                                  | `ProviderError`                     |
| `openai.APIError` subclass (bad model, rate limit, 5xx)       | `ProviderError`                     |
| untyped `httpx` transport failure                             | `ProviderError`                     |
| an SDK exception type the client did not explicitly enumerate | `ProviderError` (via the catch-all) |

### STORY-018-AC-6

Given a `chat` call in flight and the run's `CancellationToken` is hard-cancelled after the second
chunk, when the cancellation fires, then the client stops consuming at the next chunk boundary or
via the abort hook, closes the stream, and raises `TaskCancelledError` within
`provider.hard_cancel_max_ms`, leaving no orphaned streaming connection.

### STORY-018-AC-7

Each `probe_health` / `list_models` scenario produces the result per this table (never raising for
`probe_health`):

| Scenario                                      | Result                                                                                                                        |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| unreachable host                              | `ProviderHealth(reachable=False, discovery_supported=True, model_count=None, last_error=<redacted>)`; discovery not attempted |
| reachable, `GET /v1/models` lists zero models | `ProviderHealth(reachable=True, discovery_supported=True, model_count=0, last_error=None)`                                    |
| reachable, listing call returns 5xx           | `ProviderHealth(reachable=True, discovery_supported=True, model_count=None, last_error=<redacted>)`                           |
| `list_models()` and the listing call fails    | raises `ProviderError` (distinct from the zero-models case)                                                                   |

### STORY-018-AC-8

Given an `OPENAI_COMPATIBLE` client embeds a text against a fake `/v1/embeddings` endpoint, when
`embed(text)` is called, then it returns a `tuple[float, ...]` of the endpoint's dimensionality; and
given the embeddings call raises the SDK's error, `embed` raises `ProviderError` with a redacted
message.

### STORY-018-AC-9

Each `test_inference(model_name)` scenario produces the `InferenceTestResult.outcome` per this
table, the method never raises, and on any non-`GATE_BUSY` path the `PROVIDER_TEST` gate is acquired
before the call and released in `finally`:

| Scenario                                                  | `outcome`                                                  |
| --------------------------------------------------------- | ---------------------------------------------------------- |
| gate already held by another activity                     | `GATE_BUSY` (no call issued, `latency_ms=None`)            |
| canned-prompt call returns non-empty text                 | `SUCCESS` (`response_excerpt` verbatim, `last_error=None`) |
| call exceeds the inference-test deadline                  | `TIMEOUT`                                                  |
| provider rejects with a model-not-found error             | `MODEL_NOT_FOUND`                                          |
| provider rejects with an auth error                       | `AUTH_FAILED`                                              |
| any other provider rejection or unexpected internal error | `PROVIDER_ERROR` (redacted `last_error`)                   |

### STORY-018-AC-10

Given an `OPENAI_COMPATIBLE` provider whose `azure_endpoint`, `azure_deployment`, and
`azure_api_version` are all populated, when a chat call is issued, then the client selects the Azure
transport and the call succeeds against the Azure-shaped endpoint using the same call shape as
plain OpenAI-compatible mode.

## Test plan

- STORY-018-AC-1 — integration (real adapter + real `openai` SDK against the wire stub), colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_chat_stream.py`,
  `test_chat_streams_content_and_captures_ttft_and_usage`. Covers LC-01.
- STORY-018-AC-2 — integration, same file, `test_ttft_measured_from_first_content_chunk`.
  Covers LC-02.
- STORY-018-AC-3 — integration, same file, `test_empty_stream_reports_soft_error_without_raising`.
  Covers LC-03.
- STORY-018-AC-4 — integration, colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_deadline.py`,
  `test_stall_past_deadline_raises_timeout_and_closes_stream`. Covers LC-04.
- STORY-018-AC-5 — integration (table-driven over the wire-stub error matrix), colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_exception_translation.py`,
  `test_sdk_failure_translates_to_taxonomy_and_redacts`. Covers LC-05/LC-06.
- STORY-018-AC-6 — unit (cancellation token set + a fake stream), colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_cancellation.py`,
  `test_hard_cancel_aborts_stream_within_bound`. Covers LC-07.
- STORY-018-AC-7 — integration (table-driven over the probe scenarios), colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_probe_health.py`,
  `test_probe_health_and_list_models_per_scenario`. Covers LC-09/LC-10/LC-10b/LC-11.
- STORY-018-AC-8 — integration, colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_embed.py`,
  `test_embed_returns_vector_and_translates_errors`. Covers LC-13.
- STORY-018-AC-9 — unit (table-driven over the outcome map; a fake `InferenceActivityStore` and a
  wire-stub-backed call), colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_inference_test.py`,
  `test_test_inference_classifies_outcome_and_manages_gate`. Covers LC-18/LC-19/LC-20/LC-21/LC-23.
- STORY-018-AC-10 — integration, colocated
  `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_azure_mode.py`,
  `test_azure_fields_select_azure_transport`. Covers LC-15.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-018.
- [ ] The `LLMClient` shared contract-test suite (§6a) runs against both the real adapter (wire
  stub, §7a) and `provider_openai_compatible/testing.py`, and both legs pass.
- [ ] Table-driven tests cover the exception-translation matrix (AC-5), the probe/list scenarios
  (AC-7), and the `test_inference` outcome map (AC-9).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/provider_openai_compatible/`.
- [ ] An architecture test confirms `backend/provider_openai_compatible/` imports no Qt, no
  `asyncio`, and no sibling provider adapter, and that no provider SDK exception type escapes any
  public method (the finite-deadline / no-raw-SDK invariants).
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-018.
- [ ] The module inventory is unchanged.

## Notes

- **Ambiguity #3 (discovery matrix) — applied here.** `OPENAI_COMPATIBLE` supports discovery via
  `GET /v1/models`; `probe_health` therefore always reports `discovery_supported=True` and runs the
  listing step after a successful reachability handshake (AC-7). This differs from STORY-019
  (Anthropic: `discovery_supported=False`, no listing) and STORY-020 (Gemini: SDK `models.list()`).
- **Ambiguity #5 (translation/redaction placement) — resolved consistently across STORY-018/019/020.**
  Each adapter owns its own `_translate_exception` boundary helper in `_internal/` — there is no
  shared cross-adapter translation utility, because the "Provider adapters are independent"
  import-linter contract forbids one adapter importing another and the three SDK exception
  hierarchies are disjoint. The *redaction* primitive is shared: every adapter's helper calls
  `redact(text)` from `backend/errors` (STORY-002) before attaching the message, so the redaction
  rule is uniform while the SDK-specific mapping stays local to each adapter.
- The provider wire stub (`tests/integration/provider_stub/`, §7a) is a shared test fixture the
  tester builds for this story's integration leg and reuses for STORY-019/020; it is not a shipped
  module and is outside this story's `modules:` surface.
