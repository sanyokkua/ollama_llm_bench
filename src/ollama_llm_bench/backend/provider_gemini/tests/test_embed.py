"""Tests proving STORY-020-AC-7: ``embed`` returns a vector, and translates
SDK failures per §6.10.

Source of truth: ``docs/stories/story-020-gemini-provider-adapter.md``;
``docs/v3_specification/11_Services_and_Algorithms/02_LLM_CLIENT_PROTOCOL.md``
§6.7.
"""

from collections.abc import Callable

import pytest
from pytest_httpserver import HTTPServer

from ollama_llm_bench.backend.errors import ProviderServerError
from ollama_llm_bench.backend.provider_gemini._internal.client_impl import GeminiClient
from ollama_llm_bench.backend.provider_gemini.models import GeminiClientSettings

_EMBED_PATH = "/v1beta/models/embed-test-model:batchEmbedContents"
_CANNED_VECTOR = (0.1, 0.2, 0.3, 0.4)


def test_embed_returns_vector(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-7

    Given a ``GEMINI`` client embeds a text against a fake embeddings
    endpoint, when ``embed(text)`` is called, then it returns a
    ``tuple[float, ...]`` of the endpoint's dimensionality.
    """
    # Arrange
    httpserver.expect_request(_EMBED_PATH, method="POST").respond_with_json(
        {"embeddings": [{"values": list(_CANNED_VECTOR)}]}
    )
    client = make_client(settings=GeminiClientSettings(embedding_model="embed-test-model"))

    # Act
    vector = client.embed("hello world")

    # Assert
    assert vector == _CANNED_VECTOR


def test_embed_translates_sdk_error(
    httpserver: HTTPServer, make_client: Callable[..., GeminiClient]
) -> None:
    """Proves: STORY-020-AC-7

    Given the embeddings call raises the SDK's error, ``embed`` raises
    ``ProviderError`` (here, its ``ProviderServerError`` leaf for a 5xx)
    with a redacted message.
    """
    # Arrange
    httpserver.expect_request(_EMBED_PATH, method="POST").respond_with_json(
        {"error": {"code": 500, "message": "boom"}}, status=500
    )
    client = make_client(settings=GeminiClientSettings(embedding_model="embed-test-model"))

    # Act / Assert
    with pytest.raises(ProviderServerError):
        client.embed("hello world")
