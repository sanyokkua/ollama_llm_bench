"""The shared ``LLMClient`` contract-test suite (§6a) — runs against both real
provider adapters (wire-stub-backed, §7a) and their ``testing.py`` fakes,
proving each fake is a faithful stand-in for its real adapter.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md``
§6a; ``docs/stories/story-018-openai-compatible-provider-adapter.md`` and
``docs/stories/story-019-anthropic-provider-adapter.md`` Definition of Done
("The ``LLMClient`` shared contract-test suite (§6a) runs against both the real
adapter (wire stub, §7a) and the module's ``testing.py`` fake, and both legs
pass.").

This is the **first** contract suite in the codebase — STORY-018 is the first
concrete ``LLMClient`` provider adapter to ship alongside its ``testing.py`` fake;
STORY-019 adds the ``ANTHROPIC`` real/fake legs onto the same suite. Every
assertion below is a genuine ``LLMClient`` Protocol-level behavioural contract
(``08_Cross_Cutting/08-E_interfaces_contracts.md`` §10: return shapes, the
never-raises rules for ``probe_health``/``test_inference``) — never a
provider-specific wire detail. The suite is parametrized
``params=["openai_real", "openai_fake", "anthropic_real", "anthropic_fake"]``
via the ``llm_client`` fixture below; every leg must pass in the pull-request
gate. ``embed``/``list_models`` are OpenAI-only Protocol-level assertions
(``test_embed_returns_tuple_of_floats``, ``test_list_models_returns_tuple_of_strings``)
because Anthropic's ``LLMClient`` deliberately raises immediately from both —
per-provider-type behaviour §6.9, not a Protocol-level contract every
implementation shares; STORY-019's own colocated
``tests/test_probe_and_embed.py`` proves the Anthropic raise-immediately
contract instead.

The real legs reuse the wire-stub fixture patterns already established in
``src/ollama_llm_bench/backend/provider_openai_compatible/tests/conftest.py``
and ``src/ollama_llm_bench/backend/provider_anthropic/tests/conftest.py``
(``FakeClock``, ``FakeEventBus``, the ``threaded=True`` httpserver override)
rather than duplicating them — this module imports those helpers directly.
Each fake leg constructs the module's own fake from its ``testing.py`` and
configures its canned responses to be shape-comparable with the real leg's
wire-stub responses (non-empty ``text``, a populated embedding vector, etc.).
"""

