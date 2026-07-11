"""Tests proving STORY-019-AC-3: input tokens read from ``message_start``,
output tokens from the final ``message_delta``; both ``None`` when a response
carries no usage at all.

Source of truth: ``docs/stories/story-019-anthropic-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.5.

Given/When/Then (Pattern A): the criterion states two related but distinct
concrete flows (usage present -> read; usage absent -> both ``None``) sharing
one precondition family, tested as two focused functions rather than a table
— there is no enumerable variation across a case set, just a presence/absence
pair.
"""

from collections.abc import Callable

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic.tests.conftest import (
    FakeClock,
    anthropic_success_stream_body,
    make_chat_request,
    sse_event,
)

_EXPECTED_PROMPT_TOKENS = 17
_EXPECTED_COMPLETION_TOKENS = 6


def test_usage_read_from_message_start_and_message_delta(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-3

    Given a fake Anthropic stream that carries ``message_start`` input usage
    and a final ``message_delta`` output usage, when ``chat`` is called,
    then ``ChatResponse.prompt_tokens`` comes from ``message_start`` and
    ``ChatResponse.completion_tokens`` comes from the final ``message_delta``.
    """
    # Arrange
    body = anthropic_success_stream_body(
        text="hi", input_tokens=_EXPECTED_PROMPT_TOKENS, output_tokens=_EXPECTED_COMPLETION_TOKENS
    )
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.prompt_tokens == _EXPECTED_PROMPT_TOKENS
    assert response.completion_tokens == _EXPECTED_COMPLETION_TOKENS


def test_usage_absent_leaves_both_token_counts_none(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-3

    Given a response with no usage data at all (no ``message_start``, no
    ``message_delta`` usage), when ``chat`` is called, then both
    ``prompt_tokens`` and ``completion_tokens`` are ``None``.
    """
    # Arrange: a minimal stream with a text delta but no usage-carrying events.
    body = "".join(
        [
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "hi"},
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": 0}),
            sse_event("message_stop", {"type": "message_stop"}),
        ]
    )
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.prompt_tokens is None
    assert response.completion_tokens is None
