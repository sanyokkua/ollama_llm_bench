---
id: STORY-020
title: Implement the Gemini LLM client adapter with per-chunk usage and SDK discovery
status: draft
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#64-the-chat_stream-surface
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65-token-usage-capture
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65a-per-chunk-delta_tokens-and-provider-availability-matrix
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#67-the-embedding-surface
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#681-probe_health--reachability--conditional-discovery
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#682-test_inferencemodel_name--manual-end-to-end-check
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#691-per-provider-type-discovery-support-matrix
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#610-exception-translation
modules:
  - backend/provider_gemini/
acceptance_criteria:
  - STORY-020-AC-1
  - STORY-020-AC-2
  - STORY-020-AC-3
  - STORY-020-AC-4
  - STORY-020-AC-5
  - STORY-020-AC-6
  - STORY-020-AC-7
  - STORY-020-AC-8
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

# STORY-020 — Implement the Gemini LLM client adapter with per-chunk usage and SDK discovery

## Goal

Provide the one concrete `LLMClient` that wraps the `google-genai` SDK. It streams
`GenerateContentResponse` parts to measure time-to-first-token, captures per-chunk usage metadata,
concatenates any reasoning part with the text part into `ChatResponse.text` in document order,
discovers models through the SDK's `models.list()` (falling back to `discovery_supported=False` when
the SDK build lacks the call), runs the gated inference test through `generate_content`, embeds text
through the Gemini embeddings endpoint, and translates every `google-genai` error into the
application taxonomy with a redacted message.

## In scope

- The concrete `GEMINI` `LLMClient` and the `make_gemini_client` factory on `api.py`, re-exporting
  the canonical `LLMClient` Protocol from `backend/provider_registry` (STORY-017) and guarded by
  `icontract` on programmer invariants only.
- **`chat_stream` / `chat`** — streamed `GenerateContentResponse` parts, TTFT from the first
  text-carrying part, the internal-consume `chat` sugar, the finite-deadline wrap (SPEC-015), and
  the DD-51 non-streaming fallback behind the same iterator contract.
- **Token-usage capture (§6.5)** — `usage_metadata` from the final streamed response object;
  `prompt_tokens`/`completion_tokens` left `None` when absent.
- **Per-chunk `delta_tokens` (§6.5a)** — mapping each streamed chunk's
  `usage_metadata.candidates_token_count` (or the SDK-build equivalent) onto the `ChatChunk`'s
  `delta_tokens` field, and `None` when a chunk exposes none.
- **Reasoning-part handling (§6.9 matrix)** — concatenating a distinct reasoning part and the text
  part into `ChatResponse.text` in document order; the client does not strip the reasoning part.
- **Mid-stream cancellation (§6.6, DD-39)** — the chunk-boundary hard-cancel poll plus the
  idempotent abort hook closing the in-flight stream, raising `TaskCancelledError` within
  `provider.hard_cancel_max_ms`; the soft flag is never polled mid-call.
- **`embed(text)` (§6.7)** — one Gemini embeddings call returning a `tuple[float, ...]`, wrapped in
  the embedding timeout.
- **`probe_health()` (§6.8.1, §6.9.1)** — reachability handshake then discovery via the SDK's
  `models.list()` with `discovery_supported=True`; falling back to `discovery_supported=False`,
  `model_count=None` when the SDK build lacks `models.list()`; never raises; zero models is healthy.
- **`test_inference(model_name)` (§6.8.2, §6.9.2)** — acquire `PROVIDER_TEST` on the
  single-inference gate (returning `GATE_BUSY` when held), issue the canned prompt through
  `generate_content`, and classify the outcome; never raises; release the gate in `finally`.
- **Exception translation and redaction (§6.10)** — the boundary block catching the
  `google-genai` timeout/transport exceptions → `TimeoutError`, the SDK's API errors → `ProviderError`,
  the catch-all for unenumerated SDK types → `ProviderError`, with the attached message passed
  through `redact(text)`.
- The `testing.py` fake implementing the `LLMClient` Protocol with no network or SDK.

## Out of scope

- The canonical `LLMClient` Protocol declaration and provider-registry routing — owned by
  STORY-017; this story re-exports and implements that Protocol.
- The `OPENAI_COMPATIBLE` and `ANTHROPIC` adapters — owned by STORY-018 and STORY-019; provider
  adapters never import one another.
- The provider wire stub (`tests/integration/provider_stub/`, §7a) — a shared test fixture, not a
  shipped module.
- The running-token-count consumer that prefers `delta_tokens` over the char/4 heuristic —
  a `backend/benchmark_pipeline` inference-progress concern; this story only populates
  `delta_tokens` on the chunk, it does not compute the running counter.
