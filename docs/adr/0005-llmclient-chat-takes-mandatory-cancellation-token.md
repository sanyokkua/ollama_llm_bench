# ADR-0005 — Thread the CancellationToken into LLMClient.chat/chat_stream as a mandatory keyword-only parameter

**Status:** accepted
**Date:** 2026-07-11
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** DD-39, SPEC-015

## Context and problem statement

STORY-017 shipped the canonical `LLMClient` Protocol on
`backend/provider_registry/protocols.py`, transcribed from
`08_Cross_Cutting/08-E_interfaces_contracts.md` §10. Its chat surface was declared as
`chat(self, request: ChatRequest) -> ChatResponse` and
`chat_stream(self, request: ChatRequest) -> ChatStream` — no cancellation handle in either
signature. While planning STORY-018 (the first concrete `LLMClient`, the OpenAI-compatible
adapter) the architect found this leaves the adapter no way to satisfy its own hard-cancel
contract: `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §6.3/§6.4/§6.6 have the
adapter register an abort hook via `token.add_hard_cancel_hook(stream.close)`, poll
`token.is_hard_cancelled` at each chunk boundary, and raise `TaskCancelledError` within
`provider.hard_cancel_max_ms` — but the `token` those algorithms reference is never handed to
the method. `ChatRequest` (`backend/domain/models.py`) carries no token field either, and as a
frozen cross-boundary `msgspec.Struct` it deliberately holds no live mutable handle.

The `08-E` §10 Protocol is an `Accepted` spec surface that a `done` story (STORY-017) owns and
that every provider adapter (STORY-018/019/020) must implement identically. Under this
project's discipline (`02_STORY_FORMAT.md` §8, `traceability-and-stories.md`) an accepted
Protocol from a `done` story is never silently re-edited: a change needs its own story and,
because this Protocol is the single contract every adapter satisfies, an ADR. The question is:
how should the run's `CancellationToken` reach `chat`/`chat_stream` so the hard-cancel contract
becomes expressible?

## Decision drivers

- The hard-cancel contract of §6.6 (DD-39) is unimplementable unless the adapter receives the
  live two-level `CancellationToken` the run holds — it must register an abort hook against the
  in-flight stream and poll the hard flag at chunk boundaries.
- `CancellationToken` is a live, mutable, thread-safe handle (`threading.Event`-backed,
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md` §5). It is categorically not
  pipeline-input content and must not travel inside a frozen `msgspec.Struct`.
- `ChatRequest` is a `msgspec.Struct(frozen=True, kw_only=True, gc=False)` describing the
  request payload (messages, deadline, format) — a value object, not a carrier of run-scoped
  concurrency handles.
- Every real caller of `chat`/`chat_stream` already holds the run's token: the concurrency
  standard requires one token "created per run and threaded through every work unit" (§5).
  Making the token omittable would let a caller silently forfeit hard cancellation for that
  call — exactly the failure the abort-hook mechanism exists to prevent.
- Whatever shape is chosen binds STORY-018/019/020 identically; it must be uniform.

## Considered options

- Option A — Add a mandatory keyword-only `token: CancellationToken` parameter to
  `chat`/`chat_stream` on the canonical Protocol.
- Option B — Add a `token` field to `ChatRequest` and leave the method signatures unchanged.
- Option C — Add an optional `token: CancellationToken | None = None` parameter, defaulting to
  no cancellation when omitted.

## Decision outcome

Chosen option: **Option A.** `chat` and `chat_stream` take a mandatory, keyword-only
`token: CancellationToken` (`from ollama_llm_bench.backend.concurrency import CancellationToken`, STORY-006) with no default:

```python
def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse: ...
def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream: ...
```

Keyword-only keeps the two arguments unambiguous at every call site (`request` is the payload,
`token` is the concurrency handle) and matches the `TaskRunner.submit(fn, *, token=...)` shape
already established in STORY-006. Having no default makes the cancellation contract
non-optional: every caller passes the run's token explicitly, so the abort hook and
chunk-boundary poll of §6.6 are always wired and the `provider.hard_cancel_max_ms` bound
always holds. The token stays a live handle passed alongside the immutable `ChatRequest`, never
embedded in it, preserving `ChatRequest`'s frozen value-object nature. The other `LLMClient`
methods (`list_models`, `probe_health`, `test_inference`, `embed`, the `supports_*` queries,
`close`) are unchanged: `test_inference` has no Stop affordance during the test so its own
deadline is the effective bound (§6.8), and `probe_health`/`embed`/`list_models` are bounded by
their own finite timeout budgets (SPEC-015), not by cooperative mid-call cancellation.

### Consequences

- Positive — The §6.6 hard-cancel contract becomes expressible and type-checkable: an adapter
  that ignores the token fails its own AC, and a caller that forgets to pass one fails to
  compile. `ChatRequest` stays a pure frozen value object. The signature is uniform across all
  three adapters.
- Negative — This is a source-incompatible change to a Protocol a `done` story shipped: every
  call site and every `LLMClient` fake/stub (including STORY-017's own test doubles) must be
  updated to pass/accept the keyword-only token, or they fail structural typing under
  `mypy --strict`. That fan-out is why this correction is its own story, not an edit to
  STORY-017.
- Neutral — STORY-018/019/020 consume this corrected signature directly; STORY-019 and
  STORY-020 are still `draft`, so their bodies inherit the token without a separate correction.

## Pros and cons of the options

### Option A — Mandatory keyword-only `token` parameter

- Good — Makes cancellation non-optional; keeps `ChatRequest` frozen and handle-free; uniform
  and type-checkable across adapters; matches the existing `submit(fn, *, token=...)` shape.
- Bad — Source-incompatible; every caller and every fake must be updated in one story.

### Option B — `token` field on `ChatRequest`

- Good — No method-signature change.
- Bad — Puts a live, mutable, thread-safe handle inside a `frozen=True` `msgspec.Struct` meant
  to be pipeline-input-shaped and immutable-per-call-content; conflates request payload with
  run-scoped concurrency state; muddies equality/serialisation of the request value.

### Option C — Optional `token` defaulting to `None`

- Good — Backwards-source-compatible; existing call sites compile unchanged.
- Bad — Lets a caller omit the token and silently forfeit hard cancellation for that call,
  defeating the whole §6.6 guarantee and the `hard_cancel_max_ms` bound; every adapter would
  need a `None`-guard branch that can never be safely exercised in production.

## Links

- Related ADRs: —
- Spec clauses:
  `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client`,
  `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm`,
  `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation`,
  `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken`
- Stories: STORY-021 (applies this decision), STORY-018 / STORY-019 / STORY-020 (consume the
  corrected signature)
  </content>
  </invoke>
