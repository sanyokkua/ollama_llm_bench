# STORY-018 — OpenAI-Compatible LLM Client Adapter Implementation Plan

> **For agentic workers:** This project has its own implementation/verification split —
> the `coder` agent (Sonnet) implements this plan task-by-task, then the `tester` agent
> writes and runs the acceptance-criteria-proving tests named in the story's Test Plan,
> then `spec-conformance-reviewer` gates `done`. Do **not** use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` — dispatch
> each task below to a fresh `coder` invocation (or execute inline in one `coder` session
> task-by-task), then hand off to `tester`. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Implement `backend/provider_openai_compatible/` — the one concrete `LLMClient`
serving Ollama, LM Studio, llama.cpp, OpenAI, and Azure — satisfying all 10 acceptance
criteria of `docs/stories/story-018-openai-compatible-provider-adapter.md`.

**Architecture:** A single concrete class (`_internal/client.py::OpenAICompatibleClient`)
built by `api.py::make_openai_client(...)` (icontract-guarded factory), structurally
satisfying the `LLMClient` Protocol re-exported from `backend/provider_registry`. Five
small `_internal/` helper modules carry the non-trivial logic (exception translation,
Azure transport selection, the streaming/TTFT algorithm, health/discovery, and the
inference-test outcome classifier) so no single file exceeds the project's 300-line class
/ 50-line function limits. A `testing.py` fake (`FakeOpenAICompatibleClient`) gives
downstream modules a network-free double.

**Tech Stack:** `openai` Python SDK (new dependency, sync client only — no `asyncio`),
`httpx` (transitive, for the untyped-transport-failure exception class), `msgspec` DTOs
already defined in `backend/domain`, `icontract` on the `api.py` factory.

## Global Constraints

- Python 3.13, `mypy --strict`, `ruff` (see `.claude/rules/coding-style.md`,
  `.claude/rules/linting.md`) — every file in this plan must pass both with zero
  suppressions unless a suppression carries a specific code and justification.
- `backend/provider_openai_compatible/` imports **only**: the `openai` SDK (and its
  transitive `httpx` exception types when needed for the untyped-transport-failure leaf),
  `backend.domain`, `backend.errors`, `backend.infra`, `backend.events`, and
  `backend.provider_registry` (Protocol re-export only) — confirmed against the import
  boundary table in `.claude/rules/project-structure.md` and the three `import-linter`
  contracts already present in `pyproject.toml` (Backend layer is Qt-free; Provider
  adapters are independent; Only compose.py wires concrete adapters — all three already
  list this module by name, so no `pyproject.toml` contract edit is needed).
- Every cross-boundary data structure is an existing `msgspec.Struct` from
  `backend.domain` — this story defines **no new DTOs**, so `models.py` is omitted from
  the module's public surface (see Task 3).
- `chat`, `chat_stream`, `embed`, `list_models`, `probe_health`, `test_inference` are
  blocking, invoked only on `TaskRunner` worker threads; the client holds **no per-call
  mutable state** — every call builds its own accumulator, timing, and deadline locally.
- Every provider call path passes a **finite** deadline to the transport (SPEC-015) — the
  `openai` SDK client is constructed with `timeout=httpx.Timeout(...)` per call (never a
  default/absent timeout), and `max_retries=0` (the SDK's own retry loop is disabled —
  this application's retry policy lives one layer up, in the pipeline, not the client;
  see `docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md` §1,
  "The client holds no benchmark state. It does not retry...").
- No provider SDK exception type ever escapes any public method; every re-raised message
  is passed through `redact(text)` from `backend.errors` before being attached to the
  raised leaf's `message`.
- `icontract` on `api.py::make_openai_client` guards **programmer** invariants only
  (`provider.provider_type is ProviderType.OPENAI_COMPATIBLE`) — never provider-supplied
  config content (that is `ConfigurationError` territory, already handled upstream by
  `backend/provider_registry/_internal/client_builder.py::validate_structure`).
- **Test-authoring split (resolved from `CLAUDE.md`'s Agents Reference table):** the
  `coder` agent implements production code and may write small, narrowly-scoped
  **developer-verification tests** for pure/isolable logic to drive its own TDD loop —
  these live in files **not** named in the story's Test Plan and carry no `Proves:`
  docstring line, so they are inert with respect to `traceability.yaml`. The `tester`
  agent, in a separate follow-up invocation, writes the actual AC-proving tests named in
  the story's Test Plan (`test_chat_stream.py`, `test_deadline.py`,
  `test_exception_translation.py`, `test_cancellation.py`, `test_probe_health.py`,
  `test_embed.py`, `test_inference_test.py`, `test_azure_mode.py`), most of which need
  the provider wire stub (`tests/integration/provider_stub/`) that the story's own
  "Out of scope" section assigns to the tester, not the coder. **This plan's tasks
  therefore end at "coder implements + self-verifies"; it does not end at "AC proven."**
  A final task in this plan hands off to `tester`.

______________________________________________________________________

## File Structure

```
src/ollama_llm_bench/backend/provider_registry/
    protocols.py                        # MODIFY (Task 1) — add `token` param

src/ollama_llm_bench/backend/provider_openai_compatible/
    __init__.py                         # MODIFY (Task 3) — facade
    api.py                              # CREATE (Task 9) — make_openai_client(...)
    testing.py                          # CREATE (Task 10) — FakeOpenAICompatibleClient
    _internal/
        __init__.py                     # CREATE (Task 3)
        exception_translation.py        # CREATE (Task 4)
        azure_transport.py              # CREATE (Task 5)
        chat_stream_impl.py             # CREATE (Task 6) — the ChatStream + chat_stream algorithm
        discovery.py                    # CREATE (Task 7) — probe_health + list_models
        inference_test.py               # CREATE (Task 8) — test_inference outcome classification
        client.py                       # CREATE (Task 9) — OpenAICompatibleClient (assembles the above)
    tests/
        __init__.py                     # CREATE (Task 3)
        conftest.py                     # CREATE (Task 3) — shared fake-SDK fixtures
        test_dev_exception_translation.py   # CREATE (Task 4) — dev-verification only
        test_dev_azure_transport.py         # CREATE (Task 5) — dev-verification only
        test_dev_chat_stream_impl.py        # CREATE (Task 6) — dev-verification only
        test_dev_discovery.py               # CREATE (Task 7) — dev-verification only
        test_dev_inference_test.py          # CREATE (Task 8) — dev-verification only

docs/stories/story-017-provider-registry-and-llm-client-protocol.md   # MODIFY (Task 1) — addendum note
pyproject.toml                          # MODIFY (Task 2) — add `openai` dependency
.claude/rules/external-libraries.md     # MODIFY (Task 2) — dependency table entry
uv.lock                                 # regenerated by `uv add` (Task 2)
```

**Why this split.** `exception_translation.py`, `azure_transport.py`, `discovery.py`, and
`inference_test.py` are each a handful of small pure/near-pure functions with no shared
state — they follow the same "free functions in `_internal/`" shape as the sibling
`provider_registry/_internal/client_builder.py`. `chat_stream_impl.py` is kept separate
from `client.py` because the streaming/TTFT/usage-accumulation algorithm (§6.2–§6.6 of
the LLM Client Protocol doc) is the single most intricate piece of this story and
benefits from being independently unit-testable against a hand-built fake SDK stream,
without constructing a full `OpenAICompatibleClient`. `client.py` itself is the thin
assembly layer implementing the `LLMClient` Protocol's method signatures and delegating
to the helpers — this keeps it under the 300-line class-size ceiling.

______________________________________________________________________

## Task 1: Extend the `LLMClient` Protocol with a `CancellationToken` parameter

This must land **first** — every later task's `chat`/`chat_stream` signature depends on
it, and STORY-019/STORY-020 (not yet built) inherit the corrected signature for free.

**Files:**

- Modify: `src/ollama_llm_bench/backend/provider_registry/protocols.py`
- Modify: `docs/stories/story-017-provider-registry-and-llm-client-protocol.md` (Notes
  section — addendum, append-only)

**Interfaces:**

- Produces: `LLMClient.chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse`

- Produces: `LLMClient.chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream`

- Produces: `CancellationToken` now imported into `provider_registry/protocols.py` from
  `backend.concurrency`.

- [ ] **Step 1: Read the current signatures to confirm line numbers before editing**

Run: `grep -n "def chat\|def chat_stream\|^from\|^import" src/ollama_llm_bench/backend/provider_registry/protocols.py`

Expected: shows `def chat(self, request: ChatRequest) -> ChatResponse:` and
`def chat_stream(self, request: ChatRequest) -> ChatStream:` with no `token` parameter,
confirming the gap this task fixes.

- [ ] **Step 2: Add the `CancellationToken` import**

In `src/ollama_llm_bench/backend/provider_registry/protocols.py`, add to the existing
`from ollama_llm_bench.backend.domain import (...)` import block's neighbourhood a new
import line:

```python
from ollama_llm_bench.backend.concurrency import CancellationToken
```

Place it in the first-party import block, alphabetically before the existing
`from ollama_llm_bench.backend.domain import (...)` line (imports are sorted
alphabetically within the first-party block per `.claude/rules/coding-style.md`).

- [ ] **Step 3: Extend `LLMClient.chat` and `LLMClient.chat_stream`**

Replace:

```python
    def chat(self, request: ChatRequest) -> ChatResponse:
        """Consume this client's own ``chat_stream`` to completion.

        Convenience wrapper (DD-51); not a second transport path. Error
        behaviour is identical to ``chat_stream``.

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
        """
        ...

    def chat_stream(self, request: ChatRequest) -> ChatStream:
        """Execute a chat call, returning a synchronous stream of chunks (DD-51).

        THE chat execution surface; invoked on a worker thread. The transport
        always opens in streaming mode; when the provider cannot stream the
        client falls back to a non-streaming request behind the same iterator
        contract.

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
        """
        ...
