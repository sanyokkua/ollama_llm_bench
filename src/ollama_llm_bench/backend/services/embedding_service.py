"""Embedding service with LRU caching wrapping an EmbeddingProviderApi."""

import logging
from collections import OrderedDict

from ollama_llm_bench.backend.core.interfaces import EmbeddingProviderApi

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Caching wrapper around EmbeddingProviderApi that avoids redundant API calls.

    Implements a least-recently-used (LRU) cache keyed on the input text string.
    Cache hits are promoted to the most-recent position; when the cache is full
    the oldest entry is evicted before inserting a new one.
    """

    def __init__(self, *, provider: EmbeddingProviderApi, cache_size: int = 512) -> None:
        """Initialize the service with an embedding provider and optional cache limit.

        Args:
            provider: Embedding provider used to compute vectors for cache misses.
            cache_size: Maximum number of text→embedding pairs held in memory; must
                be a positive integer. Defaults to 512.
        """
        self._provider = provider
        self._cache_size = cache_size
        self._cache: OrderedDict[str, list[float]] = OrderedDict()

    def encode_single(self, text: str) -> list[float]:
        """Return the embedding vector for a single text string.

        Retrieves the result from the in-memory LRU cache when available; otherwise
        delegates to the provider and caches the result before returning.

        Args:
            text: Input string to embed; may be empty.

        Returns:
            Embedding vector as a list of floats.
        """
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]

        embeddings = self._provider.encode([text])
        embedding = embeddings[0]
        self._store(text, embedding)
        return embedding

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of text strings.

        Texts already present in the cache are served directly. Uncached texts are
        deduplicated, sent to the provider in a single batched call, stored in the
        cache, and then assembled into the result list in the original input order.

        Args:
            texts: Input strings to embed; duplicates are deduplicated before the
                provider call but results are returned in the original order.

        Returns:
            List of embedding vectors in the same order as the input list; empty if
            ``texts`` is empty.
        """
        if not texts:
            return []

        # Collect uncached texts in first-occurrence order (no duplicates).
        seen: set[str] = set()
        uncached_texts: list[str] = []
        for text in texts:
            if text not in self._cache and text not in seen:
                uncached_texts.append(text)
                seen.add(text)

        if uncached_texts:
            new_embeddings = self._provider.encode(uncached_texts)
            new_results: dict[str, list[float]] = dict(zip(uncached_texts, new_embeddings, strict=True))
            for text, embedding in new_results.items():
                self._store(text, embedding)

        return [self._cache[t] for t in texts]

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for a list of text strings.

        Satisfies the EmbeddingProviderApi Protocol. Delegates to encode_batch,
        which applies LRU caching and deduplication before calling the provider.

        Args:
            texts: Input strings to embed.

        Returns:
            List of embedding vectors in the same order as the input; empty if
            ``texts`` is empty.
        """
        return self.encode_batch(texts)

    def _store(self, text: str, embedding: list[float]) -> None:
        if text in self._cache:
            self._cache.move_to_end(text)
        else:
            if len(self._cache) >= self._cache_size:
                self._cache.popitem(last=False)  # evict oldest (LRU)
            self._cache[text] = embedding
