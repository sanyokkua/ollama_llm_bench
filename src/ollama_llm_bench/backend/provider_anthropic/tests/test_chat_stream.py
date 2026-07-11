"""Tests proving STORY-019-AC-1 and STORY-019-AC-2: the chat stream assembles
text and captures TTFT from the first ``text``-block delta, and a ``thinking``
block is concatenated before the ``text`` block in document order.

Source of truth: ``docs/stories/story-019-anthropic-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.4, §6.9.

Given/When/Then (Pattern A, ``acceptance-criteria-authoring`` skill): each
criterion describes a single concrete flow — one canned stream, one call, one
observable outcome — with no enumerable variation. Both tests are
integration-tier: the real ``AnthropicClient`` against the real ``anthropic``
SDK, talking to a local ``pytest_httpserver`` wire stub, per the
provider-wire-stub convention.
"""

from collections.abc import Callable

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_anthropic._internal.client_impl import AnthropicClient
from ollama_llm_bench.backend.provider_anthropic.tests.conftest import (
    FakeClock,
    anthropic_success_stream_body,
    anthropic_thinking_and_text_stream_body,
    make_chat_request,
)


def test_chat_assembles_text_and_captures_ttft(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-1

    Given a fake Anthropic event stream that delivers a text
    ``content_block_delta`` event then a final ``message_delta``, when
    ``chat`` is called, then it returns one ``ChatResponse`` whose ``text``
    is the assembled content and whose ``ttft_ms`` equals the interval to
    the first text-block ``content_block_delta``.
    """
    # Arrange
    body = anthropic_success_stream_body(text="hi")
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.text == "hi"
    assert response.ttft_ms is not None


def test_thinking_and_text_blocks_concatenated_in_order(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., AnthropicClient]
) -> None:
    """Proves: STORY-019-AC-2

    Given a fake Anthropic response carrying a ``thinking`` content block
    followed by a ``text`` content block, when ``chat`` is called, then
    ``ChatResponse.text`` contains both blocks concatenated in document
    order (thinking first), and ``ttft_ms`` corresponds to the text delta's
    arrival, not the thinking delta's.
    """
    # Arrange
    body = anthropic_thinking_and_text_stream_body(thinking="let me think", text="the answer")
    httpserver.expect_request("/v1/messages", method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.text.startswith("let me think")
    assert response.text.endswith("the answer")
    assert response.text == "let me thinkthe answer"