```

With:

```python
    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Consume this client's own ``chat_stream`` to completion.

        Convenience wrapper (DD-51); not a second transport path. Error
        behaviour is identical to ``chat_stream``.

        Args:
            request: The fully-formed chat request; ``timeout_ms`` is the
                budget the caller already computed.
            token: The run's two-level ``CancellationToken`` (DD-39). A hard
                cancellation aborts the in-flight call at the next chunk
                boundary or via the registered abort hook (§6.6); a soft
                cancellation is never observed mid-call.

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
            TaskCancelledError: ``token`` was hard-cancelled mid-call.
        """
        ...

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        """Execute a chat call, returning a synchronous stream of chunks (DD-51).

        THE chat execution surface; invoked on a worker thread. The transport
        always opens in streaming mode; when the provider cannot stream the
        client falls back to a non-streaming request behind the same iterator
        contract.

        Args:
            request: The fully-formed chat request; ``timeout_ms`` is the
                budget the caller already computed.
            token: The run's two-level ``CancellationToken`` (DD-39), held by
                the client for the duration of the call so it can register a
                hard-cancel abort hook and poll ``token.is_hard_cancelled`` at
                each chunk boundary (§6.6).

        Raises:
            ProviderError: The provider rejected the request or returned an
                unusable response.
            TimeoutError: The call exceeded ``request.timeout_ms``.
            TaskCancelledError: ``token`` was hard-cancelled mid-call.
        """
        ...
```

Update the module docstring's top-of-file summary line (currently describing
`chat`/`chat_stream` without mentioning cancellation) is not required — the per-method
docstrings above are the authoritative signature documentation.

- [ ] **Step 4: Verify the edit with mypy on this one file**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_registry/protocols.py`
Expected: `Success: no issues found in 1 source file`

- [ ] **Step 5: Append the addendum note to STORY-017**

Open `docs/stories/story-017-provider-registry-and-llm-client-protocol.md`, find the
`## Notes` section (create one at the end of the file, after `## Definition of done`, if
it does not already exist), and append:

```markdown
## Notes

- **Addendum (STORY-018).** `LLMClient.chat`/`chat_stream` originally declared no
  `CancellationToken` parameter, matching the printed signature block in
  `08_Cross_Cutting/08-E_interfaces_contracts.md` §10. Implementing STORY-018 surfaced
  that `02_LLM_CLIENT_PROTOCOL.md` §6.3/§6.6 requires the client itself to hold the token
  (to call `token.add_hard_cancel_hook(stream.close)` and poll
  `token.is_hard_cancelled` at chunk boundaries) — there was no other channel for the
  token to reach the client. Both methods now take a required keyword-only
  `token: CancellationToken` parameter. This is a completion of a signature the spec's
  algorithm always required, not a change to accepted scope: zero concrete `LLMClient`
  implementations existed at the time of this addendum, so the fix carries no migration
  cost and STORY-019/STORY-020 inherit the corrected signature directly.
```

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_registry/protocols.py \
        docs/stories/story-017-provider-registry-and-llm-client-protocol.md
git commit -m "STORY-018: extend LLMClient.chat/chat_stream with a CancellationToken parameter"
```

______________________________________________________________________

## Task 2: Add the `openai` SDK dependency

**Files:**

- Modify: `pyproject.toml`

- Modify: `.claude/rules/external-libraries.md`

- Modify: `uv.lock` (regenerated, not hand-edited)

- [ ] **Step 1: Add the dependency at the latest stable version**

Run: `uv add openai`

Expected: `pyproject.toml`'s `dependencies` array gains an `openai>=X.Y.Z` line (X.Y.Z is
whatever `uv add` resolves as latest-stable at run time — do not hardcode a version by
hand), and `uv.lock` is regenerated.

- [ ] **Step 2: Confirm the floor landed correctly**

Run: `grep -n '"openai' pyproject.toml`
Expected: one line inside `[project] dependencies`, e.g. `"openai>=2.x.x",`.

- [ ] **Step 3: Update the dependency-version policy table**

In `.claude/rules/external-libraries.md`, under `## Runtime dependencies`, add a row
(alphabetically is not enforced there — append after the existing table's last row,
`typing-extensions`):

```markdown
| `openai` | `>=<the resolved floor from Step 1>` | OpenAI-compatible SDK — the transport for Ollama, LM Studio, llama.cpp, OpenAI, and Azure (`backend/provider_openai_compatible/`) |
```

- [ ] **Step 4: Sync and verify the environment installs cleanly**

Run: `uv sync --frozen --all-extras --dev`
Expected: exits 0, no dependency resolution errors.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .claude/rules/external-libraries.md
git commit -m "STORY-018: add openai SDK dependency"
```

______________________________________________________________________

## Task 3: Scaffold the module's public surface and test package

**Files:**

- Modify: `src/ollama_llm_bench/backend/provider_openai_compatible/__init__.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/__init__.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/__init__.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/conftest.py`

**Interfaces:**

- Produces: `FakeSdkStream` fixture and `FakeSdkChunk`/`FakeSdkUsage` helper builders used
  by every dev-verification test in Tasks 4–8 (defined once here to avoid duplication).

- [ ] **Step 1: Write `_internal/__init__.py`**

```python
"""Private internals of ``backend.provider_openai_compatible``. Do not import."""
```

- [ ] **Step 2: Write `tests/__init__.py`**

```python
"""Colocated unit tests for ``backend.provider_openai_compatible``."""
```

- [ ] **Step 3: Write `tests/conftest.py` — hand-built fake OpenAI SDK stream primitives**

These fakes stand in for the real `openai` SDK's streamed-chunk shape (a `ChatCompletionChunk`
with `.choices[0].delta.content` / `.choices[0].delta.role` and an optional `.usage`) without
importing `openai` at all, so Tasks 4–8's dev-verification tests run with zero network and zero
SDK coupling to internal SDK types. The tester's later wire-stub integration tests exercise the
real SDK's actual chunk shape end-to-end; these fakes exist only to unit-test this module's own
accumulation/translation logic in isolation.

```python
"""Shared fake-SDK fixtures for provider_openai_compatible dev-verification tests.

These fakes are a minimal structural stand-in for the ``openai`` SDK's streamed chunk
and usage shapes — enough to drive this module's own accumulation, TTFT, and
translation logic without a network call or a real SDK object. They are NOT a
substitute for the provider wire stub (``tests/integration/provider_stub/``) the
tester builds for the acceptance-criteria-proving integration tests.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class FakeSdkDelta:
    content: str | None = None
    role: str | None = None


@dataclass
class FakeSdkChoice:
    delta: FakeSdkDelta


@dataclass
class FakeSdkUsage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class FakeSdkChunk:
    choices: list[FakeSdkChoice]
    usage: FakeSdkUsage | None = None


@dataclass
class FakeSdkStream:
    """A hand-built stand-in for the ``openai`` SDK's streaming response object.

    Iterating yields the programmed chunks in order; ``close()`` records that it
    was called (for cancellation/deadline dev-verification tests) and is
    idempotent, matching the real SDK stream's context-manager close semantics.
    """

    chunks: list[FakeSdkChunk]
    closed: bool = field(default=False, init=False)
    _index: int = field(default=0, init=False)

    def __iter__(self) -> Iterator[FakeSdkChunk]:
        return self

    def __next__(self) -> FakeSdkChunk:
        if self._index >= len(self.chunks):
            raise StopIteration
        chunk = self.chunks[self._index]
        self._index += 1
        return chunk

    def close(self) -> None:
        self.closed = True
```

- [ ] **Step 4: Update the module facade `__init__.py`**

Replace the current placeholder body of
`src/ollama_llm_bench/backend/provider_openai_compatible/__init__.py`:

```python
"""OpenAI-compatible (Ollama / LM Studio / llama.cpp / OpenAI / Azure)."""
```

With the full facade (the `make_openai_client` re-export target does not exist until
Task 9 — this step only establishes the docstring and `__all__` scaffold; Step is
revisited in Task 9's Step where the re-export line is added):

```python
"""OpenAI-compatible LLM client adapter (Ollama, LM Studio, llama.cpp, OpenAI, Azure).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§10 (LLM Client) and ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md``. Implements the ``LLMClient`` Protocol declared in
``backend.provider_registry`` for ``ProviderType.OPENAI_COMPATIBLE``.
"""

__all__: list[str] = []
```

(`__all__` stays empty until Task 9 adds `make_openai_client` — an empty `__all__` on a
module with no public symbols yet is valid and keeps this scaffolding step self-contained
and independently committable.)

- [ ] **Step 5: Run the test collector to confirm the new package is discovered**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests --collect-only -q`
Expected: `no tests ran` with no collection errors (conftest.py has no test functions of
its own).

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/__init__.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/_internal/__init__.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/__init__.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/conftest.py
git commit -m "STORY-018: scaffold provider_openai_compatible module and test fixtures"
```

______________________________________________________________________

## Task 4: Exception translation (`_internal/exception_translation.py`)

Implements AC-5's table plus AC-7/AC-8's "raises a concrete `ProviderError`-marked leaf"
requirement. This is the single most important boundary duty in the story
(`02_LLM_CLIENT_PROTOCOL.md` §6.10) — get the SDK-exception → taxonomy-leaf mapping right
here and every other call site (`chat`, `embed`, `list_models`, `probe_health`,
`test_inference`) reuses it.

**Design decision — the catch-all default leaf.** `ProviderError` (`backend.errors`) is a
marker **mixin** with no `__init__` and no `Exception`/`BaseException` base — it is not
directly instantiable (confirmed by reading
`backend/errors/_internal/hierarchy.py:108-114`). The concrete leaf catalogue that mixes
it in is: `HttpTimeoutError`, `HttpConnectionError`, `ProviderRateLimitedError`,
`ProviderServerError`, `ProviderOverloadedError` (transient); `ProviderBadRequestError`,
`ProviderContentFilterError`, `ProviderQuotaExhaustedError`, `ProviderContextLengthError`
(permanent); `ProviderAuthError`, `ModelNotAvailableError`, `MissingEnvVarError` (user).
For the true catch-all — an `openai` SDK exception type this module did not explicitly
enumerate, or a bare `httpx` transport failure with no recognisable status code — this
plan chooses **`ProviderServerError`** (transient category). Justification: a completely
unrecognised failure mode is far more likely to be a transient server-side condition (a
non-standard 5xx body shape, a proxy error, an SDK version skew on an error class this
code hasn't seen yet) than a request the user could fix by editing something — and
`TransientError` retries are already bounded by the pipeline's retry policy, so choosing
transient here does not risk an unbounded retry loop; choosing a `PermanentError`/
`UserError` default instead would silently swallow a genuinely transient failure into a
non-retried terminal status, which is the worse failure mode of the two options.

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/exception_translation.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_exception_translation.py`

**Interfaces:**

- Consumes: `redact` from `backend.errors`; `ErrorContext` from `backend.errors`.

- Produces:
  `translate_exception(exc: BaseException, *, provider_id: str, model_name: str | None) -> NoReturn`
  — always raises (never returns), used by every other `_internal/` module in this story.

- [ ] **Step 1: Write the failing dev-verification test**