- Reasoning-part stripping for `sanitized_response` and `tokens_per_second` — inference-phase
  concerns; the client returns `text` verbatim and computes no throughput.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client` — the Protocol surface this adapter
  implements, including the never-raises rules and the soft-failure-in-`ChatResponse.error`
  contract.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm` — the one-call rule,
  the given-not-computed deadline, the finite-deadline invariant, and the hard-vs-soft failure
  split.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#64-the-chat_stream-surface` — yielding each
  content chunk then the identical trailing `ChatResponse`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65-token-usage-capture` — reading
  `usage_metadata` from the final streamed response object.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#65a-per-chunk-delta_tokens-and-provider-availability-matrix`
  — mapping Gemini's per-chunk `usage_metadata.candidates_token_count` onto `ChatChunk.delta_tokens`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation` — the two
  hard-cancel mechanisms, the idempotent abort hook, and the `hard_cancel_max_ms` bound.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#67-the-embedding-surface` — the single
  embeddings call and the timeout budget.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#681-probe_health--reachability--conditional-discovery`
  — the reachability-then-`models.list()` algorithm, the SDK-absent fallback, and the never-raise,
  zero-models-is-healthy rules.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#682-test_inferencemodel_name--manual-end-to-end-check`
  — the gate acquire/release, the canned prompt, the outcome-classification table, and never-raise.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#691-per-provider-type-discovery-support-matrix`
  — `GEMINI` discovery via `models.list()`, `discovery_supported=True`, and the SDK-absent fallback
  to `False`.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#610-exception-translation` — the SDK-type →
  taxonomy mapping and the mandatory boundary redaction of the attached message.

## Design constraints

- `backend/provider_gemini/` is Qt-free and asyncio-free; it imports only the `google-genai` SDK,
  `backend/domain`, `backend/errors`, `backend/infra`, `backend/events`, and the canonical
  `LLMClient` Protocol re-exported from `backend/provider_registry` (`01_MODULE_INVENTORY.md`
  §4.3). No PySide6.
- Provider adapters never import one another (`import-linter` "Provider adapters are independent").
- `chat`, `chat_stream`, `embed`, `list_models`, `probe_health`, and `test_inference` are blocking
  synchronous methods invoked only on `TaskRunner` worker threads (D-R-01); the client holds no
  per-call mutable state.
- Every call path passes a **finite** deadline to the transport (SPEC-015).
- No `google-genai` SDK exception type ever escapes any method; every re-raised message is passed
  through `redact(text)`; `ChatResponse.text` and `InferenceTestResult.response_excerpt` are stored
  verbatim, never redacted.
- `icontract` on the `api.py` factory guards programmer invariants only.

## Acceptance criteria

### STORY-020-AC-1

Given a fake Gemini stream that delivers text-carrying `GenerateContentResponse` parts then a final
response with `usage_metadata`, when `chat` is called, then it returns one `ChatResponse` whose
`text` is the assembled content, whose `ttft_ms` equals the interval to the first text-carrying
part, and whose `prompt_tokens`/`completion_tokens` come from the final `usage_metadata`.

### STORY-020-AC-2

Given a fake Gemini stream whose chunks each carry `usage_metadata.candidates_token_count`, when
`chat_stream` yields chunks, then each yielded `ChatChunk` carries that count in `delta_tokens`; and
given a chunk that exposes no per-chunk count, its `delta_tokens` is `None`.

### STORY-020-AC-3

Given a fake Gemini response carrying a reasoning part followed by a text part, when `chat` is
called, then `ChatResponse.text` contains both parts concatenated in document order (reasoning
first), so a later inference phase can strip the reasoning part.

### STORY-020-AC-4

Each `google-genai` SDK failure translates to a taxonomy exception per this table, and in every case
no SDK exception type escapes and the attached message has been passed through `redact(text)`:

| Observed SDK condition                                        | Re-raised as                        |
| ------------------------------------------------------------- | ----------------------------------- |
| the SDK's timeout / transport-timeout exception               | `TimeoutError`                      |
| the SDK's API error (auth, bad model, rate limit, 5xx)        | `ProviderError`                     |
| an SDK exception type the client did not explicitly enumerate | `ProviderError` (via the catch-all) |

### STORY-020-AC-5

Given a `chat` call in flight and the run's `CancellationToken` is hard-cancelled after the second
part, when the cancellation fires, then the client stops consuming at the next chunk boundary or via
the abort hook, closes the stream, and raises `TaskCancelledError` within
`provider.hard_cancel_max_ms`, leaving no orphaned streaming connection.

### STORY-020-AC-6

Each `probe_health` scenario produces the result per this table, and `probe_health` never raises:

| Scenario                                           | Result                                                                                                                        |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| reachable, SDK `models.list()` returns N models    | `ProviderHealth(reachable=True, discovery_supported=True, model_count=N)`                                                     |
| reachable, SDK `models.list()` returns zero models | `ProviderHealth(reachable=True, discovery_supported=True, model_count=0)`                                                     |
| reachable, SDK build lacks `models.list()`         | `ProviderHealth(reachable=True, discovery_supported=False, model_count=None)`                                                 |
| unreachable host                                   | `ProviderHealth(reachable=False, discovery_supported=True, model_count=None, last_error=<redacted>)`; discovery not attempted |

