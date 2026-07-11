"""Tests proving STORY-019-AC-8: ``max_tokens`` is always present on the SDK
request, whether the caller supplied a value or relied on the domain
default.

Source of truth: ``docs/stories/story-019-anthropic-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.9 (DD-67).

Unit-tier (per the story's Test Plan): the wire stub records every request it
receives, so the test asserts the actual JSON body sent to
``POST /v1/messages`` always carries a ``max_tokens`` field — a genuine,
real-SDK-produced request body, not a hand-constructed one.
"""

from collections.abc import Callable
import json

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain import (
    ChatMessage,
    ChatRequest,
    ChatRole,
    ReasoningEffort,
    ResponseFormat,
)
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic.tests.conftest import (
    FakeClock,
    anthropic_success_stream_body,
)

_EXPLICIT_MAX_TOKENS = 512


def test_max_tokens_always_present_in_request(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-8

    Given any Anthropic chat request, when it is built for the SDK, then
    ``max_tokens`` is always present (default 4096 when the caller supplied
    none), so the SDK-required field is never omitted.
    """
    # Arrange
    body = anthropic_success_stream_body(text="hi")
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = ChatRequest(
        model="claude-test-model",
        messages=(ChatMessage(role=ChatRole.USER, content="hello"),),
        timeout_ms=5000,
        reasoning_effort=ReasoningEffort.DEFAULT,
        response_format=ResponseFormat.TEXT,
        echo_tokens_to_log=False,
    )
    token = CancellationToken(clock=fake_clock)

    # Act
    client.chat(request, token=token)

    # Assert
    assert len(httpserver.log) == 1
    sent_request, _ = httpserver.log[0]
    sent_body = json.loads(sent_request.get_data())
    assert "max_tokens" in sent_body
    assert sent_body["max_tokens"] == request.max_output_tokens


def test_max_tokens_reflects_an_explicit_caller_value(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-8

    Given a ``ChatRequest`` with an explicit ``max_output_tokens``, when it
    is built for the SDK, then the sent ``max_tokens`` field carries that
    explicit value, not the domain default.
    """
    # Arrange
    body = anthropic_success_stream_body(text="hi")
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = ChatRequest(
        model="claude-test-model",
        messages=(ChatMessage(role=ChatRole.USER, content="hello"),),
        timeout_ms=5000,
        max_output_tokens=_EXPLICIT_MAX_TOKENS,
        reasoning_effort=ReasoningEffort.DEFAULT,
        response_format=ResponseFormat.TEXT,
        echo_tokens_to_log=False,
    )
    token = CancellationToken(clock=fake_clock)

    # Act
    client.chat(request, token=token)

    # Assert
    sent_request, _ = httpserver.log[0]
    sent_body = json.loads(sent_request.get_data())
    assert sent_body["max_tokens"] == _EXPLICIT_MAX_TOKENS