```python
"""Dev-verification tests for exception_translation.py — not AC-proving.

The tester's test_exception_translation.py (integration, wire-stub-backed) is the
authoritative proof of STORY-018-AC-5.
"""

import httpx
import openai
import pytest

from ollama_llm_bench.backend.errors import (
    HttpConnectionError,
    HttpTimeoutError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderRateLimitedError,
    ProviderServerError,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.exception_translation import (
    translate_exception,
)


def _fake_request() -> httpx.Request:
    return httpx.Request("POST", "https://example.invalid/v1/chat/completions")


def _fake_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=_fake_request())


@pytest.mark.parametrize(
    ("sdk_exc", "expected_leaf"),
    [
        (openai.APITimeoutError(request=_fake_request()), HttpTimeoutError),
        (
            openai.APIConnectionError(message="connection refused", request=_fake_request()),
            HttpConnectionError,
        ),
        (
            openai.AuthenticationError(
                "bad key", response=_fake_response(401), body=None
            ),
            ProviderAuthError,
        ),
        (
            openai.NotFoundError(
                "model not found", response=_fake_response(404), body=None
            ),
            ModelNotAvailableError,
        ),
        (
            openai.RateLimitError(
                "rate limited", response=_fake_response(429), body=None
            ),
            ProviderRateLimitedError,
        ),
        (
            openai.InternalServerError(
                "boom", response=_fake_response(500), body=None
            ),
            ProviderServerError,
        ),
        (
            openai.BadRequestError(
                "malformed", response=_fake_response(400), body=None
            ),
            ProviderBadRequestError,
        ),
        (ValueError("an SDK type this module never enumerated"), ProviderServerError),
    ],
)
def test_translate_exception_maps_to_expected_leaf(sdk_exc, expected_leaf) -> None:
    with pytest.raises(expected_leaf):
        translate_exception(sdk_exc, provider_id="p1", model_name="m1")


def test_translate_exception_redacts_the_message() -> None:
    secret = "sk-proj-AbCdEf1234567890AbCdEf1234567890AbCdEf12"
    exc = openai.AuthenticationError(
        f"Invalid API key: {secret}", response=_fake_response(401), body=None
    )
    with pytest.raises(ProviderAuthError) as excinfo:
        translate_exception(exc, provider_id="p1", model_name="m1")
    assert secret not in excinfo.value.message


def test_translate_exception_chains_the_original_cause() -> None:
    exc = openai.AuthenticationError("bad key", response=_fake_response(401), body=None)
    with pytest.raises(ProviderAuthError) as excinfo:
        translate_exception(exc, provider_id="p1", model_name="m1")
    assert excinfo.value.__cause__ is exc
```

- [ ] **Step 2: Run it to verify it fails on import**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_exception_translation.py -v`
Expected: `ModuleNotFoundError: No module named 'ollama_llm_bench.backend.provider_openai_compatible._internal.exception_translation'`

- [ ] **Step 3: Implement `_internal/exception_translation.py`**

```python
"""Translate ``openai`` SDK exceptions into the application error taxonomy.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.10 (Exception translation) and §6.9's
"Exception types to translate" row for ``OPENAI_COMPATIBLE``.

The single boundary duty of this module: no ``openai``/``httpx`` exception type may
escape ``backend.provider_openai_compatible`` past this function. Every leaf raised
here is a concrete member of the ``ProviderError``-marked catalogue in
``backend.errors`` — ``ProviderError`` itself is a marker mixin with no
``__init__`` and is never instantiated directly.
"""

from typing import NoReturn

import httpx
import openai

from ollama_llm_bench.backend.errors import (
    ErrorContext,
    HttpConnectionError,
    HttpTimeoutError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderContentFilterError,
    ProviderContextLengthError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitedError,
    ProviderServerError,
    redact,
)

__all__: list[str] = [
    "translate_exception",
]

_CONTENT_FILTER_MARKERS = ("content_filter", "content management policy")
_CONTEXT_LENGTH_MARKERS = ("context_length_exceeded", "maximum context length")


def translate_exception(
    exc: BaseException, *, provider_id: str, model_name: str | None
) -> NoReturn:
    """Catch an ``openai``/``httpx`` exception and re-raise a taxonomy leaf.

    Args:
        exc: The raw exception caught at the SDK call boundary. Never
            re-raised as-is; always wrapped.
        provider_id: The provider's internal UUID4, for ``ErrorContext``.
        model_name: The model targeted by the failed call, or ``None`` for a
            call with no single target model (e.g. ``list_models``).

    Raises:
        HttpTimeoutError: ``exc`` is ``openai.APITimeoutError`` (or the
            provider's connection-timeout condition).
        HttpConnectionError: ``exc`` is ``openai.APIConnectionError`` (not a
            timeout) or an untyped ``httpx`` transport failure.
        ProviderAuthError: ``exc`` is ``openai.AuthenticationError`` or
            ``openai.PermissionDeniedError`` (401/403).
        ModelNotAvailableError: ``exc`` is ``openai.NotFoundError`` (404).
        ProviderRateLimitedError: ``exc`` is ``openai.RateLimitError`` (429).
        ProviderServerError: ``exc`` is ``openai.InternalServerError`` (5xx),
            or any exception type this function did not explicitly enumerate
            (the defensive catch-all — see this module's design note in the
            implementation plan for why the catch-all default is transient).
        ProviderBadRequestError: ``exc`` is ``openai.BadRequestError`` (400)
            with no content-filter or context-length marker in its message.
        ProviderContentFilterError: ``exc`` is a 400-class error whose
            message names a content-policy refusal.
        ProviderContextLengthError: ``exc`` is a 400-class error whose
            message names a context-window overflow.
        ProviderQuotaExhaustedError: ``exc`` is ``openai.RateLimitError``
            whose message names an exhausted quota rather than a rate limit
            (the SDK does not distinguish these by exception type).
    """
    context = ErrorContext(provider_id=provider_id, model_id_truncated=model_name)
    message = redact(str(exc))

    if isinstance(exc, openai.APITimeoutError):
        raise HttpTimeoutError(message=message, context=context) from exc
    if isinstance(exc, openai.APIConnectionError):
        raise HttpConnectionError(message=message, context=context) from exc
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        raise ProviderAuthError(message=message, context=context) from exc
    if isinstance(exc, openai.NotFoundError):
        raise ModelNotAvailableError(message=message, context=context) from exc
    if isinstance(exc, openai.RateLimitError):
        if "quota" in str(exc).lower():
            raise ProviderQuotaExhaustedError(message=message, context=context) from exc
        raise ProviderRateLimitedError(message=message, context=context) from exc
    if isinstance(exc, openai.InternalServerError):
        raise ProviderServerError(message=message, context=context) from exc
    if isinstance(exc, openai.BadRequestError):
        lowered = str(exc).lower()
        if any(marker in lowered for marker in _CONTENT_FILTER_MARKERS):
            raise ProviderContentFilterError(message=message, context=context) from exc
        if any(marker in lowered for marker in _CONTEXT_LENGTH_MARKERS):
            raise ProviderContextLengthError(message=message, context=context) from exc
        raise ProviderBadRequestError(message=message, context=context) from exc
    if isinstance(exc, httpx.TransportError):
        raise HttpConnectionError(message=message, context=context) from exc
    # Defensive catch-all (LC-06): an openai.APIError subclass or any other SDK
    # exception type this function did not explicitly enumerate. Transient by
    # design — see this module's docstring and the implementation plan's design note.
    raise ProviderServerError(message=message, context=context) from exc
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_exception_translation.py -v`
Expected: all cases `PASS`.

- [ ] **Step 5: Typecheck and lint**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/_internal/exception_translation.py && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/_internal/exception_translation.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_exception_translation.py
git commit -m "STORY-018: implement openai SDK exception translation (AC-5)"
```

______________________________________________________________________

## Task 5: Azure transport selection (`_internal/azure_transport.py`)

Implements AC-10 and the SPEC-114 predicate. Structural validation of "some but not all
three Azure fields set" already happens in
`provider_registry/_internal/client_builder.py::validate_structure` (STORY-017, already
`done`) **before** this module's factory is ever called — this module only decides which
SDK client class to construct, assuming the config already passed that check.

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/azure_transport.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_azure_transport.py`

**Interfaces:**

- Consumes: `ProviderConfig` from `backend.domain`.

- Produces: `is_azure_mode(provider: ProviderConfig) -> bool`;
  `build_sdk_client(provider: ProviderConfig, api_key: str, *, timeout_ms: int) -> openai.OpenAI`
  — used by `client.py` (Task 9) at construction time.

- [ ] **Step 1: Write the failing dev-verification test**

```python
"""Dev-verification tests for azure_transport.py — not AC-proving.

The tester's test_azure_mode.py (integration, wire-stub-backed) is the authoritative
proof of STORY-018-AC-10.
"""

import openai

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.provider_openai_compatible._internal.azure_transport import (
    build_sdk_client,
    is_azure_mode,
)


def _provider(**overrides: object) -> ProviderConfig:
    base = {
        "provider_id": "11111111-1111-1111-1111-111111111111",
        "name": "Test Provider",
        "provider_type": ProviderType.OPENAI_COMPATIBLE,
        "enabled": True,
        "base_url": "http://localhost:11434/v1",
    }
    base.update(overrides)
    return ProviderConfig(**base)  # type: ignore[arg-type]


def test_is_azure_mode_true_when_all_three_fields_set() -> None:
    provider = _provider(
        azure_endpoint_raw="https://example.openai.azure.com",
        azure_deployment_raw="gpt-4o-deploy",
        azure_api_version_raw="2024-10-21",
    )
    assert is_azure_mode(provider) is True


def test_is_azure_mode_false_when_no_azure_fields_set() -> None:
    assert is_azure_mode(_provider()) is False


def test_build_sdk_client_selects_azure_client_in_azure_mode() -> None:
    provider = _provider(
        azure_endpoint_raw="https://example.openai.azure.com",
        azure_deployment_raw="gpt-4o-deploy",
        azure_api_version_raw="2024-10-21",
    )
    client = build_sdk_client(provider, "resolved-key", timeout_ms=5000)
    assert isinstance(client, openai.AzureOpenAI)


def test_build_sdk_client_selects_plain_client_outside_azure_mode() -> None:
    client = build_sdk_client(_provider(), "resolved-key", timeout_ms=5000)
    assert isinstance(client, openai.OpenAI)
    assert not isinstance(client, openai.AzureOpenAI)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_azure_transport.py -v`
Expected: `ModuleNotFoundError` for `azure_transport`.

- [ ] **Step 3: Implement `_internal/azure_transport.py`**

```python
"""Select and construct the OpenAI-compatible or Azure SDK transport (SPEC-114).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.9 ("Azure selection (SPEC-114)").

Structural validation of the Azure field set (all-three-or-none) already runs in
``backend.provider_registry._internal.client_builder.validate_structure`` before this
module's factory is ever called — this module assumes that check already passed.
"""

import openai

from ollama_llm_bench.backend.domain import ProviderConfig

__all__: list[str] = [
    "build_sdk_client",
    "is_azure_mode",
]

