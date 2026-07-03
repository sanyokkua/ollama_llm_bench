# LLM Client Protocol

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-06-06
**Cross-references:** `08_Cross_Cutting/08-E_interfaces_contracts.md`, `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`, `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`, `11_Services_and_Algorithms/07_ADAPTIVE_TIMEOUT.md`, `11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md`, `11_Services_and_Algorithms/09_READINESS_PROBE.md`, `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`, `08_Cross_Cutting/08-P_judge_protocol.md`, `10_Domain_and_Data/08_REDACTION_PATTERNS.md`

This document specifies the unified provider-facing client of the application — the single `LLMClient` Protocol declared in `08_Cross_Cutting/08-E_interfaces_contracts.md` §10. It defines one chat surface, one embedding surface, a two-method health/probe surface (a cheap **reachability + conditional discovery** probe and a manual **end-to-end inference test**), and three synchronous capability lookups, and it specifies how each `ProviderType` (`OPENAI_COMPATIBLE`, `ANTHROPIC`, `GEMINI`) satisfies that surface: the streaming model used for time-to-first-token measurement, token-usage capture, mid-stream cancellation, the per-provider discovery-support matrix, and the boundary translation of every provider SDK exception into the application error taxonomy. No provider SDK exception type ever escapes a client. Neither of the health/probe methods raises to the caller.

---

## Table of Contents

1. Purpose
2. Inputs
3. Outputs
4. Preconditions
5. Postconditions
6. Algorithm
   - 6.1 The unified contract
   - 6.2 Transport streaming and time-to-first-token
   - 6.3 The `chat` algorithm
   - 6.4 The `chat_stream` surface
   - 6.5 Token-usage capture
   - 6.6 Mid-stream cancellation
   - 6.7 The embedding surface
   - 6.8 The health/probe surface
     - 6.8.1 `probe_health()` — reachability + conditional discovery
     - 6.8.2 `test_inference(model_name)` — manual end-to-end check
   - 6.9 Per-provider-type behaviour matrix
     - 6.9.1 Per-provider-type discovery-support matrix
     - 6.9.2 Per-provider-type inference-test behaviour
   - 6.10 Exception translation
7. Configuration
8. Error handling
9. Threading and concurrency
10. Examples
11. Test cases

---

## 1. Purpose

The LLM Client is the only component in the backend that opens a network connection to a model provider. Every inference call, every judge call, every embedding call, and every health probe passes through one `LLMClient` instance. The client exists to give the rest of the application one stable, provider-agnostic surface — the pipeline asks for a chat completion and receives a `ChatResponse`; it never imports an `openai`, `anthropic`, or `google-genai` symbol and never sees a provider's own exception class.

There is one concrete `LLMClient` implementation per `ProviderType`. Each implementation wraps exactly one provider SDK and is responsible for three boundary duties:

- Translating a `ChatRequest` into that SDK's request shape and translating the SDK's response back into a `ChatResponse`.
- Measuring time-to-first-token and end-to-end duration with the injected `Clock`, and capturing the provider's reported token usage.
- Catching every exception type the SDK can raise and re-raising it as a **`ProviderError`-marked leaf** of the application error taxonomy (`11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` §6.4, D-R-11). `ProviderError` is the provider-surface marker that every leaf raised across this boundary inherits (alongside its retry category), so "the client raises only a `ProviderError`; no raw SDK exception escapes" holds. Where this document writes `TimeoutError` it means `HttpTimeoutError` (the transport-timeout leaf; `TimeoutError` is an alias for it). The leaf simultaneously carries its retry category (`TransientError`/`PermanentError`/`UserError`, category-first in the MRO) and, for `ProviderRateLimitedError`, a `retry_after`, so the retry policy and circuit breaker dispatch on the same object.

The client holds no benchmark state. It does not retry, does not consult the circuit breaker, and does not compute timeout budgets — those concerns belong to the pipeline, the Adaptive Timeout Service, and the Provider Circuit Breaker respectively. The client receives a fully-formed `ChatRequest` (timeout budget already set) and performs exactly one call.

---

## 2. Inputs

| Input | Type | Source | Notes |
|---|---|---|---|
| Provider configuration | `BenchmarkRunProviderEntry` (during a run) or `ProviderConfig` (during provider testing) | Provider Registry | Supplies `provider_type`, `base_url`, resolved secrets, and the `azure_*` fields. |
| Chat request | `ChatRequest` | Inference phase, judge phase | Carries `model`, `messages`, `timeout_ms`, `temperature`, `reasoning_effort`, `response_format`. For the benchmark inference phase the pipeline sets `temperature` from the run snapshot's `benchmark.temperature` (`None` when blank ⇒ the client omits the parameter and the provider default applies; a set value is passed through verbatim and not clamped — D-R-04). The judge phase pins `temperature` to `0.0` (`08_Cross_Cutting/08-P_judge_protocol.md`); there is no `seed` field. |
| Embedding text | `str` | Cosine phase, semantic-keyword phase | Single text to embed; embedding-capable clients only. |
| Cancellation signal | the run's single two-level `CancellationToken` (DD-39) | Benchmark pipeline | Hard level polled at chunk boundaries + abort hook; soft level not observed mid-call; see §6.6. |
| Clock | `Clock` | composition root | Provides `monotonic_ms()` for duration and time-to-first-token measurement. |

All DTOs named above are defined in `10_Domain_and_Data/02_DTOS_AND_ENUMS.md`. The `CancellationToken` is the cooperative-cancellation primitive specified in `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`.

---

## 3. Outputs

| Output | Type | Produced by | Notes |
|---|---|---|---|
| Chat completion | `ChatResponse` | `chat` | Carries `text`, `total_time_ms`, `ttft_ms`, `prompt_tokens`, `completion_tokens`, and an optional `error`. |
| Streamed token deltas | a synchronous iterator of `str` chunks, then a final `ChatResponse` | `chat_stream` | The chunks are the live token stream; the trailing `ChatResponse` carries the assembled text and metrics. |
| Embedding vector | `tuple[float, ...]` | `embed` | The dense vector for one text. |
| Model catalog | `tuple[ModelName, ...]` | `list_models` | May be empty for a reachable provider that exposes none. |
| Provider health | `ProviderHealth` | `probe_health` | Reachability, `discovery_supported`, `model_count` (`None` when discovery skipped), probe latency, optional error string, `probed_at`. |
| Inference-test result | `InferenceTestResult` | `test_inference` | Outcome, latency, response excerpt (displayed as-is — `10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1), optional error (already redacted at the adapter boundary if SDK-originated), `tested_at`. Never raises to the caller. |
| Capability flags | `bool` | `supports_streaming`, `supports_reasoning_effort`, `supports_thinking` | Synchronous lookups. |

No output ever carries a raw provider secret. SDK exception messages — the only output strings the client itself authors — are passed through `redact(text)` at the adapter boundary (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` surface 2) before being placed on `AppError.message` or `InferenceTestResult.last_error`. User-machine model responses (`InferenceTestResult.response_excerpt`, `ChatResponse.text`) are not redacted — they are the user's own machine's output, displayed and stored verbatim.

---

## 4. Preconditions

