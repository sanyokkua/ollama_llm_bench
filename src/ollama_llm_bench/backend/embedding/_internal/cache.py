"""The in-memory, bounded, single-accessor LRU embedding cache (§6.5, §9)."""

from collections import OrderedDict

from ollama_llm_bench.backend.domain import ModelName, ProviderId

_CacheKey = tuple[ProviderId, ModelName, str]


class _EmbeddingCache:
    """A bounded least-recently-used cache of embedding vectors (§6.5).

    Keyed on ``(provider_id, model_name, normalised_text)``. Bounded by
    ``max_entries``; the least-recently-used entry is evicted on overflow.
    Scoped to the lifetime of one owning ``EmbeddingService`` instance — never
    persisted, never shared across runs (§6.5, §9).

    No locking: because execution is strictly serial app-wide (D-R-16), the
    embedding service — and therefore this cache — is touched by at most one
    thread at a time (§9).

    Args:
        max_entries: The maximum number of cached entries before the
            least-recently-used entry is evicted; must be at least 1.
    """

    def __init__(self, *, max_entries: int) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[_CacheKey, tuple[float, ...]] = OrderedDict()

    def get(
        self, *, provider_id: ProviderId, model_name: ModelName, normalised_text: str
    ) -> tuple[float, ...] | None:
        """Return the cached vector for this key, marking it most-recently-used.

        Args:
            provider_id: The embedding provider identity component of the key.
            model_name: The embedding model name component of the key.
            normalised_text: The whitespace-trimmed text component of the key.

        Returns:
            The cached vector, or ``None`` on a cache miss.
        """
        key: _CacheKey = (provider_id, model_name, normalised_text)
        if key not in self._entries:
            return None
        self._entries.move_to_end(key)
        return self._entries[key]

    def put(
        self,
        *,
        provider_id: ProviderId,
        model_name: ModelName,
        normalised_text: str,
        vector: tuple[float, ...],
    ) -> None:
        """Store a vector under this key, evicting the LRU entry on overflow.

        Args:
            provider_id: The embedding provider identity component of the key.
            model_name: The embedding model name component of the key.
            normalised_text: The whitespace-trimmed text component of the key.
            vector: The embedding vector to cache.
        """
        key: _CacheKey = (provider_id, model_name, normalised_text)
        self._entries[key] = vector
        self._entries.move_to_end(key)
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
