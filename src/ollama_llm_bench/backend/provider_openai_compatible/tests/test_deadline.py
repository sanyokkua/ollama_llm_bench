"""Tests proving STORY-018-AC-4: a stall past ``ChatRequest.timeout_ms`` raises
``HttpTimeoutError`` (the taxonomy leaf the story's AC text names ``TimeoutError``;
see ``backend/errors/_internal/hierarchy.py``) and closes the stream.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.3
(the finite-deadline invariant, SPEC-015).

The last two tests are regression guards for the live defect STORY-086's opt-in tier
found: the streaming call's transport ``read`` timeout used to be a fixed 0.5 s, and a
local provider withholds the HTTP response headers until generation begins, so every
cold model failed with a timeout before its first token. They carry no ``Proves:`` line
because they guard a defect rather than an acceptance criterion.
"""

from collections.abc import Callable, Generator
import json
import time

import httpx
import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.errors import HttpTimeoutError
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    _STREAM_POOL_TIMEOUT_S,
    _STREAM_WRITE_TIMEOUT_S,
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
# Longer than the 0.5 s the streaming `read` timeout was pinned to before STORY-086, and
# well short of `_BUDGET_MS`, so it isolates exactly the defect being guarded.
_HEADER_WITHHOLD_SECONDS = 1.5
_BUDGET_MS = 8000
_CONNECT_TIMEOUT_MS = 5000


def _chunk_line() -> bytes:
    """Return one well-formed SSE line carrying the content delta ``"hi"``."""
    chunk = {
        "id": "1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "delta": {"content": "hi"}, "finish_reason": None}],
    }
    return f"data: {json.dumps(chunk)}\n\n".encode()


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
        yield _chunk_line()
        time.sleep(_STALL_SECONDS)
        yield b"data: [DONE]\n\n"

    return Response(_body(), content_type="text/event-stream", direct_passthrough=True)


def _cold_start_handler(request: Request) -> Response:
    """Withhold the response headers, then stream one normal chunk and finish.

    The shape a cold local model actually produces: Ollama sends no HTTP response
    headers at all until generation begins, and httpx's ``read`` timeout governs that
    header wait. Yielding nothing for ``_HEADER_WITHHOLD_SECONDS`` reproduces it, because
    a WSGI server may not flush the headers before the application yields its first
    non-empty bytestring.
    """
    del request

    def _body() -> Generator[bytes]:
        time.sleep(_HEADER_WITHHOLD_SECONDS)
        yield _chunk_line()
        yield b"data: [DONE]\n\n"

    return Response(_body(), content_type="text/event-stream", direct_passthrough=True)


def _prompt_start_handler(request: Request) -> Response:
    """Stream one normal chunk and finish, with no delay anywhere."""
    del request

    def _body() -> Generator[bytes]:
        yield _chunk_line()
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
    The transport's own ``read`` timeout is what actually fires here: it is
    this call's remaining budget (``timeout_ms=200`` → 0.2 s), and this test's
    ``fake_clock`` never advances, so the between-chunks deadline check in
    ``OpenAICompatibleChatStream.__next__`` cannot fire. ``httpx.ReadTimeout``
    is translated to the same leaf, closing the connection either way.
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


def test_stream_read_timeout_handed_to_the_sdk_is_the_request_budget(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Regression guard (STORY-086 live defect): the streaming call's transport ``read``
    timeout is ``ChatRequest.timeout_ms``, not a fixed sub-second constant.

    Given a request carrying an 8 s budget, when ``chat`` is called, then the
    ``httpx.Timeout`` the SDK hands to the transport carries ``read=8.0`` — and
    ``connect``/``write``/``pool`` are unchanged. Asserted at the httpx request hook, so
    the value observed is the one that actually reached the socket, not one re-derived
    from the client's own source.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_handler(
        _prompt_start_handler
    )
    client = make_client(
        settings=OpenAICompatibleClientSettings(connect_timeout_ms=_CONNECT_TIMEOUT_MS)
    )
    captured: list[object] = []

    def _capture(request: httpx.Request) -> None:
        captured.append(request.extensions["timeout"])

    client._sdk_client._client.event_hooks["request"].append(_capture)
    request = make_chat_request(timeout_ms=_BUDGET_MS)
    token = CancellationToken(clock=fake_clock)

    # Act
    client.chat(request, token=token)

    # Assert
    assert captured == [
        {
            "connect": _CONNECT_TIMEOUT_MS / 1000,
            "read": _BUDGET_MS / 1000,
            "write": _STREAM_WRITE_TIMEOUT_S,
            "pool": _STREAM_POOL_TIMEOUT_S,
        }
    ]


def test_cold_start_within_budget_streams_instead_of_timing_out(
    httpserver: HTTPServer,
    fake_clock: FakeClock,
    make_client: Callable[..., OpenAICompatibleClient],
) -> None:
    """Regression guard (STORY-086 live defect): a first token slower than a second, but
    inside the call's budget, completes rather than raising ``HttpTimeoutError``.

    Given the endpoint withholds its response headers for 1.5 s — what a cold local model
    does — and the request's budget is 8 s, when ``chat`` is called, then it returns the
    streamed text. Before STORY-086 this raised ``HttpTimeoutError`` at 0.5 s, making every
    cold model unbenchmarkable.
    """
    # Arrange
    httpserver.expect_request("/chat/completions", method="POST").respond_with_handler(
        _cold_start_handler
    )
    client = make_client(
        settings=OpenAICompatibleClientSettings(connect_timeout_ms=_CONNECT_TIMEOUT_MS)
    )
    request = make_chat_request(timeout_ms=_BUDGET_MS)
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.text == "hi"