_CONNECT_TIMEOUT_S = 5.0


def is_azure_mode(provider: ProviderConfig) -> bool:
    """Return whether ``provider`` is configured for the Azure transport.

    Args:
        provider: The provider configuration to inspect.

    Returns:
        ``True`` iff all three ``azure_endpoint_raw``, ``azure_deployment_raw``,
        and ``azure_api_version_raw`` are non-empty.
    """
    return bool(
        provider.azure_endpoint_raw
        and provider.azure_deployment_raw
        and provider.azure_api_version_raw
    )


def build_sdk_client(
    provider: ProviderConfig, api_key: str, *, timeout_ms: int
) -> openai.OpenAI:
    """Construct the ``openai`` SDK client for ``provider`` (§6.9).

    Selects ``openai.AzureOpenAI`` when ``is_azure_mode(provider)``, else plain
    ``openai.OpenAI`` against ``provider.base_url``. The SDK's own retry loop is
    disabled (``max_retries=0``) — this application's retry policy lives in the
    benchmark pipeline, not the client (§1). A finite per-call transport timeout
    is always set (SPEC-015); ``timeout_ms`` here is a construction-time default
    that individual calls override per-request via the SDK's per-call
    ``timeout=`` argument.

    Args:
        provider: The provider configuration; must already have passed
            ``client_builder.validate_structure``.
        api_key: The already-resolved secret value (never the env-var name).
        timeout_ms: The default transport timeout in milliseconds, used only
            when a call site does not override it per-request.

    Returns:
        A constructed, unopened SDK client — no network call happens here.
    """
    timeout = openai.Timeout(timeout_ms / 1000, connect=_CONNECT_TIMEOUT_S)
    if is_azure_mode(provider):
        return openai.AzureOpenAI(
            azure_endpoint=provider.azure_endpoint_raw,
            azure_deployment=provider.azure_deployment_raw,
            api_version=provider.azure_api_version_raw,
            api_key=api_key or "placeholder",
            timeout=timeout,
            max_retries=0,
        )
    return openai.OpenAI(
        base_url=provider.base_url,
        api_key=api_key or "placeholder",
        timeout=timeout,
        max_retries=0,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_azure_transport.py -v`
Expected: all 4 cases `PASS`.

- [ ] **Step 5: Typecheck and lint**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/_internal/azure_transport.py && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/_internal/azure_transport.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_azure_transport.py
git commit -m "STORY-018: implement Azure vs plain OpenAI-compatible transport selection (AC-10)"
```

______________________________________________________________________

## Task 6: The streaming/TTFT/cancellation algorithm (`_internal/chat_stream_impl.py`)

Implements AC-1, AC-2, AC-3, AC-4, and AC-6 — the core of §6.2–§6.6 of the LLM Client
Protocol doc. This is the largest and most intricate task in the story.

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/chat_stream_impl.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_chat_stream_impl.py`

**Interfaces:**

- Consumes: `translate_exception` (Task 4); `ChatRequest`/`ChatResponse`/`ChatChunk`/
  `ChatMessage` from `backend.domain`; `CancellationToken` from `backend.concurrency`;
  `Clock` from `backend.infra`; `ChatStream` Protocol from `backend.provider_registry`.

- Produces: `class _OpenAIChatStream` (implements the `ChatStream` Protocol structurally:
  `__iter__`, `__next__`, `trailing_response()`); the factory function
  `open_chat_stream(sdk_client: openai.OpenAI, request: ChatRequest, *, token: CancellationToken, clock: Clock, provider_id: str) -> ChatStream`
  — this is what `client.py::OpenAICompatibleClient.chat_stream` delegates to directly,
  and what `.chat()` consumes internally per DD-51.

- [ ] **Step 1: Write the failing dev-verification test**

```python
"""Dev-verification tests for chat_stream_impl.py — not AC-proving.

The tester's test_chat_stream.py / test_deadline.py / test_cancellation.py
(the latter is unit-tier per the story's own Test Plan) are the authoritative proof
of STORY-018-AC-1/2/3/4/6. This file exercises the same algorithm against the
hand-built FakeSdkStream from conftest.py instead of the real openai SDK, to give
the coder a fast, network-free TDD loop.
"""

from unittest.mock import MagicMock

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import CancelReason, ChatMessage, ChatRequest, ChatRole
from ollama_llm_bench.backend.errors import HttpTimeoutError, TaskCancelledError
from ollama_llm_bench.backend.provider_openai_compatible._internal.chat_stream_impl import (
    open_chat_stream,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import (
    FakeSdkChoice,
    FakeSdkChunk,
    FakeSdkDelta,
    FakeSdkStream,
    FakeSdkUsage,
)


def _request(timeout_ms: int = 30_000) -> ChatRequest:
    return ChatRequest(
        model="qwen2.5:7b",
        messages=(ChatMessage(role=ChatRole.USER, content="hi"),),
        timeout_ms=timeout_ms,
    )


def _clock_with(monotonic_sequence: list[int]) -> MagicMock:
    clock = MagicMock()
    clock.monotonic_ms.side_effect = monotonic_sequence
    return clock


def test_three_content_chunks_then_usage_concatenates_and_captures_ttft() -> None:
    # Arrange — AC-1
    stream = FakeSdkStream(
        chunks=[
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(content="Hel"))]),
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(content="lo "))]),
            FakeSdkChunk(
                choices=[FakeSdkChoice(delta=FakeSdkDelta(content="world"))],
                usage=FakeSdkUsage(prompt_tokens=10, completion_tokens=3),
            ),
        ]
    )
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.return_value = stream
    clock = _clock_with([0, 380, 380, 380, 11240])
    token = CancellationToken(clock=clock)

    # Act
    chat_stream = open_chat_stream(
        sdk_client, _request(), token=token, clock=clock, provider_id="p1"
    )
    chunks = list(chat_stream)
    response = chat_stream.trailing_response()

    # Assert
    assert "".join(c.content for c in chunks) == "Hello world"
    assert response.text == "Hello world"
    assert response.ttft_ms == 380
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 3


def test_role_only_leading_chunk_does_not_trip_ttft() -> None:
    # Arrange — AC-2
    stream = FakeSdkStream(
        chunks=[
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(role="assistant"))]),
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(content="ok"))]),
        ]
    )
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.return_value = stream
    clock = _clock_with([0, 50, 50, 200])
    token = CancellationToken(clock=clock)

    # Act
    chat_stream = open_chat_stream(
        sdk_client, _request(), token=token, clock=clock, provider_id="p1"
    )
    list(chat_stream)
    response = chat_stream.trailing_response()

    # Assert — ttft measured from the SECOND chunk (first content), not the role-only first
    assert response.ttft_ms == 50


def test_empty_stream_reports_soft_error_without_raising() -> None:
    # Arrange — AC-3
    stream = FakeSdkStream(chunks=[])
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.return_value = stream
    clock = _clock_with([0, 5])
    token = CancellationToken(clock=clock)

    # Act
    chat_stream = open_chat_stream(
        sdk_client, _request(), token=token, clock=clock, provider_id="p1"
    )
    list(chat_stream)
    response = chat_stream.trailing_response()

    # Assert
    assert response.text == ""
    assert response.ttft_ms is None
    assert response.error is not None


def test_stall_past_deadline_raises_timeout_and_closes_stream() -> None:
    # Arrange — AC-4: the fake SDK client raises the SDK's own timeout type directly,
    # simulating the per-read socket timeout firing inside provider_sdk.open_stream().
    import openai

    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = openai.APITimeoutError(
        request=MagicMock()
    )
    clock = _clock_with([0])
    token = CancellationToken(clock=clock)

    # Act / Assert
    with pytest.raises(HttpTimeoutError):
        open_chat_stream(sdk_client, _request(), token=token, clock=clock, provider_id="p1")


def test_hard_cancel_after_second_chunk_raises_task_cancelled_and_closes_stream() -> None:
    # Arrange — AC-6
    stream = FakeSdkStream(
        chunks=[
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(content="a"))]),
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(content="b"))]),
            FakeSdkChunk(choices=[FakeSdkChoice(delta=FakeSdkDelta(content="c"))]),
        ]
    )
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.return_value = stream
    clock = _clock_with([0, 10, 10, 20])
    token = CancellationToken(clock=clock)

    # Act
    chat_stream = open_chat_stream(
        sdk_client, _request(), token=token, clock=clock, provider_id="p1"
    )
    iterator = iter(chat_stream)
    next(iterator)  # consume chunk 1 ("a")
    next(iterator)  # consume chunk 2 ("b")
    token.cancel(reason=CancelReason.USER_STOP, hard=True)

    # Assert
    with pytest.raises(TaskCancelledError):
        next(iterator)
    assert stream.closed is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_chat_stream_impl.py -v`
Expected: `ModuleNotFoundError` for `chat_stream_impl`.

- [ ] **Step 3: Implement `_internal/chat_stream_impl.py`**

```python
"""The chat_stream algorithm — streaming consumption, TTFT, usage, cancellation.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.2 (transport streaming and TTFT), §6.3 (the ``chat``
algorithm), §6.4 (the ``chat_stream`` surface), §6.5 (token-usage capture), §6.6
(mid-stream cancellation).
"""

from collections.abc import Iterator

import openai

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import ChatChunk, ChatRequest, ChatResponse
from ollama_llm_bench.backend.errors import TaskCancelledError, redact
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_openai_compatible._internal.exception_translation import (
    translate_exception,
)
from ollama_llm_bench.backend.provider_registry import ChatStream

__all__: list[str] = [
    "open_chat_stream",
]

_EMPTY_RESPONSE_ERROR = "empty_response"


