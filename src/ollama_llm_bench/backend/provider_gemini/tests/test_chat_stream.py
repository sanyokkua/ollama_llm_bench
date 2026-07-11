"""Tests proving STORY-020-AC-1 and STORY-020-AC-3.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.2-6.3, §6.9 (reasoning-part concatenation).
"""

from collections.abc import Callable

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini.tests.conftest import (
    FakeClock,
    gemini_reasoning_and_text_stream_body,
    gemini_success_stream_body,
    make_chat_request,
)

_STREAM_PATH = "/v1beta/models/gemini-test-model:streamGenerateContent"
_EXPECTED_PROMPT_TOKENS = 10
_EXPECTED_COMPLETION_TOKENS = 3


def test_chat_assembles_text_and_captures_ttft_and_usage(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-1

    Given a fake Gemini stream that delivers a text-carrying chunk with
    ``usageMetadata``, when ``chat`` is called, then it returns one
    ``ChatResponse`` whose ``text`` is the assembled content, whose
    ``ttft_ms`` is set (the interval to the first text-carrying part), and
    whose ``prompt_tokens``/``completion_tokens`` come from that chunk's
    ``usageMetadata``.
    """
    # Arrange
    body = gemini_success_stream_body(
        text="hello there",
        prompt_tokens=_EXPECTED_PROMPT_TOKENS,
        candidates_tokens=_EXPECTED_COMPLETION_TOKENS,
    )
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.text == "hello there"
    assert response.ttft_ms is not None
    assert response.prompt_tokens == _EXPECTED_PROMPT_TOKENS
    assert response.completion_tokens == _EXPECTED_COMPLETION_TOKENS


def test_reasoning_and_text_parts_concatenated_in_order(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-3

    Given a fake Gemini response carrying a reasoning part (``thought:
    true``) followed by a text part, when ``chat`` is called, then
    ``ChatResponse.text`` contains both parts concatenated in document
    order (reasoning first), so a later inference phase can strip the
    reasoning part.
    """
    # Arrange
    body = gemini_reasoning_and_text_stream_body(reasoning="let me think", text="the answer")
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    response = client.chat(request, token=token)

    # Assert
    assert response.text == "let me thinkthe answer"
