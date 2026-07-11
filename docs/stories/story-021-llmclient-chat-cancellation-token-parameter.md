---
id: STORY-021
title: Add a mandatory CancellationToken parameter to the canonical LLMClient chat surface
status: done
spec_clauses:
  - 08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm
  - 11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation
  - 16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken
modules:
  - backend/provider_registry/
acceptance_criteria:
  - STORY-021-AC-1
  - STORY-021-AC-2
  - STORY-021-AC-3
depends_on:
  - STORY-006
  - STORY-017
adrs:
  - ADR-0005
owner: coder
estimate: S
---

# STORY-021 — Add a mandatory CancellationToken parameter to the canonical LLMClient chat surface

## Goal

Correct the canonical `LLMClient` Protocol so its two chat methods receive the run's live
two-level `CancellationToken`, making the hard-cancellation contract of the LLM Client Protocol
(§6.6, DD-39) expressible at all. Every concrete adapter must be able to register an abort hook
against its in-flight stream and poll the hard-cancel flag at chunk boundaries; the shipped
Protocol gives it no token to do so. This story threads that token in as a mandatory,
keyword-only parameter so a caller can never omit it and silently forfeit hard cancellation.

This is a **Protocol correction, not new behaviour.** The interface gap was discovered while
planning STORY-018 (the first concrete `LLMClient`): STORY-017 transcribed `08-E` §10 exactly as
written, but §10 itself omits the token that the algorithms in §6.3/§6.4/§6.6 already reference.
The correction is recorded in ADR-0005; per `02_STORY_FORMAT.md` §8 an accepted Protocol a
`done` story owns is amended through a new story plus an ADR, never a silent edit to STORY-017.

## In scope

- Amend `LLMClient.chat` and `LLMClient.chat_stream` on
  `backend/provider_registry/protocols.py` (the one canonical declaration re-exported by every
  provider adapter per STORY-017) to take a mandatory keyword-only `token: CancellationToken`
  with no default:
  ```python
  def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse: ...
  def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream: ...
  ```
  `CancellationToken` is imported from `ollama_llm_bench.backend.concurrency` (STORY-006).
- Update the `chat`/`chat_stream` docstrings to document the `token` parameter and the
  hard-cancellation contract: the method registers an idempotent abort hook against the
  in-flight stream, polls the hard-cancel flag at each chunk boundary, and raises
  `TaskCancelledError` promptly (within `provider.hard_cancel_max_ms`) on a hard cancel, closing
  the stream and returning nothing partial. `TaskCancelledError` is the one user-category
  cancellation error from `backend/errors` (STORY-002); soft cancellation is never observed
  mid-call.
- Update every `LLMClient` fake/stub inside `backend/provider_registry/` (`testing.py` and any
  local double under `provider_registry/tests/`) so its `chat`/`chat_stream` match the corrected
  keyword-only signature and keep satisfying the Protocol under structural typing.

## Out of scope

- Any concrete adapter's *use* of the token (registering the abort hook, the chunk-boundary
  poll, raising `TaskCancelledError`) — owned by STORY-018 (`OPENAI_COMPATIBLE`), STORY-019
  (`ANTHROPIC`), and STORY-020 (`GEMINI`), each of which consumes this corrected signature.
- `list_models`, `probe_health`, `test_inference`, `embed`, `supports_streaming`,
  `supports_reasoning_effort`, `supports_thinking`, and `close` — unchanged. `test_inference`
  has no Stop affordance during the test, so its own deadline is the effective bound (§6.8);
  `probe_health`, `embed`, and `list_models` are bounded purely by their own finite timeout
  budgets (SPEC-015), not by cooperative mid-call cancellation.
- Adding a token field to `ChatRequest` — explicitly rejected in ADR-0005; the token is a live
  mutable handle passed alongside the frozen `ChatRequest`, never inside it. No
  `backend/domain/` change is made by this story.
- Threading the token from the pipeline/dispatcher into the client call site — pipeline work
  owned by `backend/benchmark_pipeline/`, not this story; this story only shapes the Protocol.

## Spec inputs

- `08_Cross_Cutting/08-E_interfaces_contracts.md#10-llm-client` — the authoritative `LLMClient`
  Protocol whose `chat`/`chat_stream` signatures this story corrects; the threading/error notes
  confirming both methods are blocking worker-thread calls and that no SDK exception escapes.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#63-the-chat-algorithm` — the `chat`
  pseudocode that already references `token.add_hard_cancel_hook(...)`,
  `check_hard_cancellation()`, and `token.remove_hard_cancel_hook(...)`, demonstrating the token
  must be a parameter of the method.
