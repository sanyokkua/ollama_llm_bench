"""Unit tests for OpenAIEmbeddingProvider."""

from unittest.mock import MagicMock

import openai
import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.services.providers.openai_embedding_provider import (
    EmbeddingError,
    OpenAIEmbeddingProvider,
)

_BASE_URL = "http://localhost:11434/v1"
_API_KEY = "test-key"
_MODEL = "bge-m3"


def _make_provider(
    mocker: MockerFixture,
    *,
    base_url: str = _BASE_URL,
    api_key: str = _API_KEY,
    model: str = _MODEL,
) -> tuple[OpenAIEmbeddingProvider, MagicMock]:
    """Create an OpenAIEmbeddingProvider with a patched openai.OpenAI client.

    Returns:
        Tuple of (provider instance, mock client instance).
    """
    mock_cls = mocker.patch("ollama_llm_bench.backend.services.providers.openai_embedding_provider.openai.OpenAI")
    mock_client = mock_cls.return_value
    provider = OpenAIEmbeddingProvider(base_url=base_url, api_key=api_key, model=model)
    return provider, mock_client


def _make_embedding_response(mocker: MockerFixture, vectors: list[list[float]]) -> object:
    """Create a mock embeddings API response with the given vectors.

    Args:
        mocker: pytest-mock fixture.
        vectors: List of float vectors to return as embedding data.

    Returns:
        Mock object whose .data list contains items with .embedding attributes.
    """
    mock_response = mocker.Mock()
    mock_items = []
    for vec in vectors:
        item = mocker.Mock()
        item.embedding = vec
        mock_items.append(item)
    mock_response.data = mock_items
    return mock_response


class TestOpenAIEmbeddingProviderEncode:
    """Tests for encode."""

    def test_encode_non_empty_texts_returns_list_of_vectors(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, vectors)

        # Act
        result = provider.encode(["text1", "text2"])

        # Assert
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    def test_encode_returns_one_vector_per_input_text(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, vectors)

        # Act
        result = provider.encode(["a", "b", "c"])

        # Assert
        assert len(result) == 3

    def test_encode_returns_float_vectors(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        vectors = [[0.1, 0.2, 0.3]]
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, vectors)

        # Act
        result = provider.encode(["single text"])

        # Assert
        assert isinstance(result[0], list)
        assert all(isinstance(v, float) for v in result[0])

    def test_encode_passes_texts_to_api(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, [[0.1]])

        # Act
        provider.encode(["hello world"])

        # Assert — input texts forwarded to embeddings API
        call_kwargs = mock_client.embeddings.create.call_args.kwargs
        assert call_kwargs["input"] == ["hello world"]

    def test_encode_passes_model_to_api(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker, model="nomic-embed-text")
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, [[0.1]])

        # Act
        provider.encode(["text"])

        # Assert — model injected at construction time is forwarded
        call_kwargs = mock_client.embeddings.create.call_args.kwargs
        assert call_kwargs["model"] == "nomic-embed-text"

    def test_encode_empty_list_returns_empty_list(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, _ = _make_provider(mocker)

        # Act
        result = provider.encode([])

        # Assert
        assert result == []

    def test_encode_empty_list_does_not_call_api(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)

        # Act
        provider.encode([])

        # Assert — early-return path skips the network call entirely
        mock_client.embeddings.create.assert_not_called()

    def test_encode_on_openai_error_raises_embedding_error(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.embeddings.create.side_effect = openai.OpenAIError("embedding service unavailable")

        # Act / Assert
        with pytest.raises(EmbeddingError):
            provider.encode(["text"])

    def test_encode_on_openai_error_wraps_original_exception(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        original = openai.OpenAIError("quota exceeded")
        mock_client.embeddings.create.side_effect = original
        # Act
        with pytest.raises(EmbeddingError) as exc_info:
            provider.encode(["text"])

        # Assert — EmbeddingError chains the original exception
        assert exc_info.value.__cause__ is original

    def test_encode_on_openai_error_message_preserved_in_embedding_error(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        mock_client.embeddings.create.side_effect = openai.OpenAIError("rate limit exceeded")

        # Act
        with pytest.raises(EmbeddingError) as exc_info:
            provider.encode(["text"])

        # Assert
        assert "rate limit exceeded" in str(exc_info.value)

    def test_encode_single_text_returns_single_vector(self, mocker: MockerFixture) -> None:
        # Arrange
        provider, mock_client = _make_provider(mocker)
        vectors = [[1.0, 2.0, 3.0]]
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, vectors)

        # Act
        result = provider.encode(["only one"])

        # Assert
        assert len(result) == 1
        assert result[0] == [1.0, 2.0, 3.0]

    def test_encode_preserves_vector_order(self, mocker: MockerFixture) -> None:
        # Arrange — vectors have distinct first elements so order is verifiable
        provider, mock_client = _make_provider(mocker)
        vectors = [[1.0], [2.0], [3.0]]
        mock_client.embeddings.create.return_value = _make_embedding_response(mocker, vectors)

        # Act
        result = provider.encode(["first", "second", "third"])

        # Assert
        assert result[0][0] == 1.0
        assert result[1][0] == 2.0
        assert result[2][0] == 3.0