- The client has been constructed by the Provider Registry from a structurally valid provider configuration; the api-key secret has already been resolved by reading the environment variable whose **name** is stored on the provider (an env-var name that does not resolve — the named variable unset/empty — is a `ConfigurationError` raised by the registry before a client is ever built — see `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`).
- For `chat` and `chat_stream`: `ChatRequest.timeout_ms` is a positive duration; `ChatRequest.messages` is non-empty and well-ordered (an optional leading `SYSTEM` message, then alternating `USER`/`ASSISTANT`, ending with a `USER` message).
- For `embed`: the client is an embedding-capable client (its concrete class implements the embedding surface); a non-embedding client raises `ProviderError` immediately if `embed` is called.
- These methods run on `TaskRunner` worker threads (`16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`); there is no event loop.

## 5. Postconditions

- `chat` returns exactly one `ChatResponse`, or raises exactly one taxonomy exception (`ProviderError` or `TimeoutError`). It never returns and raises, and it never raises a provider SDK exception.
- On a successful `chat`/`chat_stream`, `ChatResponse.total_time_ms` and `streamed` are set; `ttft_ms` is set when the transport streamed at least one token and `supports_streaming()` is `True`, and is `None` otherwise.
- `chat` performs exactly one provider call. Retrying a failed call is the pipeline's responsibility, not the client's.
- Cancellation is two-level (DD-39, `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §5). A **soft** cancellation (pause) is never observed mid-call: the in-flight `chat`/`chat_stream` runs to completion (or its deadline) so its result can be saved. A **hard** cancellation (stop/shutdown) aborts the in-flight call promptly: the client stops consuming at the next chunk boundary, the token's registered abort hook closes the in-flight stream (bounding even a silent no-token wait), the connection is released, and the call raises `TaskCancelledError` — leaving no orphaned background task and persisting nothing.
- `probe_health` always returns a `ProviderHealth`; it never raises.
- The client mutates no persistent state; capability observations are reported to the model-capability service by the caller, not written by the client.

---

## 6. Algorithm

### 6.1 The unified contract

The contract is the `LLMClient` Protocol from `08_Cross_Cutting/08-E_interfaces_contracts.md` §10, extended in this document with one streaming method. The full surface:

| Method | Kind | Purpose |
|---|---|---|
| `list_models()` | blocking | Return the provider's available model names. |
| `probe_health()` | blocking | Reachability + conditional model discovery into a `ProviderHealth`. Never issues an inference call. Never raises. |
| `test_inference(model_name)` | blocking | User-initiated end-to-end chat call against `model_name` using a fixed canned prompt; returns a typed `InferenceTestResult`. Holds the `PROVIDER_TEST` activity for the call duration. Never raises. |
| `chat(request)` | blocking | Convenience wrapper (DD-51): consumes its own `chat_stream` to completion and returns the trailing `ChatResponse`; not a second transport path. |
| `chat_stream(request)` | blocking | THE chat execution surface (DD-51): the live `ChatChunk` stream (content + >=1 Hz heartbeat chunks) and the trailing `ChatResponse`; hides the non-streaming fallback behind the same iterator contract. |
| `embed(text)` | blocking | Return one embedding vector. Embedding-capable clients only. |
| `supports_streaming()` | `def` | Whether the transport supports token streaming. |
| `supports_reasoning_effort()` | `def` | Whether the provider accepts a reasoning-effort parameter. |
| `supports_thinking()` | `def` | Whether the model emits a reasoning/thinking block. |

`chat` and `chat_stream` differ only in what the caller observes: `chat` assembles the stream internally and hands back a finished `ChatResponse`; `chat_stream` yields each token chunk to the caller as it arrives and then hands back the same finished `ChatResponse`. Both use transport streaming underneath; the distinction is purely about the caller's view.

**Consumers (DD-51).** Every user-visible LLM call — the benchmark per-task inference, the per-task judge call, the run-analysis generation, and `test_inference` — executes through `emit_progress_during(chat_stream(...))` (`04_EVALUATION_PIPELINE.md` §6.9), which is what drives the live `_inference_progress` heartbeat and TTFT capture. The Log widget's live-token echo additionally consumes the chunks when `ChatRequest.echo_tokens_to_log` is `True`. The `chat` sugar is for internal callers that need no live progress.

### 6.2 Transport streaming and time-to-first-token

Time-to-first-token (`ttft_ms`) is the interval between issuing the request and receiving the first content token. It can only be measured if the transport delivers tokens incrementally. Therefore **every** chat call — whether the caller invoked `chat` or `chat_stream` — opens the provider connection in streaming mode at the transport layer. `chat` simply does not expose the chunks; it consumes them internally.

The measurement algorithm, identical for every provider type:

1. Read a monotonic start instant `t0` from `Clock.monotonic_ms()` immediately before the network call is issued.
2. Open the streaming response.
3. On the first chunk that carries non-empty content, read `t1` from `Clock.monotonic_ms()` and record `ttft_ms = t1 - t0`. A provider that emits role-only or empty leading chunks does not trip this measurement; only the first content-bearing chunk counts.
4. Continue consuming chunks, appending each chunk's content to a text accumulator.
5. When the stream ends, read `t2` and record `total_time_ms = t2 - t0`.
6. If the stream completes with no content chunk at all, `ttft_ms` stays `None` and the accumulated text is empty (a soft failure — see §6.3).

If the provider cannot stream — `supports_streaming()` is `False`, **or** the stream-open is rejected at call time — the client silently falls back to a single non-streaming request **behind the same iterator contract** (DD-51): the `chat_stream` iterator still yields >=1 Hz heartbeat chunks while waiting (the body read uses the same sub-second per-read socket timeout), then one full-content chunk, then the trailing `ChatResponse`. Callers cannot tell the difference except through the metrics: `ChatResponse.streamed` is `False` and `ttft_ms` is `None` (never fabricated). `total_time_ms` is still measured around the call. In practice all three supported provider types stream, so this fallback is a defensive path rather than a routine one.

### 6.3 The `chat` algorithm

```
function chat(request):
    t0 = clock.monotonic_ms()
    accumulator = ""
    ttft_ms = None
    usage = None
    try:
        with deadline(request.timeout_ms):          # synchronous deadline: per-read socket timeout + monotonic elapsed check
            stream = provider_sdk.open_stream(translate(request))
            token.add_hard_cancel_hook(stream.close)     # abort hook (DD-39); removed in finally — see 6.6
            for chunk in stream:
                check_hard_cancellation()            # hard cancel only (DD-39) — see 6.6
                content = extract_content(chunk)
                if content and ttft_ms is None:
                    ttft_ms = clock.monotonic_ms() - t0
                accumulator += content
                usage = merge_usage(usage, extract_usage(chunk))
    except DeadlineExceeded:
        raise TimeoutError(provider_id, model, elapsed = clock.monotonic_ms() - t0)
    except <any provider SDK exception>:
        raise ProviderError(provider_id, model, translate_message(exc))
    except (HardCancelled, TransportClosedByAbortHook):
        close_stream_quietly()                       # idempotent with the hook's close
        raise TaskCancelledError(token.reason or "cancelled")
    finally:
        token.remove_hard_cancel_hook(stream.close)
    total_time_ms = clock.monotonic_ms() - t0
    soft_error = classify_soft_failure(accumulator)   # empty / refusal
    return ChatResponse(
        text             = accumulator,
        total_time_ms    = total_time_ms,
        ttft_ms          = ttft_ms,
        prompt_tokens    = usage.prompt_tokens     if usage else None,
        completion_tokens= usage.completion_tokens if usage else None,
        error            = soft_error,              # None on a normal completion
    )
```

Key points:

- **One call only.** `chat` issues exactly one request. It never loops over attempts.
- **The timeout budget is given, not computed.** `request.timeout_ms` is the budget the pipeline already computed from the Adaptive Timeout Service. The client wraps the stream consumption in a synchronous deadline of exactly that length (a per-read socket timeout plus a monotonic overall-elapsed check between chunks). Exceeding it raises `TimeoutError`. **Finite-deadline invariant (architecture-tested, SPEC-015):** every provider call path — `chat`, `chat_stream`, `embed`, `probe_health`, `test_inference`, `list_models` — passes a finite deadline to the transport; an infinite or absent transport timeout must not exist anywhere in a client. This invariant, with the hard-cancel escape (DD-39), is what guarantees the dispatcher and the single-inference gate can never be wedged by a hung connection in a live process.
- **Hard failure versus soft failure.** A hard failure — the provider rejected the request, the connection broke, the deadline expired — is raised as `ProviderError` or `TimeoutError`. A soft failure — the provider returned a complete, well-formed response that happens to be empty, or a content-policy refusal that still returned text — is **not** raised: it is reported in `ChatResponse.error` with the assembled `text` left as whatever was returned. The pipeline's deterministic sanity check then decides the result. This split is the contract stated in `08_Cross_Cutting/08-E_interfaces_contracts.md` §10.
- **The reasoning/thinking block stays in `text`.** The client returns the response exactly as the provider delivered it, reasoning block included. Stripping the `<think>`-style block to produce the sanitized response is the inference phase's job, not the client's.

### 6.4 The `chat_stream` surface

`chat_stream` runs the same algorithm as §6.3 but yields each content chunk to the caller before appending it to the accumulator. Its shape:

```
function chat_stream(request):
    ... same setup, deadline, exception translation as chat ...
    for chunk in stream:
        check_hard_cancellation()            # hard cancel only (DD-39) — see 6.6
        content = extract_content(chunk)
        if content and ttft_ms is None:
            ttft_ms = clock.monotonic_ms() - t0
        if content:
            yield content                  # caller observes the live token
        accumulator += content
        usage = merge_usage(usage, extract_usage(chunk))
    ... assemble and return the trailing ChatResponse exactly as chat does ...
```

The caller consumes the chunk stream and, when it ends, receives the same `ChatResponse` it would have received from `chat`. The trailing `ChatResponse` is delivered as the iterator's final, distinguished item (an implementation may model this as a small tagged-union chunk type, or as a `(chunks, response)` pair; the contract is that the caller gets both the live chunks and the final assembled response). Cancellation, deadline, and exception translation are identical to `chat`.

`chat_stream` is the execution surface for every user-visible LLM call (DD-51 — see the Consumers paragraph in §6.1); `chat` is sugar over it for internal no-progress callers.

### 6.5 Token-usage capture

`prompt_tokens` and `completion_tokens` come from the provider's own usage report, never from a client-side tokenizer. The application never re-tokenizes a prompt; doing so would disagree with the provider's billing and with its context-window accounting.

**The client always requests usage.** The `OPENAI_COMPATIBLE` `translate(request)` step sets `stream_options = {"include_usage": true}` on every streaming chat request, so a backend that supports it returns the usage object on the final chunk. Modern Ollama (2024-08+, the §7 minimum), LM Studio, and llama.cpp report usage when asked; the request never silently omits the flag. (Anthropic and Gemini report usage unconditionally through their SDKs.)

Where the usage appears differs by provider type:

- **`OPENAI_COMPATIBLE`** — with `stream_options.include_usage` set (above), the usage object arrives on the final stream chunk; for an endpoint that still does not stream usage it arrives on the response object after the stream closes. The client merges whichever it gets.
- **`ANTHROPIC`** — the SDK emits a `message_start` event carrying input-token usage and a `message_delta` event near the end carrying cumulative output-token usage. The client reads input tokens from the first and output tokens from the last.
- **`GEMINI`** — the usage metadata is attached to the final streamed response object.

If a provider returns no usage at all (even with `include_usage` requested), `prompt_tokens` and `completion_tokens` stay `None` — the application never substitutes a client-side tokenizer count into these provider-grade fields (this keeps them consistent with the provider's billing and context-window accounting). **`tokens_per_second` is computed by the inference phase**, not the client, and is never silently empty in a throughput mode (SPEC-047):

- When `completion_tokens` is present, `tokens_per_second = completion_tokens / (total_time_ms / 1000)` and `BenchmarkResult.tokens_estimated` is `False`.
- When `completion_tokens` is absent, the inference phase computes an **estimated** throughput from the response character count — `est_tokens = ceil(len(raw_response) / 4)` (the same char/4 basis as the live counter, §6.5a, including any reasoning block per MISS-08) — sets `tokens_per_second = est_tokens / (total_time_ms / 1000)`, and sets `BenchmarkResult.tokens_estimated = True`. `completion_tokens` itself stays `None`, so the provider-grade token field is never polluted with a guess; only the throughput metric carries the clearly-flagged estimate. UI and exports render an estimated value with an `≈` marker (Details tab §, Summary/Charts notes). **Basis (MISS-08):** `completion_tokens` is the provider's own count and, for a thinking/reasoning model, **includes the reasoning-block tokens** (which remain in `text` until the inference phase strips them for `sanitized_response`). So `tokens_per_second` reflects *total* generation throughput including hidden reasoning, not visible-answer throughput; cross-model TPS comparison therefore mixes models that emit large reasoning blocks with those that do not. This is documented as the metric's basis; the `AVG_TPS_PER_MODEL` chart label notes it.

#### 6.5a Per-chunk `delta_tokens` and provider availability matrix

Each `ChatChunk` yielded by `chat_stream` (`10_Domain_and_Data/02_DTOS_AND_ENUMS.md` §7.6a) carries an optional `delta_tokens: int | None`. When the provider exposes a per-chunk token count, the client populates this field on the chunk it yields; when the provider does not, the field is `None` and the consumer falls back to a heuristic.

| `ProviderType` | Typical availability of per-chunk `delta_tokens` | Notes |
|---|---|---|
| `OPENAI_COMPATIBLE` | Usually **absent** mid-stream — the OpenAI streaming protocol delivers token usage only at end-of-stream (on the final chunk when `stream_options.include_usage` is set, otherwise on the post-stream response object). Per-chunk counts are not exposed by the standard transport, so `delta_tokens` is `None` on every interior chunk. Locally-hosted backends behind the OpenAI-compatible API (Ollama, LM Studio, llama.cpp) vary; when the backend reports a running count, the client surfaces it as `delta_tokens`. | The final running count is still produced from the end-of-stream usage object via the existing token-usage capture path. |
| `ANTHROPIC` | **Sometimes available** — the SDK exposes a `message_delta` event near the end carrying cumulative output-token usage, and some intermediate streaming events may carry running counts. When present, the client maps them to `delta_tokens`; when absent, the chunk's `delta_tokens` is `None`. | The `message_start` event carries the input-token count only; output-token deltas appear later in the stream. |
| `GEMINI` | **Typically present** — Gemini streaming responses carry usage metadata on each streamed chunk that includes a token count. The client maps that count to `delta_tokens` on the corresponding `ChatChunk`. | Streamed `GenerateContentResponse` parts expose `usage_metadata.candidates_token_count` (or equivalent in the SDK build). |

Consumers that need a running token count for an in-flight stream (notably the benchmark pipeline's live inference-progress emitter — see `11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §"Live inference-progress emission") MUST honour the following source-preference order when computing `tokens_received` on each tick:

