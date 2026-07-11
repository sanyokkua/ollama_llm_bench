"""The shared ``LLMClient`` contract-test suite (§6a) — runs against both the real
``OpenAICompatibleClient`` (wire-stub-backed, §7a) and the
``provider_openai_compatible/testing.py`` fake, proving the fake is a faithful
stand-in for the real adapter.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/07_TESTING_STANDARD.md``
§6a; ``docs/stories/story-018-openai-compatible-provider-adapter.md`` Definition of
Done ("The ``LLMClient`` shared contract-test suite (§6a) runs against both the real
adapter (wire stub, §7a) and ``provider_openai_compatible/testing.py``, and both legs
pass.").

This is the **first** contract suite in the codebase — STORY-018 is the first
concrete ``LLMClient`` provider adapter to ship alongside its ``testing.py`` fake.
Every assertion below is a genuine ``LLMClient`` Protocol-level behavioural contract
(``08_Cross_Cutting/08-E_interfaces_contracts.md`` §10: return shapes, the
never-raises rules for ``probe_health``/``test_inference``) — never a
provider-specific wire detail. The suite is parametrized ``params=["real", "fake"]``
via the ``llm_client`` fixture below; both legs must pass in the pull-request gate.

The real leg reuses the wire-stub fixture patterns already established in
``src/ollama_llm_bench/backend/provider_openai_compatible/tests/conftest.py``
(``FakeClock``, ``FakeEventBus``, the ``threaded=True`` httpserver override) rather
than duplicating them — this module imports those helpers directly. The fake leg
constructs ``FakeOpenAICompatibleClient`` from the module's own ``testing.py`` and
configures its canned responses to be shape-comparable with the real leg's wire-stub
responses (non-empty ``text``, a populated embedding vector, etc.).
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


@pytest.fixture(params=["real", "fake"])
def llm_client(request: pytest.FixtureRequest, httpserver: HTTPServer) -> LLMClient:
    """Parametrized ``LLMClient`` under test: the real wire-stub-backed adapter,
    or the module's ``testing.py`` fake — both legs run every test below."""
    if request.param == "real":
        return _make_real_client(httpserver)
    return _make_fake_client()


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


def test_list_models_returns_tuple_of_strings(llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-7

    Given any ``LLMClient`` implementation, when ``list_models`` is called,
    then it returns a ``tuple[str, ...]``.
    """
    # Act
    models = llm_client.list_models()

    # Assert
    assert isinstance(models, tuple)
    assert all(isinstance(model, str) for model in models)


def test_embed_returns_tuple_of_floats(llm_client: LLMClient) -> None:
    """Proves: STORY-018-AC-8

    Given any ``LLMClient`` implementation with an embedding model
    configured, when ``embed(text)`` is called, then it returns a
    ``tuple[float, ...]`` matching the canned vector's dimensionality.
    """
    # Act
    vector = llm_client.embed("hello world")

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
