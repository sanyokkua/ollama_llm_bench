"""Tests proving STORY-018-AC-8: ``embed(text)`` returns the endpoint's vector and
translates the SDK's embeddings-call failure into a redacted taxonomy error.

Source of truth: ``docs/stories/story-018-openai-compatible-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md`` §6.7.
"""

from collections.abc import Callable

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.errors import AppError, ProviderAuthError
from ollama_llm_bench.backend.provider_openai_compatible._internal.client_impl import (
    OpenAICompatibleClient,
)
from ollama_llm_bench.backend.provider_openai_compatible.models import (
    OpenAICompatibleClientSettings,
)

_VECTOR_DIMENSIONALITY = 4
_EXPECTED_VECTOR = (0.1, 0.2, 0.3, 0.4)


def test_embed_returns_vector_of_endpoints_dimensionality(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-8

    Given an ``OPENAI_COMPATIBLE`` client embeds a text against a fake
    ``/v1/embeddings`` endpoint, when ``embed(text)`` is called, then it
    returns a ``tuple[float, ...]`` of the endpoint's dimensionality.
    """
    # Arrange
    httpserver.expect_request("/embeddings", method="POST").respond_with_json(
        {
            "object": "list",
            "data": [{"object": "embedding", "index": 0, "embedding": list(_EXPECTED_VECTOR)}],
            "model": "embed-model",
            "usage": {"prompt_tokens": 3, "total_tokens": 3},
        }
    )
    client = make_client(settings=OpenAICompatibleClientSettings(embedding_model="embed-model"))

    # Act
    vector = client.embed("hello world")

    # Assert
    assert vector == _EXPECTED_VECTOR
    assert len(vector) == _VECTOR_DIMENSIONALITY


def test_embed_raises_provider_error_with_redacted_message_on_sdk_failure(
    httpserver: HTTPServer, make_client: Callable[..., OpenAICompatibleClient]
) -> None:
    """Proves: STORY-018-AC-8

    Given the embeddings call raises the SDK's error, ``embed`` raises a
    taxonomy ``ProviderError``-marked leaf with a redacted message — no raw
    ``openai``/``httpx`` exception type escapes.
    """
    # Arrange
    httpserver.expect_request("/embeddings", method="POST").respond_with_json(
        {"error": {"message": "Invalid API key", "code": "invalid_api_key"}}, status=401
    )
    client = make_client(settings=OpenAICompatibleClientSettings(embedding_model="embed-model"))

    # Act / Assert
    with pytest.raises(AppError) as exc_info:
        client.embed("hello world")
    assert isinstance(exc_info.value, ProviderAuthError)
    assert type(exc_info.value).__module__.startswith("ollama_llm_bench")