1. **Provider-reported per-chunk `delta_tokens`** — sum the `delta_tokens` of every `ChatChunk` whose field is non-`None` since the call started.
2. **Provider-reported running count**, if the SDK exposes one through the chunk shape (for example a cumulative `usage_metadata.candidates_token_count` on each Gemini chunk).
3. **Character-count heuristic** — when neither (1) nor (2) is available, approximate from the accumulated character count as `ceil(char_count / 4)`. The heuristic is a deliberate approximation; consumers that display the value MUST surface that it is an approximation (see `04_Progress_Widget/description.md` §7 and `08_Cross_Cutting/08-I_edge_cases.md`).

The client itself does not maintain a per-call running count for its own purposes — `ChatResponse.completion_tokens` is still taken from the end-of-stream usage object via §6.5. The `delta_tokens` field exists only to make a running counter possible for consumers that need one.

### 6.6 Mid-stream cancellation

The run holds a single two-level `CancellationToken` (DD-39). The client's behaviour depends on the level:

**Soft cancellation (pause) is not observed mid-call.** The chunk loop does **not** poll the soft flag: a paused run lets the in-flight call finish (or hit its deadline) so the unit can be parsed, scored, and saved — that is the work-preserving point of Pause. The pipeline observes the soft cancellation at its own checkpoints between units.