class _Usage:
    __slots__ = ("completion_tokens", "prompt_tokens")

    def __init__(self, *, prompt_tokens: int | None, completion_tokens: int | None) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _OpenAIChatStream:
    """Structurally satisfies the ``ChatStream`` Protocol (see ``provider_registry``).

    Iterating drives the underlying SDK stream one chunk at a time, appending
    content to a local accumulator and updating TTFT/usage as it goes;
    ``trailing_response()`` assembles the final ``ChatResponse`` once
    iteration is exhausted. Holds no state shared across calls — a fresh
    instance is constructed per ``open_chat_stream`` call.
    """

    def __init__(
        self,
        sdk_stream: object,
        *,
        token: CancellationToken,
        clock: Clock,
        provider_id: str,
        model_name: str,
        t0: int,
    ) -> None:
        self._sdk_stream = sdk_stream
        self._token = token
        self._clock = clock
        self._provider_id = provider_id
        self._model_name = model_name
        self._t0 = t0
        self._accumulator = ""
        self._ttft_ms: int | None = None
        self._usage: _Usage | None = None
        self._closed = False
        self._exhausted = False
        self._hook_registered = False
        self._register_hook()

    def _register_hook(self) -> None:
        self._token.add_hard_cancel_hook(self._close_quietly)
        self._hook_registered = True

    def _close_quietly(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._sdk_stream, "close", None)
        if close is not None:
            close()

    def __iter__(self) -> Iterator[ChatChunk]:
        return self

    def __next__(self) -> ChatChunk:
        if self._token.is_hard_cancelled:
            self._finish(cancelled=True)
            raise TaskCancelledError(
                message=redact(self._token.snapshot()[1].value if self._token.snapshot()[1] else ""),
                context=None,
            )
        try:
            raw_chunk = next(iter(self._sdk_stream))
        except StopIteration:
            self._finish(cancelled=False)
            raise
        except BaseException as exc:
            self._finish(cancelled=False)
            translate_exception(exc, provider_id=self._provider_id, model_name=self._model_name)
        content = _extract_content(raw_chunk)
        if content and self._ttft_ms is None:
            self._ttft_ms = self._clock.monotonic_ms() - self._t0
        self._accumulator += content
        delta_usage = _extract_usage(raw_chunk)
        if delta_usage is not None:
            self._usage = delta_usage
        return ChatChunk(content=content)

    def _finish(self, *, cancelled: bool) -> None:
        if not self._exhausted:
            self._exhausted = True
            self._token.remove_hard_cancel_hook(self._close_quietly)
        if cancelled:
            self._close_quietly()

    def trailing_response(self) -> ChatResponse:
        """Return the completed response once the stream is exhausted."""
        total_time_ms = self._clock.monotonic_ms() - self._t0
        error = _EMPTY_RESPONSE_ERROR if not self._accumulator else None
        return ChatResponse(
            text=self._accumulator,
            total_time_ms=total_time_ms,
            streamed=True,
            ttft_ms=self._ttft_ms,
            prompt_tokens=self._usage.prompt_tokens if self._usage else None,
            completion_tokens=self._usage.completion_tokens if self._usage else None,
            error=error,
        )


def open_chat_stream(
    sdk_client: openai.OpenAI,
    request: ChatRequest,
    *,
    token: CancellationToken,
    clock: Clock,
    provider_id: str,
) -> ChatStream:
    """Open a streaming chat call and return its ``ChatStream`` (§6.2–§6.6).

    Args:
        sdk_client: The constructed ``openai`` SDK client (plain or Azure).
        request: The fully-formed chat request.
        token: The run's ``CancellationToken``; a hard-cancel hook is
            registered around the in-flight stream for its duration.
        clock: The injected time source for ``t0``/TTFT/total-time
            measurement.
        provider_id: The provider's internal UUID4, for exception context.

    Returns:
        A ``ChatStream`` yielding content chunks, then exposing
        ``trailing_response()``.

    Raises:
        HttpTimeoutError: The deadline expired before the stream opened or
            during consumption.
        ProviderError: The provider rejected the request (a concrete leaf
            from ``exception_translation.translate_exception``).
    """
    t0 = clock.monotonic_ms()
    timeout = openai.Timeout(request.timeout_ms / 1000, connect=5.0)
    messages = [{"role": m.role.value, "content": m.content} for m in request.messages]
    try:
        sdk_stream = sdk_client.chat.completions.create(
            model=request.model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=request.max_output_tokens,
            timeout=timeout,
        )
    except BaseException as exc:
        translate_exception(exc, provider_id=provider_id, model_name=request.model)
    return _OpenAIChatStream(
        sdk_stream,
        token=token,
        clock=clock,
        provider_id=provider_id,
        model_name=request.model,
        t0=t0,
    )


def _extract_content(raw_chunk: object) -> str:
    choices = getattr(raw_chunk, "choices", None)
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None) if delta is not None else None
    return content or ""


def _extract_usage(raw_chunk: object) -> _Usage | None:
    usage = getattr(raw_chunk, "usage", None)
    if usage is None:
        return None
    return _Usage(
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
    )
```

**Note for the coder session:** the `test_stall_past_deadline_raises_timeout_and_closes_stream`
dev-verification case above simulates the deadline firing as `sdk_client.chat.completions.create`
itself raising `openai.APITimeoutError` — this is a legitimate simplification for a
network-free unit test (the SDK's own per-read timeout is what would raise this in
production, whether at stream-open or mid-consumption; both paths route through the same
`except BaseException` → `translate_exception` call). The tester's wire-stub-backed
`test_deadline.py` proves the true mid-stream-stall variant end-to-end with a real slow
HTTP response.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_chat_stream_impl.py -v`
Expected: all 5 cases `PASS`.

- [ ] **Step 5: Typecheck and lint**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/_internal/chat_stream_impl.py && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean. If `mypy` flags the `getattr`-based duck-typing in
`_extract_content`/`_extract_usage` against the SDK's actual typed chunk shape, add a
narrow, justified `# type: ignore[union-attr]` there rather than importing the SDK's
internal chunk type name (which varies across SDK minor versions) — note the specific
`mypy` error code seen before adding the suppression.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/_internal/chat_stream_impl.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_chat_stream_impl.py
git commit -m "STORY-018: implement chat_stream algorithm — TTFT, usage, cancellation (AC-1,2,3,4,6)"
```

______________________________________________________________________

## Task 7: Health probe and model discovery (`_internal/discovery.py`)

Implements AC-7.

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/discovery.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_discovery.py`

**Interfaces:**

- Consumes: `translate_exception` (Task 4); `ProviderHealth`/`ModelName` from
  `backend.domain`; `Clock` from `backend.infra`.

- Produces:
  `probe_health(sdk_client: openai.OpenAI, *, clock: Clock, provider_id: str) -> ProviderHealth`;
  `list_models(sdk_client: openai.OpenAI, *, provider_id: str) -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing dev-verification test**

```python
"""Dev-verification tests for discovery.py — not AC-proving.

The tester's test_probe_health.py (integration, wire-stub-backed) is the
authoritative proof of STORY-018-AC-7.
"""

from unittest.mock import MagicMock

import openai
import pytest

from ollama_llm_bench.backend.errors import ProviderServerError
from ollama_llm_bench.backend.provider_openai_compatible._internal.discovery import (
    list_models,
    probe_health,
)


def test_probe_health_unreachable_returns_unhealthy_without_raising() -> None:
    sdk_client = MagicMock()
    sdk_client.models.list.side_effect = openai.APIConnectionError(
        message="connection refused", request=MagicMock()
    )
    clock = MagicMock()
    clock.monotonic_ms.side_effect = [0, 5]

    health = probe_health(sdk_client, clock=clock, provider_id="p1")

    assert health.reachable is False
    assert health.discovery_supported is True
    assert health.model_count is None
    assert health.last_error is not None


def test_probe_health_reachable_zero_models_is_healthy() -> None:
    sdk_client = MagicMock()
    sdk_client.models.list.return_value = MagicMock(data=[])
    clock = MagicMock()
    clock.monotonic_ms.side_effect = [0, 5]

    health = probe_health(sdk_client, clock=clock, provider_id="p1")

    assert health.reachable is True
    assert health.model_count == 0
    assert health.last_error is None


def test_list_models_raises_on_listing_failure() -> None:
    sdk_client = MagicMock()
    sdk_client.models.list.side_effect = openai.InternalServerError(
        "boom", response=MagicMock(status_code=500), body=None
    )

    with pytest.raises(ProviderServerError):
        list_models(sdk_client, provider_id="p1")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_discovery.py -v`
Expected: `ModuleNotFoundError` for `discovery`.

- [ ] **Step 3: Implement `_internal/discovery.py`**

```python
"""Reachability probe and model discovery (§6.8.1, §6.9.1).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.8.1 (``probe_health``) and §6.9.1 (the per-provider
discovery-support matrix — ``OPENAI_COMPATIBLE`` is always ``discovery_supported=True``
via ``GET /v1/models``).
"""

import openai

from ollama_llm_bench.backend.domain import ProviderHealth
from ollama_llm_bench.backend.errors import redact
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_openai_compatible._internal.exception_translation import (
    translate_exception,
)

__all__: list[str] = [
    "list_models",
    "probe_health",
]

_PROBE_TIMEOUT_S = 5.0


def probe_health(sdk_client: openai.OpenAI, *, clock: Clock, provider_id: str) -> ProviderHealth:
    """Confirm reachability, then discover models via ``GET /v1/models`` (§6.8.1).

    Never raises. Every failure mode — unreachable host, or a reachable host
    whose listing call itself fails — is captured into the returned
    ``ProviderHealth``.

    Args:
        sdk_client: The constructed ``openai`` SDK client.
        clock: The injected time source for ``last_probe_ms``.
        provider_id: The provider's internal UUID4.

    Returns:
        The probe outcome; ``reachable=False`` only when the listing call
        itself could not be reached at all (DNS/connect/auth-handshake
        failure), never merely because it returned zero models.
    """
    t0 = clock.monotonic_ms()
    try:
        response = sdk_client.models.list(timeout=_PROBE_TIMEOUT_S)
    except openai.APIConnectionError as exc:
        return ProviderHealth(
            provider_id=provider_id,
            reachable=False,
            discovery_supported=True,
            model_count=None,
            last_probe_ms=clock.monotonic_ms() - t0,
            last_error=redact(str(exc)),
            probed_at=clock.monotonic_ms(),
        )
    except openai.APIError as exc:
        return ProviderHealth(
            provider_id=provider_id,
            reachable=True,
            discovery_supported=True,
            model_count=None,
            last_probe_ms=clock.monotonic_ms() - t0,
            last_error=redact(str(exc)),
            probed_at=clock.monotonic_ms(),
        )
    return ProviderHealth(
        provider_id=provider_id,
        reachable=True,
        discovery_supported=True,
        model_count=len(response.data),
        last_probe_ms=clock.monotonic_ms() - t0,
        last_error=None,
        probed_at=clock.monotonic_ms(),
    )


def list_models(sdk_client: openai.OpenAI, *, provider_id: str) -> tuple[str, ...]:
    """Return the provider's advertised model catalog.

    Args:
        sdk_client: The constructed ``openai`` SDK client.
        provider_id: The provider's internal UUID4, for exception context.

    Returns:
        The advertised model names; may be empty for a reachable provider
        that exposes none.

    Raises:
        ProviderError: The listing call itself failed (a concrete leaf from
            ``exception_translation.translate_exception`` — distinct from an
            empty, non-raising catalog).
    """
    try:
        response = sdk_client.models.list(timeout=_PROBE_TIMEOUT_S)
    except BaseException as exc:
        translate_exception(exc, provider_id=provider_id, model_name=None)
    return tuple(model.id for model in response.data)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_discovery.py -v`
Expected: all 3 cases `PASS`.

- [ ] **Step 5: Typecheck and lint**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/_internal/discovery.py && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/_internal/discovery.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_discovery.py
git commit -m "STORY-018: implement probe_health and list_models (AC-7)"
```

