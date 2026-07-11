---
id: STORY-019
title: Implement the Anthropic LLM client adapter with thinking-block handling and exception translation
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#64-the-chat_stream-surface
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65-token-usage-capture
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#681-probe_health--reachability--conditional-discovery
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#682-test_inferencemodel_name--manual-end-to-end-check
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#69-per-provider-type-behaviour-matrix
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#691-per-provider-type-discovery-support-matrix
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#610-exception-translation
modules:
  - backend/provider_anthropic/
acceptance_criteria:
  - STORY-019-AC-1
  - STORY-019-AC-2
  - STORY-019-AC-3
  - STORY-019-AC-4
  - STORY-019-AC-5
  - STORY-019-AC-6
  - STORY-019-AC-7
  - STORY-019-AC-8
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

# STORY-019 — Implement the Anthropic LLM client adapter with thinking-block handling and exception translation

## Goal

Provide the one concrete `LLMClient` that wraps the `anthropic` SDK. It streams the typed event
stream to measure time-to-first-token, concatenates a `thinking` block and its `text` block into
`ChatResponse.text` in document order so the inference phase can strip the thinking block, reads
input usage from `message_start` and output usage from the final `message_delta`, reports
`discovery_supported=False` because Anthropic exposes no models-list endpoint, runs the gated
inference test, always sends the SDK-required `max_tokens`, raises `ProviderError` from `embed`
because Anthropic has no embeddings endpoint, and translates every `anthropic` SDK exception into
the application taxonomy with a redacted message.

## In scope

- The concrete `ANTHROPIC` `LLMClient` and the `make_anthropic_client` factory on `api.py`,
  re-exporting the canonical `LLMClient` Protocol from `backend/provider_registry` (STORY-017) and
  guarded by `icontract` on programmer invariants only.
- **`chat_stream` / `chat`** — the Anthropic typed event stream (`content_block_delta` events carry
  text), TTFT from the first `content_block_delta` of a `text` block, the internal-consume `chat`
  sugar, the finite-deadline wrap (SPEC-015), and the DD-51 non-streaming fallback behind the same
  iterator contract.
- **Thinking-block handling (§6.9 matrix)** — concatenating the distinct `thinking` content block
  and the `text` content block into `ChatResponse.text` in document order; the client does not strip
  the thinking block.
- **Token-usage capture (§6.5)** — input tokens from `message_start`, cumulative output tokens from
  the final `message_delta`; both `None` when absent.
- **`max_tokens` always sent (DD-67)** — the SDK-required `max_tokens` is always present (default
  4096\) so a request never omits it.
- **Mid-stream cancellation (§6.6, DD-39)** — the chunk-boundary hard-cancel poll plus the
  idempotent abort hook closing the in-flight stream, raising `TaskCancelledError` within
  `provider.hard_cancel_max_ms`; the soft flag is never polled mid-call.
- **`probe_health()` (§6.8.1, §6.9.1)** — reachability handshake only with
  `discovery_supported=False` and `model_count=None`; no models-list call is made; a reachable
  Anthropic provider is healthy; never raises.
- **`embed(text)`** — raises `ProviderError` immediately with no network call (Anthropic exposes no
  embeddings endpoint).
- **`test_inference(model_name)` (§6.8.2, §6.9.2)** — acquire `PROVIDER_TEST` on the
  single-inference gate (returning `GATE_BUSY` when held), issue the canned prompt through the
  Messages API against the manually entered model name, and classify the outcome; never raises;
  release the gate in `finally`.
- **Exception translation and redaction (§6.10)** — the boundary block catching
  `anthropic.APITimeoutError`/`APIConnectionError` → `TimeoutError`, `anthropic.APIError` and its
  subclasses → `ProviderError`, the catch-all for unenumerated SDK types → `ProviderError`, with
  the attached message passed through `redact(text)`.
- The `testing.py` fake implementing the `LLMClient` Protocol with no network or SDK.

## Out of scope

- The canonical `LLMClient` Protocol declaration and provider-registry routing — owned by
  STORY-017; this story re-exports and implements that Protocol.
- The `OPENAI_COMPATIBLE` and `GEMINI` adapters — owned by STORY-018 and STORY-020; provider
  adapters never import one another.
- The provider wire stub (`tests/integration/provider_stub/`, §7a) — a shared test fixture, not a
  shipped module.