**Hard cancellation (stop / shutdown) aborts the in-flight call promptly**, through two complementary mechanisms:

1. **Chunk-boundary poll.** At the top of each chunk-loop iteration the client checks `token.is_hard_cancelled` (`check_hard_cancellation()` in §6.3 and §6.4). While tokens are streaming, this bounds the abort by one inter-chunk interval (typically milliseconds).
2. **The abort hook.** For the duration of each streaming call the client registers a hook via `token.add_hard_cancel_hook(close_stream)` and removes it in the call's `finally`. `cancel(hard=True)` invokes the hook **on the cancelling thread**; the hook closes the underlying streaming response, so a client blocked in a network read with no chunk arriving (a model still processing its prompt) is unblocked immediately by the transport error. The hook MUST be idempotent, thread-safe, and non-raising; for an SDK whose stream object is a context manager the close is the context exit, for others an explicit close. Closing is best-effort and never itself raises out of the client.

When a hard cancellation is observed (by either mechanism):

1. The client stops consuming the stream and closes it (idempotent with the hook's close).
2. It raises `TaskCancelledError` (the user-category cancellation error). The pipeline records the unit as cancelled — **not** as a provider failure: nothing is persisted, the result row stays `PENDING`, and the cancelled attempt reports no outcome to the circuit breaker or the adaptive-timeout service.

**Bound.** A hard-cancelled call returns within `provider.hard_cancel_max_ms` (default 2000 ms) of the `cancel(hard=True)` call — the hook fires synchronously and the blocked read raises as soon as the transport surfaces the close. The client never force-kills a worker thread; the per-call deadline (§6.3) remains the independent backstop for calls that were never cancelled.

### 6.7 The embedding surface

`embed(text)` is implemented only by embedding-capable clients. An embedding-capable client is one constructed for a provider whose `ProviderType` supports an embeddings endpoint (`OPENAI_COMPATIBLE`, and `GEMINI`); the model used is the one named in the embedding selection (`embedding.selected_model_name`). The `OPENAI_COMPATIBLE` client speaks **only** the OpenAI embeddings dialect (`/v1/embeddings`); native backend routes (for example Ollama's `/api/embed`) are deliberately out of scope — backend expectations and minimum versions are listed in `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md` §7, and the capability probe (`06_EMBEDDING_SERVICE.md` §6.6a) is the authoritative gate.

The algorithm:

1. Read `t0` from `Clock.monotonic_ms()`.
2. Issue a single embeddings request for `text` against the embedding model, wrapped in the embedding timeout budget (§7).
3. On success, return the dense vector as a `tuple[float, ...]`.
4. On the deadline expiring, raise `TimeoutError`. On any provider SDK exception, raise `ProviderError`.

`embed` does not stream and produces no `ttft_ms`. Calling `embed` on a client whose provider type or configured model is not embedding-capable raises `ProviderError` immediately, without a network call. The Embedding Service (a separate internal service) wraps `embed` with an LRU cache so repeated identical texts within a run are embedded once; the client itself is cache-free.

### 6.8 The health/probe surface

The client exposes **two distinct user-visible "test" surfaces**, deliberately separated. The Readiness Service consults only the first; the Settings dialog Provider Edit exposes both as separate user actions (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8).

#### 6.8.1 `probe_health()` — reachability + conditional discovery

The never-raising, never-billable probe used by the Readiness Service (`11_Services_and_Algorithms/09_READINESS_PROBE.md`) and by the Provider Edit dialog's **Test reachability** action. It performs only the checks the provider can be expected to support without producing a billable inference call. The algorithm:

1. Read `t0` from `Clock.monotonic_ms()`.
2. **Reachability step.** Confirm the configured endpoint is reachable: DNS resolution + TCP connect + (where applicable) the basic auth handshake. On failure, redact the message and return `ProviderHealth(reachable=False, discovery_supported=<per-impl>, model_count=None, last_probe_ms=elapsed, last_error=<redacted>, probed_at=<now>)`. The discovery step is **not** attempted.
3. **Discovery step — only if the per-provider implementation supports it.** Each concrete client declares whether it supports a models-list call:
   - `OPENAI_COMPATIBLE` — `discovery_supported = True`; the client calls `GET /v1/models` under the probe timeout (§7). This returns the models the endpoint **advertises**, which is **necessary but not sufficient** for runnability (SPEC-048): an endpoint may advertise a model it cannot currently load, and the count varies by whatever backend is behind the base URL (a single-model server returns one entry — `model_count == 1`, a normal healthy result; a multi-model server may advertise models that are not resident). `model_count == 0` is informational, never unhealthy. The application does not assume what backend serves the URL. Whether an advertised model loads is confirmed at use time by warmup / first inference, not here. Embedding capability is a separate check (`06_EMBEDDING_SERVICE.md` §6.6a), since an endpoint can list a chat model yet expose no embeddings route.
   - `ANTHROPIC` — `discovery_supported = False`; **no models-list endpoint exists**. The client returns `model_count=None` and the probe is considered successful for the reachability step alone. The model catalog is configured (the `default_models` list on `ProviderConfig`).
   - `GEMINI` — `discovery_supported = True`; the client calls the SDK's `models.list()` under the probe timeout, falling back to `False` if the SDK build does not expose that call.
4. On a successful discovery call return `ProviderHealth(reachable=True, discovery_supported=True, model_count=len(models), last_probe_ms=elapsed, last_error=None, probed_at=<now>)`. `len(models) == 0` is a normal return — the Readiness Service interprets it informationally, not as an unhealthy signal.
5. On a failed discovery call (the listing endpoint exists but returned an error), the probe is still considered to have observed reachability; return `ProviderHealth(reachable=True, discovery_supported=True, model_count=None, last_probe_ms=elapsed, last_error=<redacted listing error>, probed_at=<now>)`. The caller (Settings dialog) renders this as "reachable; discovery failed".

The probe NEVER issues a chat or embedding inference call. It MUST remain cheap and idempotent enough to run on a background schedule without producing user-visible cost. **Zero discovered models is NEVER an unhealthy signal**, and a provider whose implementation reports `discovery_supported=False` is healthy when reachable.

`list_models()`, by contrast, **does** raise `ProviderError` when the listing call itself fails, because its callers (the model-picker refresh) want to distinguish "the call failed" from "the provider has no models". An empty catalog from a reachable provider is a normal, non-raising return.

#### 6.8.2 `test_inference(model_name)` — manual end-to-end check

The user-initiated end-to-end check exposed by the Provider Edit dialog's **Test inference** action and emitted on the `_provider_inference_test_completed` event (`08_Cross_Cutting/08-J_event_bus_catalog.md` §5.6). It holds the application-wide single-inference gate (`PROVIDER_TEST`) and issues exactly one chat call to the named model so the user can verify the full request/response path including authentication, model availability, and content delivery. Because the call is billable on paid providers, it is NEVER run automatically: the New Benchmark widget, the Readiness Service, and the application startup sequence never call it. **The same invariant covers `embed()` (DD-48):** no automatic path ever issues an embedding call — the readiness check is handshake-only, and the only `embed()` outside a running benchmark are the user-initiated embedding test (`06_EMBEDDING_SERVICE.md` §6.6a) and the run-start fail-fast probe triggered by the user's Start/Resume (`04_EVALUATION_PIPELINE.md` §4).

The algorithm:

1. Read `t0` from `Clock.monotonic_ms()`.
2. Attempt to acquire the single-inference gate: `inference_activity_store.try_acquire(InferenceActivity.PROVIDER_TEST, ctx)`. If acquisition fails (another activity holds the gate), return `InferenceTestResult(outcome=GATE_BUSY, provider_id=..., model_name=..., latency_ms=None, response_excerpt=None, last_error="An inference activity is already in flight.", tested_at=<now>)` without issuing a call. No new exception class is introduced.
3. Build a `ChatRequest` with the canned prompt (a fixed string such as `"Reply with the single word: ok"` — sent as a single `USER` message). `timeout_ms` is the inference-test deadline (default 30 000 ms; see §7). `reasoning_effort` is `DEFAULT` and `response_format` is `TEXT`. `echo_tokens_to_log` is `False`.
4. Issue the call by reusing the `chat` algorithm (§6.3) **wrapped in the shared progress-emitter helper** (`11_Services_and_Algorithms/04_EVALUATION_PIPELINE.md` §6.9 — `emit_progress_during(...)`), so the Provider Edit inference-test panel sees a live indicator while the call is in flight. The helper is invoked with `context=InferenceContext.PROVIDER_TEST`, `run_id=None`, `result_id=None`, `task_id=None`, `provider_id=<this provider>`, `model_name=<chosen model>`. The Provider Edit inference-test panel subscribes to `_inference_progress` filtered to `context=PROVIDER_TEST` and matching `provider_id`, and renders the live "Testing — …" indicator in place of the Run-button area for the duration of the call (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8.2). The helper is the **same** one used by the Benchmark Pipeline and the Run Analysis Service; only the `context` (and the per-context nullability of `run_id`/`result_id`/`task_id`) differs. **Catch the `chat` algorithm's exceptions** at the helper boundary instead of letting them escape, and apply the boundary translation:

   | `chat` outcome | `InferenceTestResult.outcome` |
   |---|---|
   | Returns a non-empty `ChatResponse.text` (which includes any reasoning/thinking block, so a model that returns only a thinking block still counts) with `error=None` | `SUCCESS` |
   | Returns a `ChatResponse.text` empty/refusal with `error` set | `PROVIDER_ERROR` |
   | Raises `TimeoutError` | `TIMEOUT` |
   | Raises `ProviderError` classified as reachability/connect | `REACHABILITY_FAILED` |
   | Raises `ProviderError` classified as auth | `AUTH_FAILED` |
   | Raises `ProviderError` classified as model-not-found | `MODEL_NOT_FOUND` |
   | Raises `ProviderError` for any other reason | `PROVIDER_ERROR` |

   The classification consults the same SDK exception properties the existing translation block already inspects (Section 6.10); no new SDK-coupling is required.
5. Compute `latency_ms = clock.monotonic_ms() - t0`. On a `GATE_BUSY` early-exit, `latency_ms` is `None`. On `TIMEOUT`, `latency_ms` is the elapsed time when the deadline expired.
6. On `SUCCESS`, truncate the returned text to the first ~200 characters and place it in `response_excerpt` **verbatim** — the application no longer redacts user-machine model responses on display (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` §1; the response excerpt is one of the surfaces redaction does NOT apply to). On any non-success, `response_excerpt` is `None` and `last_error` carries the failure detail; for an SDK-originated failure the message has already been passed through `redact(text)` by the adapter boundary translation block (Section 6.10), so the value placed in `last_error` is canonically safe.
7. Release the gate in `finally`: `inference_activity_store.release(InferenceActivity.PROVIDER_TEST)`. The watchdog auto-release (60 s for `PROVIDER_TEST`; `08_Cross_Cutting/08-I_edge_cases.md` EC-RUN-14) is the safety net if the call hangs past the deadline.
8. Return the assembled `InferenceTestResult`.

The total wall-clock budget for the method MUST NOT exceed 30 seconds — the inference-test deadline plus the connection-establishment timeout. Cancellation is cooperative: the same `CancellationToken` mechanism the run uses applies, but since the Provider Edit dialog has no Stop affordance during the test, the deadline is the effective bound.

The method NEVER raises — even an unexpected internal error is converted into `outcome=PROVIDER_ERROR` with a redacted message. This rule is binding: the Settings dialog UI must never receive a raw exception from this surface.

### 6.9 Per-provider-type behaviour matrix

The three concrete clients differ in SDK, in where usage and the reasoning block appear, and in which exception types they must translate. The contract surface is identical; the table below is the per-type implementation guide.

| Concern | `OPENAI_COMPATIBLE` | `ANTHROPIC` | `GEMINI` |
|---|---|---|---|
| Underlying SDK | `openai` (the OpenAI Python SDK), used for Ollama, LM Studio, llama.cpp, OpenAI, and Azure endpoints | `anthropic` | `google-genai` |
| Endpoint configuration | `base_url`; for Azure additionally `azure_endpoint`, `azure_deployment`, `azure_api_version` (the client selects the Azure transport when the `azure_*` fields are populated) | provider default endpoint; `base_url` only if overridden | provider default endpoint |
| API key | Optional for local hosts (Ollama, LM Studio, llama.cpp typically need none — a placeholder token is sent if the SDK requires a non-empty string); required for OpenAI and Azure | Required | Required |
| Streaming model | Server-sent token deltas; `delta.content` carries text | Typed event stream (`content_block_delta` events carry text) | Streamed `GenerateContentResponse` parts |
| Time-to-first-token | First `delta.content` chunk with non-empty text | First `content_block_delta` of a `text` block | First streamed part carrying text |
| Reasoning/thinking block | Inline in the content for models that emit a `<think>`-style block; surfaced verbatim in `ChatResponse.text` | A distinct `thinking` content block; the client concatenates thinking and text blocks into `text` in document order so the inference phase can strip it | A distinct reasoning part when the model emits one; concatenated into `text` in order |
| Reasoning-effort parameter | Passed through when `supports_reasoning_effort()` is `True` and `reasoning_effort != DEFAULT`; ignored otherwise | Mapped to the SDK's thinking-budget parameter when supported | Mapped to the SDK's equivalent parameter when supported |
| JSON response format | `response_format` mapped to the SDK's JSON-mode parameter | Honoured by prompt-side instruction; the SDK has no separate JSON switch — the client relies on the request messages | Mapped to the SDK's JSON MIME-type / schema parameter |
| Max completion tokens (DD-67) | `max_output_tokens` → `max_tokens` (or `max_completion_tokens` on newer endpoints); always sent | `max_tokens` — **required** by the Anthropic SDK, so the field is always present (default 4096) | `max_output_tokens` in the generation config |
| Token usage | Final chunk or post-stream response object | `message_start` (input) plus final `message_delta` (output) | `usage_metadata` on the final response |
| Embedding capability | Yes — an embeddings endpoint is available | No — `embed` raises `ProviderError` | Yes — an embeddings endpoint is available |
| Exception types to translate | `openai.APIError` and subclasses, `openai.APITimeoutError`, `openai.APIConnectionError`, `openai.AuthenticationError`, plus untyped `httpx` transport failures | `anthropic.APIError` and subclasses, `anthropic.APITimeoutError`, `anthropic.APIConnectionError` | `google-genai` API errors and the SDK's timeout/transport exceptions |

Notes:

- **One client class per type, many providers per class.** A single `OPENAI_COMPATIBLE` client class serves Ollama, LM Studio, llama.cpp, OpenAI, and Azure; the difference between them is configuration (base URL, key, the `azure_*` fields), not code. Two providers exposing the same model name are still distinct targets because the target identity is `(provider_id, model_name)`.
- **Three provider *types* are first-class by product scope (SPEC-091).** The application is local-first but its stated scope explicitly includes cloud providers (`00_Foundation/01_README.md`), so the native `ANTHROPIC` and `GEMINI` clients alongside `OPENAI_COMPATIBLE` are **intentional** surface, not gold-plating. The native SDKs (vs forcing everything through the OpenAI-compatible shape) buy real capability — Anthropic thinking blocks, Gemini per-chunk usage — and are exercised offline by the provider wire stub (DD-56), so the breadth carries a bounded, tested cost.
- **Azure selection (SPEC-114).** Azure mode is a single explicit predicate: an `OPENAI_COMPATIBLE` provider is in **Azure mode iff all three** `azure_endpoint`, `azure_deployment`, and `azure_api_version` are non-empty; with **zero** set it is plain OpenAI-compatible mode. **Any-but-not-all** (one or two set) is rejected as a **structural validation error** at the provider boundary — never silently routed one way or the other — so the selection rule and the structural-validation rule can never disagree. This is the only intra-type branch.
- **`supports_thinking()` is per-model, not per-type.** Whether a given model emits a reasoning block is discovered on first inference and cached in `model_capabilities`; the client reads that cache. `supports_streaming()` and `supports_reasoning_effort()` are effectively per-type for the three supported types but are still exposed per-client so a future transport can differ.

#### 6.9.1 Per-provider-type discovery-support matrix

The per-provider implementation declares whether `probe_health()` performs a model-discovery step. This matrix is the binding contract: consumers of `ProviderHealth` MUST treat `discovery_supported=False` as informational, not unhealthy.

| `ProviderType` | `discovery_supported` | Discovery mechanism | Reachable + no discovery → `ProviderHealth.model_count` |
|---|---|---|---|
| `OPENAI_COMPATIBLE` | `True` | `GET /v1/models` against the configured base URL (Ollama, LM Studio, llama.cpp, OpenAI, and the Azure transport when the `azure_*` fields are populated all support this). | `len(models)`; `0` is valid. |
| `ANTHROPIC` | `False` | None — the Anthropic API exposes no models-list endpoint. The model catalog is provider-configured (the `default_models` list on `ProviderConfig`). | `None` — discovery was not attempted. |
| `GEMINI` | `True` | The `google-genai` SDK's `models.list()` call. Implementations targeting a build that does not expose `models.list()` may report `discovery_supported=False` and behave as `ANTHROPIC` does. | `len(models)`; `0` is valid; `None` when the SDK call is absent. |

The matrix maps directly to the `ProviderHealth.discovery_supported` boolean. The Readiness Service aggregator (`11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.5) and the Settings dialog Test reachability action (`06_Settings_Dialog/sub_dialogs/provider_edit.md` §8) both honour the matrix: an `ANTHROPIC` provider with `reachable=True, discovery_supported=False` is READY, and the Settings UI shows "discovery not supported by this provider" instead of a model count.

#### 6.9.2 Per-provider-type inference-test behaviour

`test_inference(model_name)` is provider-agnostic at the surface level — every concrete client honours the same outcome classification (§6.8.2). The per-type notes:

| `ProviderType` | Inference-test notes |
|---|---|
| `OPENAI_COMPATIBLE` | The canned prompt is sent as a single `USER` message via the standard `/chat/completions` endpoint. The Azure transport variant uses the same call shape; the deployment name is taken from `azure_deployment_raw`. A local Ollama / LM Studio / llama.cpp endpoint will typically return a near-instant `SUCCESS` for any loaded chat model; a misconfigured deployment surfaces as `MODEL_NOT_FOUND` or `AUTH_FAILED`. |
| `ANTHROPIC` | The canned prompt is sent through the Messages API. Because Anthropic provides no discovery, the user must enter the model name manually (the dropdown is empty for this provider). A wrong model name surfaces as `MODEL_NOT_FOUND`. |
| `GEMINI` | The canned prompt is sent through `generate_content`. Model names typically match the `models/gemini-...` pattern; a wrong format surfaces as `MODEL_NOT_FOUND` or `PROVIDER_ERROR` depending on the SDK build. |

### 6.10 Exception translation

Exception translation is the client's single most important boundary duty. The rule, from `08_Cross_Cutting/08-E_interfaces_contracts.md` §3: **no provider SDK exception type ever escapes the LLM Client.**

Each concrete client wraps every network operation in a translation block that catches the SDK's exception hierarchy and re-raises:

| Observed condition | Re-raised as | Resulting result status (set by the pipeline) |
|---|---|---|
| The deadline for the call expired | `TimeoutError` | `FAILED_TIMEOUT` |
| The provider's own timeout/connection-timeout exception | `TimeoutError` | `FAILED_TIMEOUT` |
| Authentication rejected, request rejected, model not found, rate-limited, server error, connection refused | `ProviderError` | `FAILED_PROVIDER` |
| An untyped transport failure (for example a bare `httpx` error from a misconfigured OpenAI-compatible host) | `ProviderError` | `FAILED_PROVIDER` |
| Cooperative cancellation observed mid-stream | `ProviderError` with the cancellation error-kind | recorded as cancelled, not a failure |
| A complete response that is empty or a content refusal | not raised — reported in `ChatResponse.error` | the pipeline's sanity check decides |

The translation block also redacts the message: the provider SDK's exception text can echo back a request that contains a resolved API key value, so the message attached to the re-raised `ProviderError`/`TimeoutError` is passed through `redact(text)` (`10_Domain_and_Data/08_REDACTION_PATTERNS.md` surface 2) before it is attached. From this wrap point onward the message flows everywhere without further redaction (`11_Services_and_Algorithms/17_ERROR_TAXONOMY.md` §6.5). The full taxonomy and the leaf classes are specified in `11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`; this section names only the categories the client raises.

The model-side error string the SDK returns is also inspected to drive capability discovery — for example, an error reported because the model rejected an unsupported reasoning-effort parameter lets the client record `REASONING_EFFORT` as not supported. This observation is returned to the caller as part of the error detail; the client does not write `model_capabilities` itself.

---

## 7. Configuration

The client reads no settings directly during a run; the pipeline passes a fully-formed `ChatRequest` with the timeout already set. The client does, however, use a small number of fixed timeout budgets for the calls the pipeline does not size:

| Setting key | Default | Purpose |
|---|---|---|
| `provider.probe_timeout_ms` | 5000 | Deadline for the reachability handshake and the optional `list_models` call inside `probe_health`, and for `list_models` called by the model picker. |
| `provider.embedding_timeout_ms` | 20000 | Deadline for a single `embed` call. |
| `provider.inference_test_timeout_ms` | 30000 | Deadline for the single chat call inside `test_inference`. Longer than `probe_timeout_ms` because the canned prompt exercises the full model path, including model load on a cold local provider. |
| `provider.connect_timeout_ms` | 5000 | Connection-establishment timeout applied to every provider call, independent of the per-call response deadline. |
| `provider.hard_cancel_max_ms` | 2000 | Upper bound between a hard cancellation (stop / shutdown — DD-39) and the in-flight call's abort: the chunk-boundary poll plus the abort hook's stream close must surface `TaskCancelledError` within this bound. |

These keys are resolved through the Settings Service three-layer hierarchy (`08_Cross_Cutting/08-C_settings_hierarchy.md`); during a run they are read from the run's frozen settings snapshot. `ChatRequest.timeout_ms` always overrides any client-side default for the chat call itself — the chat deadline is exactly the budget the Adaptive Timeout Service produced.

Per-provider configuration (`base_url`, resolved secrets, the `azure_*` fields, `provider_type`) is supplied at client construction by the Provider Registry and is immutable for the life of the client; a configuration change rebuilds the client (`11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`).

---

## 8. Error handling

| Situation | Client behaviour |
|---|---|
| Chat deadline expired | Raise `TimeoutError`; the connection is closed; no partial `ChatResponse` is returned. |
| Hard cancellation (stop / shutdown) during a chat | Abort at the next chunk boundary or via the abort hook's stream close (≤ `provider.hard_cancel_max_ms`); raise `TaskCancelledError`; the connection is closed; nothing partial is returned or persisted, and no failure is reported to the breaker or adaptive timeout. |
| Provider rejected the request (auth, bad model, rate limit, server error) | Catch the SDK exception, redact, raise `ProviderError`. |
| Connection refused or transport failure | Raise `ProviderError`. |
| Cooperative cancellation observed | Close the stream, raise `ProviderError` with the cancellation kind. |
| Complete response that is empty or a refusal | Do not raise; return a `ChatResponse` whose `error` is set and whose `text` holds whatever was returned. |
| `embed` called on a non-embedding-capable client | Raise `ProviderError` immediately, no network call. |
| `list_models` call failed | Raise `ProviderError`. |
| `list_models` succeeded with zero models | Return an empty tuple; do not raise. |
| `probe_health` could not reach the provider | Return `ProviderHealth(reachable=False, discovery_supported=<per-impl>, model_count=None, ...)`; never raise. |
| `probe_health` against a provider whose implementation does not support discovery (Anthropic, or a Gemini SDK build without `models.list()`) | Return `ProviderHealth(reachable=True, discovery_supported=False, model_count=None, ...)` after the reachability handshake; this is healthy, not degraded. |
| `test_inference` invoked while the `InferenceActivityStore` gate is held by another activity | Return `InferenceTestResult(outcome=GATE_BUSY, ...)`; never raise; no provider call is issued. |
| `test_inference` deadline expired | Return `InferenceTestResult(outcome=TIMEOUT, latency_ms=<elapsed>, ...)`; close any open stream; never raise. |
| `test_inference` provider rejected the call (auth, bad model, rate limit, server error) | Classify into `AUTH_FAILED`, `MODEL_NOT_FOUND`, or `PROVIDER_ERROR` per §6.8.2; never raise; the SDK exception type does not escape. |
| `test_inference` reachability failed before any chat round-trip began | Return `InferenceTestResult(outcome=REACHABILITY_FAILED, ...)`; never raise. |
| A provider SDK raises an exception type the client did not anticipate | The translation block's catch-all re-raises it as `ProviderError`; an unanticipated SDK type never escapes from `chat`/`embed`/`list_models`. For `test_inference`, the catch-all maps it to `outcome=PROVIDER_ERROR` instead of propagating. |

The client never logs a user-facing message and never calls the Notification Service. It raises into the pipeline, which records the failure on the `BenchmarkResult`; or it returns into the Readiness Service, which records it on a `ProviderHealth`. All error text the client attaches has already passed through redaction.

---

## 9. Threading and concurrency

- `chat`, `chat_stream`, `embed`, `list_models`, and `probe_health` are blocking synchronous methods invoked only on `TaskRunner` worker threads, per `08_Cross_Cutting/08-E_interfaces_contracts.md` §4 and `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` (D-R-01). They are network-bound; running on a worker thread keeps the Qt GUI thread responsive.
- The three `supports_*` methods are fast-synchronous capability lookups against the in-memory capability cache; they never block and are callable from any thread.
- The pipeline issues **one** inference call at a time (serial execution — D-R-16, `16_CONCURRENCY_MODEL.md` §6.2): there is never more than one in-flight call across the whole application. Each call still runs on a `TaskRunner` worker thread (off the GUI thread), and the call may run on a different worker thread than the previous one, so an `LLMClient` instance must still hold no per-call mutable state — every call carries its own accumulator, timing, and deadline — and the underlying sync HTTP client (e.g. a shared `httpx.Client`) is used from at most one thread at a time.
- Because each call runs on its own worker thread, a long inference never blocks the GUI thread or other concurrent inference calls. Cancellation is checked cooperatively at chunk boundaries (the `CancellationToken`, `threading.Event`-backed).
- Cancellation is cooperative (§6.6); the client never spawns a thread it does not join and never leaves a streaming connection open after a call ends, fails, or is cancelled.

---

## 10. Examples

### 10.1 Happy path — a streamed Ollama inference

A `GRADED` run runs a task against the target `(<UUID4 of Ollama (local)>, qwen2.5:7b)`. (In production the provider's UUID4 is opaque; the description below names the provider by its display name "Ollama (local)" — DD-33.)

1. The inference phase asks the Adaptive Timeout Service for the budget; it returns `45000` ms for the first attempt.
2. The phase builds `ChatRequest(model="qwen2.5:7b", messages=(system, user), timeout_ms=45000, reasoning_effort=DEFAULT, response_format=TEXT)` and calls `chat`.
3. The `OPENAI_COMPATIBLE` client opens a streaming request against `http://localhost:11434/v1`. `t0` is recorded.
4. The first content chunk arrives 380 ms later; `ttft_ms = 380`.
5. Chunks accumulate; the final chunk carries usage `prompt_tokens=210, completion_tokens=540`. The stream closes at `t2`; `total_time_ms = 11_240`.
6. The client returns `ChatResponse(text="...", total_time_ms=11240, ttft_ms=380, prompt_tokens=210, completion_tokens=540, error=None)`.
7. The inference phase strips the reasoning block to produce the sanitized response, computes `tokens_per_second = 540 / 11.24 ≈ 48.0`, and records the result.

### 10.2 Edge case — deadline expiry mid-stream

The same target, but the model stalls.

1. The phase calls `chat` with `timeout_ms=45000`.
2. The client opens the stream; the first chunk arrives at 600 ms (`ttft_ms` would be 600).
3. After 30 chunks the provider stops delivering tokens. The synchronous deadline (monotonic elapsed check between chunks) reaches 45000 ms with the stream still open.
4. The deadline raises; the client catches it, closes the streaming connection, and raises `TimeoutError(provider_id="1f1c0c44-2d8f-4c12-9b8a-b0a1e6c2dc31", model="qwen2.5:7b", elapsed≈45000)` (the `provider_id` is the internal UUID4 of the Ollama (local) provider; DD-33).
5. No `ChatResponse` is returned — the partial accumulator is discarded.
6. The pipeline catches `TimeoutError`, records this attempt as `AttemptOutcome.TIMEOUT` with `ErrorKind.TIMEOUT`, and asks the Adaptive Timeout Service for the next, larger budget. After all attempts are exhausted at the maximum timeout the result becomes `FAILED_TIMEOUT`.

### 10.3 Edge case — a cloud provider with a missing key, then a soft refusal

1. The Provider Registry tries to build the `anthropic` client; the configured `api_key_raw` is the bare env-var name `ANTHROPIC_API_KEY` and that variable is unset. The registry raises `ConfigurationError` before any client is constructed — the client code never runs. (See `11_Services_and_Algorithms/03_PROVIDER_REGISTRY.md`.)
2. With the variable set, the client is built. A later `chat` call returns a complete response that is a content-policy refusal: well-formed, non-empty text.
3. The client does **not** raise. It returns `ChatResponse(text="<the refusal text>", total_time_ms=..., ttft_ms=..., prompt_tokens=..., completion_tokens=..., error="<refusal classification>")`.
4. The inference phase's deterministic sanity check inspects the response and decides the result; the client's job ended at returning the `ChatResponse`.

---

## 11. Test cases

| ID | Scenario | Expected outcome |
|---|---|---|
| LC-01 | `chat` against a fake streaming provider that delivers three content chunks then a usage chunk | One `ChatResponse`; `text` is the concatenation; `ttft_ms` equals the delta to the first content chunk; token counts taken from the usage chunk. |
| LC-02 | The fake provider emits a role-only leading chunk before the first content chunk | `ttft_ms` is measured from the first **content** chunk, not the role-only chunk. |
| LC-03 | The fake provider never delivers a content chunk and closes the stream cleanly | `ChatResponse.text` is empty, `ttft_ms` is `None`, `error` is set to the empty-response classification; no exception raised. |
| LC-04 | The fake provider stalls past `timeout_ms` | `chat` raises `TimeoutError`; the streaming connection is closed; no `ChatResponse` returned. |
| LC-05 | The fake provider raises its SDK's authentication exception | `chat` raises `ProviderError`; the SDK exception type does not escape; the message is redacted. |
| LC-06 | The fake provider raises an SDK exception type the client did not explicitly enumerate | `chat` still raises `ProviderError` via the catch-all; no SDK type escapes. |
| LC-07 | The `CancellationToken` is cancelled after the second chunk | The chunk loop stops at the next checkpoint, the stream is closed, `chat` raises `ProviderError` with the cancellation kind; no orphaned task remains. |
| LC-08 | `chat_stream` against the LC-01 fake provider | The caller observes each content chunk in order, then receives a trailing `ChatResponse` identical to what `chat` would return. |
| LC-09 | `probe_health` against an unreachable host | Returns `ProviderHealth(reachable=False, discovery_supported=<per-impl>, model_count=None, last_error=<redacted>)`; never raises; the discovery step did not run. |
| LC-10 | `probe_health` against a reachable `OPENAI_COMPATIBLE` host that lists zero models | Returns `ProviderHealth(reachable=True, discovery_supported=True, model_count=0)`. |
| LC-10a | `probe_health` against a reachable `ANTHROPIC` provider (no models-list endpoint) | Returns `ProviderHealth(reachable=True, discovery_supported=False, model_count=None)`; never raises; the Readiness Service treats this as healthy (`11_Services_and_Algorithms/09_READINESS_PROBE.md` §6.5). |
| LC-10b | `probe_health` against a reachable provider whose listing call itself failed (5xx on `GET /v1/models`) | Returns `ProviderHealth(reachable=True, discovery_supported=True, model_count=None, last_error=<redacted listing error>)`; never raises. |
| LC-11 | `list_models` when the listing call itself fails | Raises `ProviderError` (distinct from the LC-10 zero-models case). |
| LC-12 | `embed` on an `ANTHROPIC` client | Raises `ProviderError` immediately with no network call. |
| LC-13 | `embed` on an `OPENAI_COMPATIBLE` client against a fake embeddings endpoint | Returns a `tuple[float, ...]` of the expected dimensionality. |
| LC-14 | `ANTHROPIC` `chat` where the response carries a `thinking` block and a `text` block | `ChatResponse.text` contains both, concatenated in document order, so the inference phase can strip the thinking block. |
| LC-15 | An `OPENAI_COMPATIBLE` provider configured with the `azure_*` fields populated | The client selects the Azure transport; the call succeeds against the Azure-shaped endpoint. |
| LC-16 | Two concurrent `chat` calls on one client instance against different models | Both complete independently; neither call's accumulator, timing, or deadline interferes with the other. |
| LC-17 | A provider that reports no usage object at all | `prompt_tokens` and `completion_tokens` are `None`; the client does not fabricate counts. |
| LC-18 | `test_inference` against a reachable provider whose canned-prompt call returns "ok" | Returns `InferenceTestResult(outcome=SUCCESS, latency_ms=<measured>, response_excerpt=<redacted "ok">, last_error=None)`; the `PROVIDER_TEST` gate was acquired and released; never raises. |
| LC-19 | `test_inference` invoked while the `InferenceActivityStore` is held by `BENCHMARK_RUN` | Returns `InferenceTestResult(outcome=GATE_BUSY, latency_ms=None, response_excerpt=None, last_error=<gate-busy message>)`; no provider call issued; the gate state is unchanged. |
| LC-20 | `test_inference` whose chat call hangs past the inference-test deadline | Returns `InferenceTestResult(outcome=TIMEOUT, latency_ms≈<deadline>, response_excerpt=None, last_error=<redacted timeout>)`; the stream is closed; never raises; the gate is released. |
| LC-21 | `test_inference` against a model name that the provider does not recognise | Returns `InferenceTestResult(outcome=MODEL_NOT_FOUND, latency_ms=<measured>, response_excerpt=None, last_error=<redacted>)`. |
| LC-22 | `test_inference` against an `ANTHROPIC` provider (entered model name manually) returning a valid response | Returns `InferenceTestResult(outcome=SUCCESS, ...)` exactly as for any other provider type. |
| LC-23 | `test_inference` raises an unexpected internal error (defensive catch-all) | Returns `InferenceTestResult(outcome=PROVIDER_ERROR, last_error=<redacted>)`; the gate is released; the method never propagates the exception. |
| LC-24 | `test_inference` emits live progress events | While the chat call is in flight, `_inference_progress` events fire at ≥ 1 Hz with `context=InferenceContext.PROVIDER_TEST`, `run_id=None`, `result_id=None`, `task_id=None`, and the call's `(provider_id, model_name)`. The Provider Edit inference-test panel (subscribed with that filter and matching `provider_id`) renders the live indicator; emission stops when the call ends and no progress event fires afterwards. |
