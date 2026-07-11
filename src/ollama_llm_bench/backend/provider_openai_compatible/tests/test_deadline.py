"""Tests proving STORY-018-AC-4: a stall past ``ChatRequest.timeout_ms`` raises
``HttpTimeoutError`` (the taxonomy leaf the story's AC text names ``TimeoutError``;
see ``backend/errors/_internal/hierarchy.py``) and closes the stream.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.3
(the finite-deadline invariant, SPEC-015).
"""

from collections.abc import Callable, Generator
import json
import time

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.errors import HttpTimeoutError
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)
from ollama_llm_bench.backend.provider_openai_compatible.tests.conftest import (
    FakeClock,
    make_chat_request,
)

_STALL_SECONDS = 3.0


def _stalling_handler(request: Request) -> Response:
    """Sleep well past every deadline used in this file, then return an empty body."""
    del request
    time.sleep(_STALL_SECONDS)
    return Response("data: [DONE]\n\n", content_type="text/event-stream")


def _mid_stream_stall_handler(request: Request) -> Response:
    """Emit one real content chunk, then stall past every deadline in this file.

    Exercises the SDK's own mid-stream ``httpx.ReadTimeout`` path — distinct
    from the immediate-stall handler above, which fires the SDK's *initial*
    connection/read timeout before any byte is sent.
    """
    del request

    def _body() -> Generator[bytes]:
        chunk = {
            "id": "1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {"content": "hi"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk)}\n\n".encode()
        time.sleep(_STALL_SECONDS)
        yield b"data: [DONE]\n\n"

    return Response(_body(), content_type="text/event-stream", direct_passthrough=True)


def test_stall_past_deadline_raises_timeout_and_closes_stream(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Proves: STORY-018-AC-4

    Given the endpoint stalls past ``ChatRequest.timeout_ms``, when ``chat``
    is called, then it raises ``HttpTimeoutError`` (the application's
    ``TimeoutError``-category taxonomy leaf) and returns no ``ChatResponse``.
    The underlying SDK transport's own short read timeout — set by the
    client's ``_STREAM_READ_TIMEOUT_S`` constant — fires first and is
    translated to the same leaf, closing the connection either way.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_handler(
        _stalling_handler
    )
    client = make_client(settings=OpenAICompatibleClientSettings(connect_timeout_ms=5000))
    request = make_chat_request(timeout_ms=200)
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(HttpTimeoutError):
        client.chat(request, token=token)


def test_mid_stream_stall_raises_timeout_and_closes_stream(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Proves: STORY-018-AC-4

    Given the endpoint sends one real content chunk and then stalls past
    ``ChatRequest.timeout_ms``, when ``chat`` is called, then it raises
    ``HttpTimeoutError`` and returns no ``ChatResponse`` — proving the
    chunk-boundary translation path (``OpenAICompatibleChatStream.__next__``'s
    boundary catch-all) classifies a bare mid-stream ``httpx.ReadTimeout`` as
    a timeout, not a generic connection failure.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_handler(
        _mid_stream_stall_handler
    )
    client = make_client(settings=OpenAICompatibleClientSettings(connect_timeout_ms=5000))
    request = make_chat_request(timeout_ms=200)
    token = CancellationToken(clock=fake_clock)

    # Act / Assert
    with pytest.raises(HttpTimeoutError):
        client.chat(request, token=token)