- Reasoning-block stripping for `sanitized_response`, `tokens_per_second`, and the manual
  model-name entry UI — inference-phase and Settings-dialog concerns, not the client; the client
  returns `text` verbatim (thinking block included) and computes no throughput.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client` — the Protocol surface this adapter
  implements, including the never-raises rules and the soft-failure-in-`ChatResponse.error`
  contract.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm` — the one-call rule,
  the given-not-computed deadline, the finite-deadline invariant, and the hard-vs-soft failure
  split.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#64-the-chat_stream-surface` — yielding each
  content chunk then the identical trailing `ChatResponse`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65-token-usage-capture` — reading input
  tokens from `message_start` and output tokens from the final `message_delta`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation` — the two
  hard-cancel mechanisms, the idempotent abort hook, and the `hard_cancel_max_ms` bound.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#681-probe_health--reachability--conditional-discovery`
  — the reachability-only algorithm for a discovery-unsupported provider and the never-raise rule.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#682-test_inferencemodel_name--manual-end-to-end-check`
  — the gate acquire/release, the canned prompt, the outcome-classification table, and never-raise.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#69-per-provider-type-behaviour-matrix` — the
  Anthropic thinking-block concatenation, the required `max_tokens`, and `embed` raising
  `ProviderError`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#691-per-provider-type-discovery-support-matrix`
  — `ANTHROPIC` `discovery_supported=False`, `model_count=None`, and the "healthy when reachable"
  rule.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#610-exception-translation` — the SDK-type →
  taxonomy mapping and the mandatory boundary redaction of the attached message.

## Design constraints

- `backend/provider_anthropic/` is Qt-free and asyncio-free; it imports only the `anthropic` SDK,
  `backend/domain`, `backend/errors`, `backend/infra`, `backend/events`, and the canonical
  `LLMClient` Protocol re-exported from `backend/provider_registry` (`01_MODULE_INVENTORY.md`
  §4.3). No PySide6.
- Provider adapters never import one another (`import-linter` "Provider adapters are independent").
- `chat`, `chat_stream`, `probe_health`, and `test_inference` are blocking synchronous methods
  invoked only on `TaskRunner` worker threads (D-R-01); the client holds no per-call mutable state.
- Every call path passes a **finite** deadline to the transport (SPEC-015).
- No `anthropic` SDK exception type ever escapes any method; every re-raised message is passed
  through `redact(text)`; `ChatResponse.text` (thinking block included) and
  `InferenceTestResult.response_excerpt` are stored verbatim, never redacted.
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-019-AC-1

Given a fake Anthropic event stream that delivers text `content_block_delta` events then a final
`message_delta`, when `chat` is called, then it returns one `ChatResponse` whose `text` is the
assembled content and whose `ttft_ms` equals the interval to the first `text`-block
`content_block_delta`.

### STORY-019-AC-2

Given a fake Anthropic response carrying a `thinking` content block followed by a `text` content
block, when `chat` is called, then `ChatResponse.text` contains both blocks concatenated in document
order (thinking first), so a later inference phase can strip the thinking block.

### STORY-019-AC-3

Given a fake Anthropic stream that carries `message_start` input usage and a final `message_delta`
output usage, when `chat` is called, then `ChatResponse.prompt_tokens` comes from `message_start`
and `ChatResponse.completion_tokens` comes from the final `message_delta`; and given a response
with no usage at all, both are `None`.

### STORY-019-AC-4

Each `anthropic` SDK failure translates to a taxonomy exception per this table, and in every case no
`anthropic` exception type escapes and the attached message has been passed through `redact(text)`:

| Observed SDK condition                                           | Re-raised as                        |
| ---------------------------------------------------------------- | ----------------------------------- |
| `anthropic.APITimeoutError` / `APIConnectionError` timeout       | `TimeoutError`                      |
| `anthropic.APIError` subclass (auth, bad model, rate limit, 5xx) | `ProviderError`                     |
| an SDK exception type the client did not explicitly enumerate    | `ProviderError` (via the catch-all) |

### STORY-019-AC-5

Given a `chat` call in flight and the run's `CancellationToken` is hard-cancelled after the second
event, when the cancellation fires, then the client stops consuming at the next chunk boundary or
via the abort hook, closes the stream, and raises `TaskCancelledError` within
`provider.hard_cancel_max_ms`, leaving no orphaned streaming connection.

### STORY-019-AC-6

Each `probe_health` / `embed` scenario produces the result per this table:

| Method and scenario                                   | Result                                                                                                                  |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `probe_health` against a reachable Anthropic provider | `ProviderHealth(reachable=True, discovery_supported=False, model_count=None)`; no models-list call issued; never raises |
| `probe_health` against an unreachable host            | `ProviderHealth(reachable=False, discovery_supported=False, model_count=None, last_error=<redacted>)`; never raises     |
| `embed(text)` on the Anthropic client                 | raises `ProviderError` immediately with no network call                                                                 |