- `11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md#66-mid-stream-cancellation` — the
  two-mechanism hard-cancel contract (chunk-boundary poll + abort hook), the raise of
  `TaskCancelledError`, and the `provider.hard_cancel_max_ms` bound the docstring must state.
- `16_Engineering_Standards/04_CONCURRENCY_STANDARD.md#5-the-cancellationtoken` — the single
  framework-agnostic `CancellationToken` type, "created per run and threaded through every work
  unit," and the single user-category `TaskCancelledError` this Protocol names.

## Design constraints

- `backend/provider_registry/` is Qt-free and asyncio-free; the import added is only
  `from ollama_llm_bench.backend.concurrency import CancellationToken` — no PySide6, no
  `asyncio`, no concrete provider adapter (the STORY-017 import contract is unchanged except for
  the added `backend/concurrency` dependency).
- The parameter is keyword-only (`*`) with no default value — a caller must pass the token
  explicitly; an omitted or `None` token is not permitted (ADR-0005).
- The change is a signature-and-docstring edit to the canonical Protocol plus companion edits to
  this module's own test doubles; it adds no public API symbol and touches no runtime logic in
  `backend/provider_registry/` beyond keeping its fakes conformant. This keeps the story `S`.
- The corrected symbol is the single declaration each adapter re-exports (STORY-017): this story
  changes it in exactly one place.

## Acceptance criteria

### STORY-021-AC-1

Given the canonical `LLMClient` Protocol on `backend/provider_registry/protocols.py`, when its
`chat` and `chat_stream` signatures are inspected, then each declares a keyword-only parameter
`token` annotated `CancellationToken` (from `ollama_llm_bench.backend.concurrency`) with no
default value, and `request: ChatRequest` remains the sole positional parameter.

### STORY-021-AC-2

Given a class whose `chat`/`chat_stream` omit the `token` parameter (the pre-correction
signature), when it is type-checked against the corrected `LLMClient` Protocol under
`mypy --strict`, then it is rejected as not structurally satisfying the Protocol; and given a
class whose `chat`/`chat_stream` include the keyword-only `token: CancellationToken`, then it is
accepted.

### STORY-021-AC-3

Given the `LLMClient` fakes and stubs shipped inside `backend/provider_registry/` (`testing.py`
and any double under `provider_registry/tests/`), when they are type-checked against the
corrected Protocol, then each fake's `chat`/`chat_stream` accepts the keyword-only
`token: CancellationToken` and the module's existing STORY-017 tests continue to pass unchanged
in behaviour.

## Test plan

- STORY-021-AC-1 — unit (introspection of the Protocol member signatures via
  `inspect.signature`), colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_llm_client_protocol.py`,
  `test_chat_methods_require_keyword_only_cancellation_token`.
- STORY-021-AC-2 — architecture/type test (a `mypy --strict` fixture pair, or a
  `typing.runtime_checkable` structural check over a conforming and a non-conforming stub),
  same file, `test_missing_token_fails_protocol_and_present_token_satisfies`.
- STORY-021-AC-3 — unit, colocated
  `src/ollama_llm_bench/backend/provider_registry/tests/test_testing_fakes_conform.py`,
  `test_registry_fakes_match_corrected_chat_signature`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-021.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for `backend/provider_registry/`,
  including the newly-permitted `backend/concurrency` import.
- [ ] An architecture test confirms `backend/provider_registry/` still imports no Qt, no
  `asyncio`, and no concrete provider adapter after the added `backend/concurrency` import.
- [ ] The STORY-017 test suite for `backend/provider_registry/` still passes with its fakes
  updated to the corrected signature.
- [ ] The traceability record validates with no orphan clause and no orphan test for STORY-021.
- [ ] The module inventory is unchanged.

## Notes

- **Why a new story and not an edit to STORY-017.** STORY-017 is `done` and owns the canonical
  `LLMClient` Protocol declaration. The `08-E` §10 surface it transcribed omitted the token the
  §6.3/§6.6 algorithms rely on — a genuine spec-internal inconsistency, not a design change. Per
  `02_STORY_FORMAT.md` §8 and `traceability-and-stories.md`, correcting an accepted Protocol a
  `done` story depends on requires a new story plus an ADR (ADR-0005), preserving the
  traceability record rather than silently rewriting a landed story.
- **Downstream fan-out.** STORY-018 depends on this story so its AC-6 hard-cancellation
  behaviour has a token to work with; STORY-019 and STORY-020 (still `draft`) consume the same
  corrected signature. No caller currently passes a token, so no production call site outside the
  three adapters needs updating within this story's scope.
  </content>
