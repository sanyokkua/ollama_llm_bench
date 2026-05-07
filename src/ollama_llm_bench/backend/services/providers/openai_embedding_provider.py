"""OpenAI-compatible embedding provider implementing EmbeddingProviderApi."""

import logging

import openai

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when the embedding API call fails."""


class OpenAIEmbeddingProvider:
    """Embedding provider that calls the OpenAI-compatible /v1/embeddings endpoint."""

    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        """Initialize the provider and construct the underlying openai client.

        Args:
            base_url: Base URL of the OpenAI-compatible endpoint (e.g. ``"http://localhost:11434/v1"``).
            api_key: API key; use any non-empty string for local servers that ignore it.
            model: Embedding model identifier to use for all encode calls.
        """
        self._client = openai.OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def abort(self) -> None:
        """Close the underlying HTTP client to cancel any in-flight request."""
        try:
            self._client.close()
        except Exception:
            logger.debug("openai_embedding_abort_error")

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode a list of texts into embedding vectors.

        Args:
            texts: Input strings to embed; may be empty.

        Returns:
            List of embedding vectors, one per input text; empty list when texts is empty.

        Raises:
            EmbeddingError: If the embedding API call fails.
        """
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except openai.OpenAIError as exc:
            logger.exception("embedding_encode_error")
            raise EmbeddingError(str(exc)) from exc
        return [item.embedding for item in response.data]