### STORY-019-AC-7

Each `test_inference(model_name)` scenario produces the `InferenceTestResult.outcome` per this
table, the method never raises, and on any non-`GATE_BUSY` path the `PROVIDER_TEST` gate is acquired
before the call and released in `finally`:

| Scenario                                                  | `outcome`                                       |
| --------------------------------------------------------- | ----------------------------------------------- |
| gate already held by another activity                     | `GATE_BUSY` (no call issued, `latency_ms=None`) |
| canned-prompt call returns non-empty text                 | `SUCCESS`                                       |
| call exceeds the inference-test deadline                  | `TIMEOUT`                                       |
| manually entered model name is not recognised             | `MODEL_NOT_FOUND`                               |
| auth rejected                                             | `AUTH_FAILED`                                   |
| any other provider rejection or unexpected internal error | `PROVIDER_ERROR` (redacted `last_error`)        |

### STORY-019-AC-8

Given any Anthropic chat request, when it is built for the SDK, then `max_tokens` is always present
(default 4096 when the caller supplied none), so the SDK-required field is never omitted.

## Test plan

- STORY-019-AC-1 — integration (real adapter + real `anthropic` SDK against the wire stub),
  colocated `src/ollama_llm_bench/backend/provider_anthropic/tests/test_chat_stream.py`,
  `test_chat_assembles_text_and_captures_ttft`. Covers LC-01/LC-02.
- STORY-019-AC-2 — integration, same file, `test_thinking_and_text_blocks_concatenated_in_order`.
  Covers LC-14.
- STORY-019-AC-3 — integration, colocated
  `src/ollama_llm_bench/backend/provider_anthropic/tests/test_usage.py`,
  `test_usage_read_from_message_start_and_message_delta`. Covers LC-17.
- STORY-019-AC-4 — integration (table-driven over the wire-stub error matrix), colocated
  `src/ollama_llm_bench/backend/provider_anthropic/tests/test_exception_translation.py`,
  `test_sdk_failure_translates_to_taxonomy_and_redacts`. Covers LC-05/LC-06.
- STORY-019-AC-5 — unit (cancellation token set + a fake stream), colocated
  `src/ollama_llm_bench/backend/provider_anthropic/tests/test_cancellation.py`,
  `test_hard_cancel_aborts_stream_within_bound`. Covers LC-07.
- STORY-019-AC-6 — integration (table-driven over the probe/embed scenarios), colocated
  `src/ollama_llm_bench/backend/provider_anthropic/tests/test_probe_and_embed.py`,
  `test_probe_health_reachability_only_and_embed_raises`. Covers LC-10a/LC-12.
- STORY-019-AC-7 — unit (table-driven over the outcome map; a fake `InferenceActivityStore`),
  colocated `src/ollama_llm_bench/backend/provider_anthropic/tests/test_inference_test.py`,
  `test_test_inference_classifies_outcome_and_manages_gate`. Covers LC-19/LC-22/LC-23.
- STORY-019-AC-8 — unit, colocated
  `src/ollama_llm_bench/backend/provider_anthropic/tests/test_request_translation.py`,
  `test_max_tokens_always_present_in_request`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-019.
- [ ] The `LLMClient` shared contract-test suite (§6a) runs against both the real adapter (wire
  stub, §7a) and `provider_anthropic/testing.py`, and both legs pass.
- [ ] Table-driven tests cover the exception-translation matrix (AC-4), the probe/embed scenarios
  (AC-6), and the `test_inference` outcome map (AC-7).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/provider_anthropic/`.
- [ ] An architecture test confirms `backend/provider_anthropic/` imports no Qt, no `asyncio`, and
  no sibling provider adapter, and that no `anthropic` SDK exception type escapes any public method.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-019.
- [ ] The module inventory is unchanged.

## Notes

- **Ambiguity #3 (discovery matrix) — applied here.** `ANTHROPIC` has no models-list endpoint, so
  `probe_health` reports `discovery_supported=False`, `model_count=None`, and is healthy when
  reachable; the model catalog is provider-configured (`default_models`) and the inference-test
  model name is entered manually (AC-6, AC-7).
- **Ambiguity #5 (translation/redaction placement) — same resolution as STORY-018:** an
  adapter-local `_translate_exception` helper in `_internal/` mapping the `anthropic` hierarchy,
  calling the shared `redact(text)` from `backend/errors`; no cross-adapter translation utility.