### STORY-020-AC-7

Given a `GEMINI` client embeds a text against a fake embeddings endpoint, when `embed(text)` is
called, then it returns a `tuple[float, ...]` of the endpoint's dimensionality; and given the
embeddings call raises the SDK's error, `embed` raises `ProviderError` with a redacted message.

### STORY-020-AC-8

Each `test_inference(model_name)` scenario produces the `InferenceTestResult.outcome` per this
table, the method never raises, and on any non-`GATE_BUSY` path the `PROVIDER_TEST` gate is acquired
before the call and released in `finally`:

| Scenario                                                  | `outcome`                                       |
| --------------------------------------------------------- | ----------------------------------------------- |
| gate already held by another activity                     | `GATE_BUSY` (no call issued, `latency_ms=None`) |
| canned-prompt call returns non-empty text                 | `SUCCESS`                                       |
| call exceeds the inference-test deadline                  | `TIMEOUT`                                       |
| model name in the wrong format / not recognised           | `MODEL_NOT_FOUND`                               |
| auth rejected                                             | `AUTH_FAILED`                                   |
| any other provider rejection or unexpected internal error | `PROVIDER_ERROR` (redacted `last_error`)        |

## Test plan

- STORY-020-AC-1 — integration (real adapter + real `google-genai` SDK against the wire stub),
  colocated `src/ollama_llm_bench/backend/provider_gemini/tests/test_chat_stream.py`,
  `test_chat_assembles_text_and_captures_ttft_and_usage`. Covers LC-01/LC-02.
- STORY-020-AC-2 — integration, colocated
  `src/ollama_llm_bench/backend/provider_gemini/tests/test_delta_tokens.py`,
  `test_per_chunk_usage_maps_to_delta_tokens`.
- STORY-020-AC-3 — integration, same file as AC-1,
  `test_reasoning_and_text_parts_concatenated_in_order`. Covers LC-14 (Gemini analogue).
- STORY-020-AC-4 — integration (table-driven over the wire-stub error matrix), colocated
  `src/ollama_llm_bench/backend/provider_gemini/tests/test_exception_translation.py`,
  `test_sdk_failure_translates_to_taxonomy_and_redacts`. Covers LC-05/LC-06.
- STORY-020-AC-5 — unit (cancellation token set + a fake stream), colocated
  `src/ollama_llm_bench/backend/provider_gemini/tests/test_cancellation.py`,
  `test_hard_cancel_aborts_stream_within_bound`. Covers LC-07.
- STORY-020-AC-6 — integration (table-driven over the probe scenarios), colocated
  `src/ollama_llm_bench/backend/provider_gemini/tests/test_probe_health.py`,
  `test_probe_health_discovery_and_fallback_per_scenario`. Covers LC-09/LC-10.
- STORY-020-AC-7 — integration, colocated
  `src/ollama_llm_bench/backend/provider_gemini/tests/test_embed.py`,
  `test_embed_returns_vector_and_translates_errors`. Covers LC-13.
- STORY-020-AC-8 — unit (table-driven over the outcome map; a fake `InferenceActivityStore`),
  colocated `src/ollama_llm_bench/backend/provider_gemini/tests/test_inference_test.py`,
  `test_test_inference_classifies_outcome_and_manages_gate`. Covers LC-19/LC-21/LC-23.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-020.
- [ ] The `LLMClient` shared contract-test suite (§6a) runs against both the real adapter (wire
  stub, §7a) and `provider_gemini/testing.py`, and both legs pass.
- [ ] Table-driven tests cover the exception-translation matrix (AC-4), the probe scenarios (AC-6),
  and the `test_inference` outcome map (AC-8).
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/provider_gemini/`.
- [ ] An architecture test confirms `backend/provider_gemini/` imports no Qt, no `asyncio`, and no
  sibling provider adapter, and that no `google-genai` SDK exception type escapes any public method.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-020.
- [ ] The module inventory is unchanged.

## Notes

- **Ambiguity #3 (discovery matrix) — applied here.** `GEMINI` supports discovery via the SDK's
  `models.list()` with `discovery_supported=True`, falling back to `discovery_supported=False`,
  `model_count=None` (Anthropic-style) when the SDK build does not expose `models.list()` (AC-6).
- **Ambiguity #5 (translation/redaction placement) — same resolution as STORY-018/019:** an
  adapter-local `_translate_exception` helper in `_internal/` mapping the `google-genai` hierarchy,
  calling the shared `redact(text)` from `backend/errors`; no cross-adapter translation utility.
- Per-chunk `delta_tokens` (§6.5a) is the one place Gemini differs materially from the other two
  adapters at the chunk level; this story only *populates* the field, leaving the running-count
  source-preference logic to the pipeline's inference-progress emitter.