______________________________________________________________________

## Task 8: Inference-test outcome classification (`_internal/inference_test.py`)

Implements AC-9 (including the architect's `REACHABILITY_FAILED` amendment).

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/inference_test.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_inference_test.py`

**Interfaces:**

- Consumes: `InferenceActivityStore`/`GateLease`/`InferenceActivity`/
  `InferenceActivityContext`/`InferenceTestOutcome`/`InferenceTestResult` from
  `backend.domain`/`backend.stores.inference_activity`; `Clock` from `backend.infra`;
  `CancellationToken` from `backend.concurrency`; the errors
  `HttpTimeoutError`/`ProviderAuthError`/`ModelNotAvailableError` from `backend.errors`
  (to classify a caught exception, not to re-raise it).

- Produces:
  `run_test_inference(chat_fn, *, model_name, provider_id, gate, clock, token) -> InferenceTestResult`
  where `chat_fn: Callable[[], ChatResponse]` is a zero-argument thunk `client.py`
  supplies (a closure over `self.chat(request, token=token)`) — this keeps this module
  fully decoupled from the SDK/HTTP layer, so it needs no fake SDK objects at all, only a
  fake `chat_fn` and a fake gate.

- [ ] **Step 1: Write the failing dev-verification test**

```python
"""Dev-verification tests for inference_test.py — not AC-proving.

The tester's test_inference_test.py (unit, wire-stub-backed for the call itself) is
the authoritative proof of STORY-018-AC-9.
"""

from unittest.mock import MagicMock

import pytest

from ollama_llm_bench.backend.domain import (
    ChatResponse,
    InferenceActivity,
    InferenceTestOutcome,
)
from ollama_llm_bench.backend.errors import (
    HttpTimeoutError,
    ModelNotAvailableError,
    ProviderAuthError,
    ProviderServerError,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.inference_test import (
    run_test_inference,
)
from ollama_llm_bench.backend.stores.inference_activity.testing import (
    FakeInferenceActivityStore,
)


def _clock() -> MagicMock:
    clock = MagicMock()
    clock.monotonic_ms.side_effect = list(range(0, 100_000, 10))
    clock.now_utc.return_value = "2026-07-11T00:00:00Z"
    return clock


def test_gate_busy_returns_gate_busy_outcome_without_calling() -> None:
    clock = _clock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=MagicMock())
    held_context = MagicMock(activity=InferenceActivity.BENCHMARK_RUN)
    gate.try_acquire(InferenceActivity.BENCHMARK_RUN, held_context)
    chat_fn = MagicMock()

    result = run_test_inference(
        chat_fn, model_name="m1", provider_id="p1", gate=gate, clock=clock
    )

    assert result.outcome == InferenceTestOutcome.GATE_BUSY
    assert result.latency_ms is None
    chat_fn.assert_not_called()


def test_successful_call_returns_success_and_releases_gate() -> None:
    clock = _clock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=MagicMock())
    chat_fn = MagicMock(
        return_value=ChatResponse(text="ok", total_time_ms=12, error=None)
    )

    result = run_test_inference(
        chat_fn, model_name="m1", provider_id="p1", gate=gate, clock=clock
    )

    assert result.outcome == InferenceTestOutcome.SUCCESS
    assert result.response_excerpt == "ok"
    assert gate.is_busy() is False


def test_timeout_error_maps_to_timeout_outcome() -> None:
    clock = _clock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=MagicMock())
    chat_fn = MagicMock(side_effect=HttpTimeoutError(message="timed out"))

    result = run_test_inference(
        chat_fn, model_name="m1", provider_id="p1", gate=gate, clock=clock
    )

    assert result.outcome == InferenceTestOutcome.TIMEOUT
    assert gate.is_busy() is False


def test_auth_error_maps_to_auth_failed_outcome() -> None:
    clock = _clock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=MagicMock())
    chat_fn = MagicMock(side_effect=ProviderAuthError(message="bad key"))

    result = run_test_inference(
        chat_fn, model_name="m1", provider_id="p1", gate=gate, clock=clock
    )

    assert result.outcome == InferenceTestOutcome.AUTH_FAILED


def test_model_not_available_maps_to_model_not_found_outcome() -> None:
    clock = _clock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=MagicMock())
    chat_fn = MagicMock(side_effect=ModelNotAvailableError(message="no such model"))

    result = run_test_inference(
        chat_fn, model_name="m1", provider_id="p1", gate=gate, clock=clock
    )

    assert result.outcome == InferenceTestOutcome.MODEL_NOT_FOUND


@pytest.mark.parametrize(
    "exc",
    [
        ProviderServerError(message="connection refused"),
    ],
)
def test_unexpected_internal_error_never_propagates(exc: BaseException) -> None:
    clock = _clock()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=MagicMock())
    chat_fn = MagicMock(side_effect=exc)

    result = run_test_inference(
        chat_fn, model_name="m1", provider_id="p1", gate=gate, clock=clock
    )

    assert result.outcome in (
        InferenceTestOutcome.PROVIDER_ERROR,
        InferenceTestOutcome.REACHABILITY_FAILED,
    )
    assert gate.is_busy() is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_inference_test.py -v`
Expected: `ModuleNotFoundError` for `inference_test`.

- [ ] **Step 3: Implement `_internal/inference_test.py`**

```python
"""The test_inference outcome classification and gate lifecycle (§6.8.2).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md`` §6.8.2. Per STORY-018's own "In scope" section, this
implementation calls the client's own ``chat()`` directly rather than wrapping it in
``emit_progress_during(...)`` — that shared pipeline helper (``04_EVALUATION_PIPELINE.md``
§6.9) does not exist yet (it belongs to a later, not-yet-built ``backend.benchmark_pipeline``
story) and STORY-018-AC-9's own test plan excludes LC-24 (the live-progress-event test
case) for exactly this reason. Live progress emission for the Provider Edit inference-test
panel is out of scope for this story.
"""

from collections.abc import Callable

from ollama_llm_bench.backend.domain import (
    InferenceActivity,
    InferenceActivityContext,
    InferenceTestOutcome,
    InferenceTestResult,
)
from ollama_llm_bench.backend.domain import ChatResponse as ChatResponseType
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpTimeoutError,
    ModelNotAvailableError,
    ProviderAuthError,
    TaskCancelledError,
    redact,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = [
    "run_test_inference",
]

_RESPONSE_EXCERPT_LEN = 200
_GATE_BUSY_MESSAGE = "An inference activity is already in flight."


def run_test_inference(
    chat_fn: Callable[[], ChatResponseType],
    *,
    model_name: str,
    provider_id: str,
    gate: InferenceActivityStore,
    clock: Clock,
) -> InferenceTestResult:
    """Run one gated end-to-end inference test and classify its outcome (§6.8.2).

    Never raises — every failure mode from ``chat_fn`` is caught and mapped
    to an ``InferenceTestOutcome``. Acquires the ``PROVIDER_TEST`` gate
    before calling ``chat_fn`` and always releases it in ``finally`` (except
    on the ``GATE_BUSY`` early exit, which never acquired anything to
    release).

    Args:
        chat_fn: A zero-argument thunk issuing exactly one chat call (a
            closure over ``self.chat(request, token=...)`` supplied by
            ``client.py``). Raising is expected and handled here; returning
            is the success path.
        model_name: The model targeted by the canned-prompt call.
        provider_id: The provider's internal UUID4.
        gate: The application-wide single-inference gate.
        clock: The injected time source for ``tested_at``/``latency_ms``.

    Returns:
        The classified ``InferenceTestResult``. Never raises.
    """
    t0 = clock.monotonic_ms()
    lease = gate.try_acquire(
        InferenceActivity.PROVIDER_TEST,
        InferenceActivityContext(
            activity=InferenceActivity.PROVIDER_TEST,
            started_at=t0,
            provider_id=provider_id,
            model_name=model_name,
        ),
    )
    if lease is None:
        return InferenceTestResult(
            outcome=InferenceTestOutcome.GATE_BUSY,
            provider_id=provider_id,
            model_name=model_name,
            latency_ms=None,
            response_excerpt=None,
            last_error=_GATE_BUSY_MESSAGE,
            tested_at=clock.monotonic_ms(),
        )
    try:
        response = chat_fn()
    except BaseException as exc:  # noqa: BLE001  # test_inference never raises (§6.8.2 rule 8)
        return _result_for_exception(
            exc,
            model_name=model_name,
            provider_id=provider_id,
            latency_ms=clock.monotonic_ms() - t0,
            clock=clock,
        )
    finally:
        gate.release(lease)
    return _result_for_response(
        response,
        model_name=model_name,
        provider_id=provider_id,
        latency_ms=clock.monotonic_ms() - t0,
        clock=clock,
    )


def _result_for_response(
    response: ChatResponseType,
    *,
    model_name: str,
    provider_id: str,
    latency_ms: int,
    clock: Clock,
) -> InferenceTestResult:
    if response.text and response.error is None:
        return InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id=provider_id,
            model_name=model_name,
            latency_ms=latency_ms,
            response_excerpt=response.text[:_RESPONSE_EXCERPT_LEN],
            last_error=None,
            tested_at=clock.monotonic_ms(),
        )
    return InferenceTestResult(
        outcome=InferenceTestOutcome.PROVIDER_ERROR,
        provider_id=provider_id,
        model_name=model_name,
        latency_ms=latency_ms,
        response_excerpt=None,
        last_error=redact(response.error or "empty response"),
        tested_at=clock.monotonic_ms(),
    )


def _result_for_exception(
    exc: BaseException,
    *,
    model_name: str,
    provider_id: str,
    latency_ms: int,
    clock: Clock,
) -> InferenceTestResult:
    outcome = _classify_exception(exc)
    message = exc.message if isinstance(exc, AppError) else str(exc)
    return InferenceTestResult(
        outcome=outcome,
        provider_id=provider_id,
        model_name=model_name,
        latency_ms=latency_ms,
        response_excerpt=None,
        last_error=redact(message),
        tested_at=clock.monotonic_ms(),
    )


def _classify_exception(exc: BaseException) -> InferenceTestOutcome:
    if isinstance(exc, TaskCancelledError):
        return InferenceTestOutcome.TIMEOUT
    if isinstance(exc, HttpTimeoutError):
        return InferenceTestOutcome.TIMEOUT
    if isinstance(exc, ProviderAuthError):
        return InferenceTestOutcome.AUTH_FAILED
    if isinstance(exc, ModelNotAvailableError):
        return InferenceTestOutcome.MODEL_NOT_FOUND
    from ollama_llm_bench.backend.errors import HttpConnectionError

    if isinstance(exc, HttpConnectionError):
        return InferenceTestOutcome.REACHABILITY_FAILED
    return InferenceTestOutcome.PROVIDER_ERROR
