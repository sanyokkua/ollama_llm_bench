"""Tests proving STORY-020-AC-2: per-chunk usage maps to ``ChatChunk.delta_tokens``.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.5a.
"""

from collections.abc import Callable
import json

from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini.tests.conftest import FakeClock, make_chat_request

_STREAM_PATH = "/v1beta/models/gemini-test-model:streamGenerateContent"
_EXPECTED_DELTA_TOKENS = 2
_EXPECTED_CHUNK_COUNT = 2


def _chunk(text: str, candidates_token_count: int | None) -> str:
    payload: dict[str, object] = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "index": 0}],
    }
    if candidates_token_count is not None:
        payload["usageMetadata"] = {
            "promptTokenCount": 5,
            "candidatesTokenCount": candidates_token_count,
        }
    return f"data: {json.dumps(payload)}\n\n"


def test_per_chunk_usage_maps_to_delta_tokens(
    httpserver: HTTPServer, fake_clock: FakeClock, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-2

    Given a fake Gemini stream whose first chunk carries
    ``usageMetadata.candidatesTokenCount`` and whose second chunk exposes no
    usage metadata at all, when ``chat_stream`` yields chunks, then the
    first yielded ``ChatChunk.delta_tokens`` equals that chunk's own count,
    and the second yielded ``ChatChunk.delta_tokens`` is ``None``.
    """
    # Arrange
    body = _chunk("first ", candidates_token_count=_EXPECTED_DELTA_TOKENS) + _chunk(
        "second", candidates_token_count=None
    )
    httpserver.expect_request(_STREAM_PATH, method="POST").respond_with_data(
        body, content_type="text/event-stream"
    )
    client = make_client()
    request = make_chat_request()
    token = CancellationToken(clock=fake_clock)

    # Act
    stream = client.chat_stream(request, token=token)
    chunks = list(stream)

    # Assert
    assert len(chunks) == _EXPECTED_CHUNK_COUNT
    assert chunks[0].delta_tokens == _EXPECTED_DELTA_TOKENS
    assert chunks[1].delta_tokens is None