from collections.abc import Iterator
import json
from ssl import SSLContext

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatChunk,
    ChatResponse,
    InferenceTestOutcome,
    InferenceTestResult,
    ProviderHealth,
)
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic._internal.collaborators import (
    AnthropicClientCollaborators,
)
from ollama_llm_bench.backend.provider_anthropic.models import AnthropicClientSettings
from ollama_llm_bench.backend.provider_anthropic.testing import FakeAnthropicClient
from ollama_llm_bench.backend.provider_anthropic.tests.conftest import (
    anthropic_success_stream_body,
    make_provider_config as make_anthropic_provider_config,
)
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini._internal.collaborators import (
    GeminiClientCollaborators,
)
from ollama_llm_bench.backend.provider_gemini.models import GeminiClientSettings
from ollama_llm_bench.backend.provider_gemini.testing import FakeGeminiClient
from ollama_llm_bench.backend.provider_gemini.tests.conftest import (
    gemini_success_stream_body,
    make_provider_config as make_gemini_provider_config,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible._internal.collaborators import (
    OpenAICompatibleClientCollaborators,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.provider_openai_compatible.testing import (
    FakeOpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import (
    FakeClock,
    FakeEventBus,
    make_chat_request,
    make_provider_config,
)
from ollama_llm_bench.backend.provider_registry import LLMClient
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore

pytestmark = pytest.mark.integration

_CANNED_TEXT = "hello from the contract suite"
_CANNED_VECTOR = (0.1, 0.2, 0.3, 0.4)
_EXPECTED_VECTOR_LEN = 4
_ANTHROPIC_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_GEMINI_PROVIDER_ID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture(scope="session")
def make_httpserver(
    httpserver_listen_address: tuple[str | None, int | None],
    httpserver_ssl_context: SSLContext | None,
) -> Iterator[HTTPServer]:
    """Override ``pytest_httpserver``'s fixture to run the server ``threaded=True``.

    Mirrors ``provider_openai_compatible/tests/conftest.py``: a slow-handler
    scenario elsewhere in the session-scoped server must never stall a
    concurrent contract-suite request. See that module's docstring for the
    full rationale.
    """
    host, port = httpserver_listen_address
    server = HTTPServer(
        host=host or HTTPServer.DEFAULT_LISTEN_HOST,
        port=port or HTTPServer.DEFAULT_LISTEN_PORT,
        ssl_context=httpserver_ssl_context,
        threaded=True,
    )
    server.start()
    yield server
    server.clear()
    if server.is_running():
        server.stop()


def _sse_body(chunks: list[dict[str, object]]) -> str:
    """Assemble a canned SSE stream body from a list of chunk payloads."""
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


def _content_chunk(content: str) -> dict[str, object]:
    return {
        "id": "1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }


def _register_chat_stub(httpserver: HTTPServer) -> None:
    """Register the canned streaming chat response the real leg's ``chat``/
    ``chat_stream`` calls consume for every contract assertion below."""
    body = _sse_body([_content_chunk(_CANNED_TEXT)])
    httpserver.expect_request("/chat/completions", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )


def _register_models_stub(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/", method="GET").respond_with_json({"ok": True})
    httpserver.expect_request("/models", method="GET").respond_with_json(
        {"object": "list", "data": [{"id": "test-model", "object": "model"}]}
    )


def _register_embeddings_stub(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/embeddings", method="POST").respond_with_json(
        {
            "object": "list",
            "data": [{"object": "embedding", "index": 0, "embedding": list(_CANNED_VECTOR)}],
            "model": "embed-model",
            "usage": {"prompt_tokens": 3, "total_tokens": 3},
        }
    )


def _make_real_client(httpserver: HTTPServer) -> OpenAICompatibleClient:
    """Build a real ``OpenAICompatibleClient`` wired against ``httpserver``, with
    every wire-stub route this suite exercises pre-registered."""
    _register_chat_stub(httpserver)
    _register_models_stub(httpserver)
    _register_embeddings_stub(httpserver)
    clock = FakeClock()
    event_bus = FakeEventBus()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    config = make_provider_config(base_url=httpserver.url_for("/"))
    collaborators = OpenAICompatibleClientCollaborators(
        clock=clock, event_bus=event_bus, inference_activity_store=gate
    )
    settings = OpenAICompatibleClientSettings(embedding_model="embed-model")
    return OpenAICompatibleClient(
        config=config, resolved_api_key="", collaborators=collaborators, settings=settings
    )


def _make_fake_client() -> FakeOpenAICompatibleClient:
    """Build a ``FakeOpenAICompatibleClient`` with every canned response this
    suite's assertions need, shape-comparable to the real leg's wire responses."""
    fake = FakeOpenAICompatibleClient()
    fake.set_chat_response(
        ChatResponse(text=_CANNED_TEXT, total_time_ms=1, ttft_ms=1),
        chunks=(ChatChunk(content=_CANNED_TEXT),),
    )
    fake.set_probe_health(
        ProviderHealth(
            provider_id="11111111-1111-4111-8111-111111111111",
            reachable=True,
            discovery_supported=True,
            model_count=1,
            last_probe_ms=1,
            probed_at=1,
        )
    )
    fake.set_models(("test-model",))
    fake.set_test_inference_result(
        InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id="11111111-1111-4111-8111-111111111111",
            model_name="test-model",
            latency_ms=1,
            response_excerpt=_CANNED_TEXT,
            tested_at=1,
        )
    )
    fake.set_embed_vector(_CANNED_VECTOR)
    return fake


def _make_anthropic_real_client(httpserver: HTTPServer) -> AnthropicClient:
    """Build a real ``AnthropicClient`` wired against ``httpserver``, with the
    canned streaming chat response pre-registered at the real SDK's
    ``/v1/messages`` path.

    ``probe_health`` and ``test_inference`` both reuse this same registered
    route: ``probe_health`` issues a bare reachability ``GET /`` (matched by
    ``pytest_httpserver``'s implicit fallback of an unmatched path to 404,
    which is still a successful TCP/HTTP round trip — reachable), and
    ``test_inference`` issues its own canned-prompt ``POST /v1/messages``
    against the same stub.
    """
    body = anthropic_success_stream_body(text=_CANNED_TEXT)
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    clock = FakeClock()
    event_bus = FakeEventBus()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    config = make_anthropic_provider_config(base_url=httpserver.url_for("/"))
    collaborators = AnthropicClientCollaborators(
        clock=clock, event_bus=event_bus, inference_activity_store=gate
    )
    return AnthropicClient(
        config=config,
        resolved_api_key="sk-ant-test-key",
        collaborators=collaborators,
        settings=AnthropicClientSettings(),
    )


def _make_anthropic_fake_client() -> FakeAnthropicClient:
    """Build a ``FakeAnthropicClient`` with every canned response this suite's
    assertions need, shape-comparable to the real leg's wire responses."""
    fake = FakeAnthropicClient()
    fake.set_chat_response(
        ChatResponse(text=_CANNED_TEXT, total_time_ms=1, ttft_ms=1),
        chunks=(ChatChunk(content=_CANNED_TEXT),),
    )
    fake.set_probe_health(
        ProviderHealth(
            provider_id=_ANTHROPIC_PROVIDER_ID,
            reachable=True,
            discovery_supported=False,
            model_count=None,
            last_probe_ms=1,
            probed_at=1,
        )
    )
    fake.set_test_inference_result(
        InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id=_ANTHROPIC_PROVIDER_ID,
            model_name="claude-test-model",
            latency_ms=1,
            response_excerpt=_CANNED_TEXT,
            tested_at=1,
        )
    )
    return fake


def _make_gemini_real_client(httpserver: HTTPServer) -> GeminiClient:
    """Build a real ``GeminiClient`` wired against ``httpserver``, with the
    canned streaming chat response pre-registered at the real SDK's
    ``streamGenerateContent`` path and the canned embedding response
    pre-registered at its ``batchEmbedContents`` path.

    ``probe_health`` issues a bare reachability ``GET /`` (matched by
    ``pytest_httpserver``'s implicit fallback of an unmatched path to 404,
    still a successful TCP/HTTP round trip — reachable) followed by
    ``GET /v1beta/models`` for discovery; ``test_inference`` reuses the same
    registered streaming route as ``chat``.
    """
    body = gemini_success_stream_body(text=_CANNED_TEXT)
    httpserver.expect_request(
        "/v1beta/models/test-model:streamGenerateContent", method="POST"
    ).respond_with_data(body, content_type="text/event-stream")
    httpserver.expect_request("/v1beta/models", method="GET").respond_with_json(
        {"models": [{"name": "models/test-model"}]}
    )
    httpserver.expect_request(
        "/v1beta/models/embed-model:batchEmbedContents", method="POST"
    ).respond_with_json({"embeddings": [{"values": list(_CANNED_VECTOR)}]})
    clock = FakeClock()
    event_bus = FakeEventBus()
    gate = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    config = make_gemini_provider_config(base_url=httpserver.url_for("/"))
    collaborators = GeminiClientCollaborators(
        clock=clock, event_bus=event_bus, inference_activity_store=gate
    )
    settings = GeminiClientSettings(embedding_model="embed-model")
    return GeminiClient(
        config=config, resolved_api_key="test-key", collaborators=collaborators, settings=settings
    )


def _make_gemini_fake_client() -> FakeGeminiClient:
    """Build a ``FakeGeminiClient`` with every canned response this suite's
    assertions need, shape-comparable to the real leg's wire responses."""
    fake = FakeGeminiClient()
    fake.set_chat_response(
        ChatResponse(text=_CANNED_TEXT, total_time_ms=1, ttft_ms=1),
        chunks=(ChatChunk(content=_CANNED_TEXT),),
    )
    fake.set_probe_health(
        ProviderHealth(
            provider_id=_GEMINI_PROVIDER_ID,
            reachable=True,
            discovery_supported=True,
            model_count=1,
            last_probe_ms=1,
            probed_at=1,
        )
    )
    fake.set_models(("test-model",))
    fake.set_test_inference_result(
        InferenceTestResult(
            outcome=InferenceTestOutcome.SUCCESS,
            provider_id=_GEMINI_PROVIDER_ID,
            model_name="test-model",
            latency_ms=1,
            response_excerpt=_CANNED_TEXT,
            tested_at=1,
        )
    )
    fake.set_embed_vector(_CANNED_VECTOR)
    return fake


def _build_llm_client(param: str, httpserver: HTTPServer) -> LLMClient:
    """Build the ``LLMClient`` leg named by ``param``; shared by both
    parametrized fixtures below."""
    if param == "openai_real":
        return _make_real_client(httpserver)
    if param == "openai_fake":
        return _make_fake_client()
    if param == "anthropic_real":
        return _make_anthropic_real_client(httpserver)
    if param == "anthropic_fake":
        return _make_anthropic_fake_client()
    if param == "gemini_real":
        return _make_gemini_real_client(httpserver)
    return _make_gemini_fake_client()


@pytest.fixture(
    params=[
        "openai_real",
        "openai_fake",
        "anthropic_real",
        "anthropic_fake",
        "gemini_real",
        "gemini_fake",
    ]
)
def llm_client(request: pytest.FixtureRequest, httpserver: HTTPServer) -> LLMClient:
    """Parametrized ``LLMClient`` under test: each real wire-stub-backed
    adapter and its ``testing.py`` fake — every leg runs every test below."""
    param: str = request.param
    return _build_llm_client(param, httpserver)


@pytest.fixture(params=["openai_real", "openai_fake", "gemini_real", "gemini_fake"])
def embedding_capable_llm_client(
    request: pytest.FixtureRequest, httpserver: HTTPServer
) -> LLMClient:
    """Parametrized ``LLMClient`` under test, embedding/discovery-capable legs only.

    Used only by ``test_embed_returns_tuple_of_floats`` and
    ``test_list_models_returns_tuple_of_strings`` — Anthropic's ``embed``/
    ``list_models`` deliberately raise immediately (§6.9/§6.9.1), so those
    two assertions are not a Protocol-level contract every implementation
    shares; STORY-019's own colocated tests prove the Anthropic raise
    behaviour instead. OpenAI-compatible and Gemini both implement ``embed``/
    ``list_models`` for real (§6.9), so both join this fixture — STORY-020
    adds the Gemini legs onto what was previously an OpenAI-only fixture.
    """
    param: str = request.param
    return _build_llm_client(param, httpserver)


@pytest.fixture
def clock() -> FakeClock:
    """A fresh ``FakeClock`` used only to build the ``CancellationToken`` below."""
    return FakeClock()


def test_chat_returns_chat_response_with_text(llm_client: LLMClient, clock: FakeClock) -> None:
    """Proves: STORY-018-AC-1

    Given any ``LLMClient`` implementation (real or fake), when ``chat`` is
    called, then it returns a ``ChatResponse`` whose ``text`` is a non-empty
    ``str`` — the Protocol-level return-shape contract both legs must honour.
    """
    # Arrange
    request = make_chat_request()
    token = CancellationToken(clock=clock)

    # Act
    response = llm_client.chat(request, token=token)

    # Assert
    assert isinstance(response, ChatResponse)
    assert isinstance(response.text, str)
    assert response.text != ""


def test_chat_stream_yields_chunks_and_exposes_trailing_response(
    llm_client: LLMClient, clock: FakeClock
) -> None:
    """Proves: STORY-018-AC-1

    Given any ``LLMClient`` implementation, when ``chat_stream`` is called,
    then the returned stream is iterable, yields ``ChatChunk`` objects, and
    ``trailing_response()`` returns a ``ChatResponse`` after exhaustion.
    """
    # Arrange
    request = make_chat_request()
    token = CancellationToken(clock=clock)

    # Act
    stream = llm_client.chat_stream(request, token=token)
    chunks = list(stream)
    trailing = stream.trailing_response()

    # Assert
    assert all(isinstance(chunk, ChatChunk) for chunk in chunks)
    assert isinstance(trailing, ChatResponse)


def test_probe_health_never_raises_and_returns_provider_health(llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-7

    Given any ``LLMClient`` implementation, when ``probe_health`` is called,
    then it never raises and returns a ``ProviderHealth`` — the Protocol's
    never-raise contract holds identically for the real adapter and the fake.
    """
    # Act
    health = llm_client.probe_health()

    # Assert
    assert isinstance(health, ProviderHealth)


def test_test_inference_never_raises_and_returns_inference_test_result(
    llm_client: LLMClient,
) -> None:
    """Proves: STORY-018-AC-9

    Given any ``LLMClient`` implementation, when ``test_inference`` is
    called, then it never raises and returns an ``InferenceTestResult``.
    """
    # Act
    result = llm_client.test_inference("test-model")

    # Assert
    assert isinstance(result, InferenceTestResult)


def test_list_models_returns_tuple_of_strings(embedding_capable_llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-7

    Given any embedding/discovery-capable ``LLMClient`` implementation, when
    ``list_models`` is called, then it returns a ``tuple[str, ...]``. Scoped
    to the embedding/discovery-capable legs (OpenAI-compatible and Gemini)
    only — Anthropic's ``list_models`` deliberately raises immediately
    (STORY-019 §6.9.1), so this is a per-provider-type contract, not a
    Protocol-wide one.
    """
    # Act
    models = embedding_capable_llm_client.list_models()

    # Assert
    assert isinstance(models, tuple)
    assert all(isinstance(model, str) for model in models)


def test_embed_returns_tuple_of_floats(embedding_capable_llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-8

    Given any embedding/discovery-capable ``LLMClient`` implementation with
    an embedding model configured, when ``embed(text)`` is called, then it
    returns a ``tuple[float, ...]`` matching the canned vector's
    dimensionality. Scoped to the embedding/discovery-capable legs
    (OpenAI-compatible and Gemini) only — Anthropic's ``embed`` deliberately
    raises immediately (STORY-019-AC-6), so this is a per-provider-type
    contract, not a Protocol-wide one.
    """
    # Act
    vector = embedding_capable_llm_client.embed("hello world")

    # Assert
    assert isinstance(vector, tuple)
    assert len(vector) == _EXPECTED_VECTOR_LEN
    assert all(isinstance(value, float) for value in vector)


def test_capability_flags_return_bool(llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-1

    Given any ``LLMClient`` implementation, when the three ``supports_*``
    capability methods are called, then each returns a plain ``bool``.
    """
    # Act / Assert
    assert isinstance(llm_client.supports_streaming(), bool)
    assert isinstance(llm_client.supports_reasoning_effort(), bool)
    assert isinstance(llm_client.supports_thinking(), bool)


def test_close_does_not_raise_and_is_idempotent(llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-1

    Given any ``LLMClient`` implementation, when ``close()`` is called
    twice, then neither call raises — ``close`` is idempotent for both the
    real adapter and the fake.
    """
    # Act / Assert
    llm_client.close()
    llm_client.close()