```

**Note for the coder session:** move the `HttpConnectionError` import to the module's
top-level import block (it was written as a late/local import above only to keep this
plan's diff readable inline — a late import inside a function body is banned by
`.claude/rules/coding-style.md`). The final file must import it alongside
`HttpTimeoutError`/`ModelNotAvailableError`/`ProviderAuthError` at the top.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_inference_test.py -v`
Expected: all 6 cases `PASS`.

- [ ] **Step 5: Typecheck and lint**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/_internal/inference_test.py && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean (the `# noqa: BLE001` above is the one sanctioned blanket-except in
this module — `test_inference` is explicitly required to never raise per §6.8.2 rule 8,
which is exactly the kind of allowlisted exception `.claude/rules/error-handling-standard.md`
permits for a failure-as-data boundary; keep the inline justification comment).

- [ ] **Step 6: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/_internal/inference_test.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/tests/test_dev_inference_test.py
git commit -m "STORY-018: implement test_inference outcome classification and gate lifecycle (AC-9)"
```

______________________________________________________________________

## Task 9: Assemble `OpenAICompatibleClient` and the `api.py` factory

Implements `embed` (AC-8, using `translate_exception` directly — no separate helper
module needed since it is a single call with no algorithmic complexity beyond
translation) and wires every helper from Tasks 4–8 into the concrete class satisfying
`LLMClient`.

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/_internal/client.py`
- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/api.py`
- Modify: `src/ollama_llm_bench/backend/provider_openai_compatible/__init__.py`

**Interfaces:**

- Consumes: every `_internal/` helper from Tasks 4–8; `LLMClient`/`ChatStream` Protocols
  from `backend.provider_registry`.

- Produces (public, importable from the package root per this project's public-surface
  rule): `make_openai_client(provider: ProviderConfig, api_key: str, *, clock: Clock) -> LLMClient`
  — this is the `ClientBuilder`-shaped factory `compose.py` (a later, not-yet-built
  story) wires into `provider_registry`'s `client_builders` map.

- [ ] **Step 1: Implement `_internal/client.py`**

```python
"""The concrete OPENAI_COMPATIBLE ``LLMClient`` (Ollama/LM Studio/llama.cpp/OpenAI/Azure).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§10 and ``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``.
"""

import openai

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import ChatRequest, ChatResponse, ModelName, ProviderConfig
from ollama_llm_bench.backend.domain import InferenceTestResult
from ollama_llm_bench.backend.errors import ProviderBadRequestError
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_openai_compatible._internal.azure_transport import (
    build_sdk_client,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.chat_stream_impl import (
    open_chat_stream,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.discovery import (
    list_models as list_models_impl,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.discovery import probe_health
from ollama_llm_bench.backend.provider_openai_compatible._internal.exception_translation import (
    translate_exception,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.inference_test import (
    run_test_inference,
)
from ollama_llm_bench.backend.provider_registry import ChatStream
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = [
    "OpenAICompatibleClient",
]

_EMBEDDING_TIMEOUT_S = 20.0
_DEFAULT_TRANSPORT_TIMEOUT_MS = 30_000


class OpenAICompatibleClient:
    """Structurally satisfies ``LLMClient`` for ``ProviderType.OPENAI_COMPATIBLE``.

    Holds no per-call mutable state: the constructed SDK client is
    stateless network-transport configuration, not per-call accumulator
    state — every call builds its own accumulator, timing, and deadline
    (D-R-01, §6.9 threading rule).
    """

    def __init__(
        self,
        *,
        provider: ProviderConfig,
        api_key: str,
        clock: Clock,
        gate: InferenceActivityStore,
    ) -> None:
        self._provider_id = provider.provider_id
        self._clock = clock
        self._gate = gate
        self._sdk_client = build_sdk_client(
            provider, api_key, timeout_ms=_DEFAULT_TRANSPORT_TIMEOUT_MS
        )

    def list_models(self) -> tuple[ModelName, ...]:
        """Return the provider's advertised model catalog."""
        return list_models_impl(self._sdk_client, provider_id=self._provider_id)

    def probe_health(self):  # noqa: ANN201  # return type is ProviderHealth; see note below
        """Check reachability and, when supported, discover models."""
        return probe_health(self._sdk_client, clock=self._clock, provider_id=self._provider_id)

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        """Run one gated, canned-prompt end-to-end chat call against ``model_name``."""
        request = ChatRequest(
            model=model_name,
            messages=(
                {"role": "user", "content": "Reply with the single word: ok"},  # type: ignore[arg-type]
            ),
            timeout_ms=30_000,
        )
        no_op_token = CancellationToken(clock=self._clock)
        return run_test_inference(
            lambda: self.chat(request, token=no_op_token),
            model_name=model_name,
            provider_id=self._provider_id,
            gate=self._gate,
            clock=self._clock,
        )

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        """Consume ``chat_stream`` to completion (DD-51)."""
        stream = self.chat_stream(request, token=token)
        for _ in stream:
            pass
        return stream.trailing_response()

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        """Open a streaming chat call (DD-51; THE execution surface)."""
        return open_chat_stream(
            self._sdk_client,
            request,
            token=token,
            clock=self._clock,
            provider_id=self._provider_id,
        )

    def embed(self, text: str) -> tuple[float, ...]:
        """Return the embedding vector for ``text`` via ``/v1/embeddings``."""
        try:
            response = self._sdk_client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
                timeout=_EMBEDDING_TIMEOUT_S,
            )
        except BaseException as exc:
            translate_exception(exc, provider_id=self._provider_id, model_name=None)
        return tuple(response.data[0].embedding)

    def supports_streaming(self) -> bool:
        """Whether the transport supports token streaming — always ``True`` here."""
        return True

    def supports_reasoning_effort(self) -> bool:
        """Whether the provider accepts a reasoning-effort parameter."""
        return False

    def supports_thinking(self) -> bool:
        """Whether the model emits a reasoning/thinking block."""
        return False

    def close(self) -> None:
        """Best-effort release of the underlying SDK client's transport resources."""
        close = getattr(self._sdk_client, "close", None)
        if close is not None:
            close()
```

**Note for the coder session:** the `probe_health` method's `# noqa: ANN201` above is a
placeholder written only because this plan cannot import `ProviderHealth` twice under two
names without a naming collision in this markdown snippet — in the real file, import
`ProviderHealth` from `backend.domain` alongside the other domain imports and annotate
`def probe_health(self) -> ProviderHealth:` properly; delete the `# noqa` entirely, it is
not needed once the return type is annotated. Likewise, the `embedding-model` name
`"text-embedding-3-small"` hardcoded in `test_inference`'s unused code path is wrong —
re-read `embed`'s signature: it does not take a model name at all in the `LLMClient`
Protocol (the model is resolved from `embedding.selected_model_name`, per
`02_LLM_CLIENT_PROTOCOL.md` §6.7, which is a **settings** concern, not a per-call
parameter). Before writing the final file, re-confirm against
`backend/provider_registry/protocols.py`'s `embed(self, text: str) -> tuple[float, ...]`
signature (no model parameter) and decide, as part of this task, where the embedding
model name for `/v1/embeddings` comes from: the two live options are (a) resolve it once
at `OpenAICompatibleClient.__init__` time from a new constructor parameter the factory
supplies, or (b) read `provider.default_models` / a first embedding-capable model. Check
`06_EMBEDDING_SERVICE.md` §6.6a (cited by `02_LLM_CLIENT_PROTOCOL.md` §6.7) before
deciding — **this is a genuine open sub-question the coder must resolve by reading that
spec file before finalizing `embed`'s implementation; do not guess a hardcoded model
name.**

- [ ] **Step 2: Implement `api.py`**

```python
"""Public factory for the OPENAI_COMPATIBLE ``LLMClient``.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§10; the ``ClientBuilder`` shape declared in ``backend.provider_registry.protocols``.
"""

import icontract

from ollama_llm_bench.backend.domain import ProviderConfig, ProviderType
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.provider_openai_compatible._internal.client import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_registry import LLMClient
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = [
    "make_openai_client",
]


@icontract.require(
    lambda provider: provider.provider_type is ProviderType.OPENAI_COMPATIBLE,
    "make_openai_client only constructs OPENAI_COMPATIBLE clients — the Provider "
    "Registry's client_builders map already dispatches by provider_type before "
    "calling this factory, so a mismatched type here is a bug in that dispatch, "
    "never a user-supplied value",
)
def make_openai_client(
    provider: ProviderConfig,
    api_key: str,
    *,
    clock: Clock,
    gate: InferenceActivityStore,
) -> LLMClient:
    """Construct the OPENAI_COMPATIBLE ``LLMClient`` for ``provider``.

    Args:
        provider: The provider configuration; already passed
            ``client_builder.validate_structure`` upstream in
            ``backend.provider_registry``.
        api_key: The already-resolved secret value (never the env-var name;
            an empty string for a keyless local provider).
        clock: The injected time source.
        gate: The application-wide single-inference gate, used by
            ``test_inference``.

    Returns:
        A constructed client — no network call happens during construction.
    """
    return OpenAICompatibleClient(provider=provider, api_key=api_key, clock=clock, gate=gate)
```

- [ ] **Step 3: Update the module facade**

In `src/ollama_llm_bench/backend/provider_openai_compatible/__init__.py`, replace the
Task 3 scaffold body with:

```python
"""OpenAI-compatible LLM client adapter (Ollama, LM Studio, llama.cpp, OpenAI, Azure).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§10 (LLM Client) and ``docs/v3_specification/11_Services_and_Algorithms/
02_LLM_CLIENT_PROTOCOL.md``. Implements the ``LLMClient`` Protocol declared in
``backend.provider_registry`` for ``ProviderType.OPENAI_COMPATIBLE``.
"""

from ollama_llm_bench.backend.provider_openai_compatible.api import make_openai_client

__all__: list[str] = [
    "make_openai_client",
]
```

- [ ] **Step 4: Resolve the `embed` model-name open question (blocking sub-step)**

Before proceeding, read `docs/v3_specification/11_Services_and_Algorithms/ 06_EMBEDDING_SERVICE.md` §6.6a and confirm how the embedding model name reaches
`LLMClient.embed(text)`. Update `_internal/client.py::embed` and, if needed,
`OpenAICompatibleClient.__init__`'s signature and `api.py::make_openai_client`'s
signature accordingly (this may require adding an `embedding_model: str | None`
constructor parameter). Document the resolution inline in `embed`'s docstring citing the
spec section consulted.

- [ ] **Step 5: Typecheck and lint the whole module**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/ && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean.

- [ ] **Step 6: Run the icontract architecture check for this one module**

Run: `uv run pytest tests/architecture -k "icontract or provider" -v`
Expected: passes (confirms `make_openai_client` carries its required `icontract`
decorator, and that no provider SDK exception type escapes past `_internal/`, per the
existing architecture-test suite).

- [ ] **Step 7: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/_internal/client.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/api.py \
        src/ollama_llm_bench/backend/provider_openai_compatible/__init__.py
git commit -m "STORY-018: assemble OpenAICompatibleClient and make_openai_client factory (AC-8, AC-10)"
```

______________________________________________________________________

## Task 10: `testing.py` — the network-free fake

**Files:**

- Create: `src/ollama_llm_bench/backend/provider_openai_compatible/testing.py`

**Interfaces:**

- Produces: `class FakeOpenAICompatibleClient` — structurally satisfies `LLMClient`,
  modeled on `backend/stores/inference_activity/testing.py`'s fake-class convention
  (plain class, no inheritance from a Protocol, constructor-injected canned behaviour).

- [ ] **Step 1: Implement `testing.py`**

```python
"""A network-free fake ``LLMClient`` for downstream module tests.

Structurally satisfies ``LLMClient`` (``backend.provider_registry``) with no SDK, no
network, and no real streaming — callers configure canned ``ChatResponse``/exception
behaviour up front. Used by any downstream module (the benchmark pipeline, the
readiness service, provider-registry contract tests) that needs an ``LLMClient``
double without wiring the real ``openai`` SDK or a wire stub.
"""

from collections.abc import Iterator

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    InferenceTestResult,
    ModelName,
    ProviderHealth,
)
from ollama_llm_bench.backend.errors import TaskCancelledError
from ollama_llm_bench.backend.provider_registry import ChatStream

__all__: list[str] = [
    "FakeChatStream",
    "FakeOpenAICompatibleClient",
]


class FakeChatStream:
    """A canned ``ChatStream`` — yields programmed chunks, then a fixed response."""

    def __init__(self, *, chunks: tuple[ChatChunk, ...], response: ChatResponse) -> None:
        self._iterator: Iterator[ChatChunk] = iter(chunks)
        self._response = response

    def __iter__(self) -> Iterator[ChatChunk]:
        return self

    def __next__(self) -> ChatChunk:
        return next(self._iterator)

    def trailing_response(self) -> ChatResponse:
        return self._response


class FakeOpenAICompatibleClient:
    """An in-memory ``LLMClient`` double with fully canned behaviour.

    Args:
        chat_response: The ``ChatResponse`` every ``chat``/``chat_stream`` call
            returns, unless ``chat_exception`` is set.
        chat_exception: When set, every ``chat``/``chat_stream`` call raises this
            instead of returning ``chat_response``.
        embedding_vector: The vector every ``embed`` call returns.
        health: The ``ProviderHealth`` every ``probe_health`` call returns.
        models: The tuple every ``list_models`` call returns.
        inference_test_result: The ``InferenceTestResult`` every ``test_inference``
            call returns.
    """

    def __init__(
        self,
        *,
        chat_response: ChatResponse | None = None,
        chat_exception: BaseException | None = None,
        embedding_vector: tuple[float, ...] = (),
        health: ProviderHealth | None = None,
        models: tuple[ModelName, ...] = (),
        inference_test_result: InferenceTestResult | None = None,
    ) -> None:
        self._chat_response = chat_response
        self._chat_exception = chat_exception
        self._embedding_vector = embedding_vector
        self._health = health
        self._models = models
        self._inference_test_result = inference_test_result

    def list_models(self) -> tuple[ModelName, ...]:
        return self._models

    def probe_health(self) -> ProviderHealth:
        assert self._health is not None, "configure `health=` before calling probe_health"
        return self._health

    def test_inference(self, model_name: ModelName) -> InferenceTestResult:
        assert self._inference_test_result is not None, (
            "configure `inference_test_result=` before calling test_inference"
        )
        return self._inference_test_result

    def chat(self, request: ChatRequest, *, token: CancellationToken) -> ChatResponse:
        stream = self.chat_stream(request, token=token)
        for _ in stream:
            pass
        return stream.trailing_response()

    def chat_stream(self, request: ChatRequest, *, token: CancellationToken) -> ChatStream:
        if token.is_hard_cancelled:
            raise TaskCancelledError(message="cancelled before call", context=None)
        if self._chat_exception is not None:
            raise self._chat_exception
        assert self._chat_response is not None, (
            "configure `chat_response=` or `chat_exception=` before calling chat_stream"
        )
        return FakeChatStream(chunks=(), response=self._chat_response)

    def embed(self, text: str) -> tuple[float, ...]:
        return self._embedding_vector

    def supports_streaming(self) -> bool:
        return True

    def supports_reasoning_effort(self) -> bool:
        return False

    def supports_thinking(self) -> bool:
        return False

    def close(self) -> None:
        pass
```

- [ ] **Step 2: Typecheck and lint**

Run: `uv run mypy --strict src/ollama_llm_bench/backend/provider_openai_compatible/testing.py && uv run ruff check src/ollama_llm_bench/backend/provider_openai_compatible/`
Expected: both clean.

- [ ] **Step 3: Commit**

```bash
git add src/ollama_llm_bench/backend/provider_openai_compatible/testing.py
git commit -m "STORY-018: add FakeOpenAICompatibleClient testing double"
```

______________________________________________________________________

## Task 11: Full local CI mirror and traceability regeneration

**Files:** none new — verification only.

- [ ] **Step 1: Run the full local CI mirror**

Run: `just check`
Expected: `lint`, `format-check` (run `just format` first if this fails, then re-run
`just check`), `typecheck`, `import-check`, `arch-test` all pass; `trace-check` will
**fail** at this point — expected, because no test in this story yet carries a
`Proves: STORY-018-AC-N` docstring (those are the tester's job, Task 12). Confirm the
`trace-check` failure is specifically "orphan story" / "AC with no test", not a spec
citation or module resolution failure — if it reports a bad `spec_clauses` anchor or an
unknown `modules` entry, that is a real defect to fix before handing off.

- [ ] **Step 2: Run the dev-verification test suite in isolation**

Run: `uv run pytest src/ollama_llm_bench/backend/provider_openai_compatible/tests -v`
Expected: all dev-verification tests from Tasks 4–8 pass (≈23 test functions total).

- [ ] **Step 3: Confirm the coverage-layers gate is not yet meaningful for this module**

Do **not** run `just coverage-layers` as a pass/fail gate yet — the story's own
Definition of Done ties coverage to the tester's AC-proving tests, which do not exist
until Task 12. Running it now would fail on this module's low coverage from
dev-verification-only tests, which is expected and not a defect.

- [ ] **Step 4: Commit any formatting fixes from Step 1**

```bash
git add -A
git commit -m "STORY-018: apply formatting fixes from just check" --allow-empty
```

(Use `--allow-empty` only if Step 1's `just format` made no changes and this commit
would otherwise be empty; omit it if there are real changes to commit.)

______________________________________________________________________

## Task 12: Hand off to `tester`

**This is a decision point, not an automated step** — the coder's work under this plan
ends at Task 11. Per `CLAUDE.md`'s Agents Reference table, invoke the `tester` agent next
(a fresh `Agent` call, not part of this plan's task sequence) with:

- The story file, `docs/stories/story-018-openai-compatible-provider-adapter.md`.
- A pointer to this plan file for context on what was actually built and the exact
  `_internal/` module boundaries (`exception_translation.py`, `azure_transport.py`,
  `chat_stream_impl.py`, `discovery.py`, `inference_test.py`, `client.py`).
- An explicit instruction to build `tests/integration/provider_stub/` (the shared
  `pytest-httpserver`-backed wire stub fixture) first, since every AC-proving integration
  test in the story's Test Plan depends on it, then write the eight files named in the
  story's Test Plan verbatim, each test's docstring first line reading
  `"""Proves: STORY-018-AC-N`.

After `tester` finishes and `just trace-check` passes with STORY-018 fully covered,
invoke `spec-conformance-reviewer` before flipping the story's `status` to `done`, per
`CLAUDE.md`'s "Marking a story `done` without `just trace-check` passing" prohibition.

______________________________________________________________________

## Self-Review

**1. Spec coverage.** AC-1/2/3 → Task 6 (`chat_stream_impl.py`). AC-4 → Task 6. AC-5 →
Task 4 (`exception_translation.py`). AC-6 → Task 6 (cancellation) + Task 1 (the Protocol
parameter it depends on). AC-7 → Task 7 (`discovery.py`). AC-8 → Task 9
(`client.py::embed`, reusing Task 4's translator). AC-9 → Task 8 (`inference_test.py`).
AC-10 → Task 5 (`azure_transport.py`) + Task 9 (wiring). The `openai` dependency add is
Task 2. The module's five-file public surface (`__init__.py`, `api.py`, `testing.py`,
`_internal/`, `tests/`) is covered across Tasks 3, 9, 10. No AC or design constraint from
the story is left without a task.

**2. Placeholder scan.** Two intentional, explicitly-flagged exceptions to "no
placeholders" remain and are each called out inline rather than silently glossed over:
Task 9 Step 1's `# noqa: ANN201` note (a markdown-snippet limitation, not a real-file
placeholder — the note tells the coder exactly what the real file must do instead), and
Task 9 Step 4's `embed` model-name resolution, which is a **genuine open sub-question**
this plan could not resolve without reading `06_EMBEDDING_SERVICE.md` §6.6a during
implementation — it is called out as a blocking sub-step with an exact spec citation to
resolve it against, not left as a vague "handle appropriately."

**3. Type consistency.** `ChatRequest`/`ChatResponse`/`ChatChunk`/`ProviderHealth`/
`InferenceTestResult`/`InferenceTestOutcome` field names are used identically across
Tasks 4, 6, 7, 8, 9, 10 (verified against `backend/domain/models.py` directly before
writing this plan, not from memory). `open_chat_stream(...)`'s signature in Task 6 matches
its call site in Task 9's `client.py::chat_stream` exactly (`sdk_client, request, *, token, clock, provider_id`). `run_test_inference(...)`'s signature in Task 8 matches its
call site in Task 9's `client.py::test_inference` exactly. `translate_exception(...)`'s
signature in Task 4 matches every call site in Tasks 6, 7, and 9. `build_sdk_client(...)`'s
signature in Task 5 matches its call site in Task 9's `client.py::__init__`. The
`LLMClient.chat`/`chat_stream` signature extended in Task 1 (`*, token: CancellationToken`)
is used consistently in Tasks 6, 9, and 10.
