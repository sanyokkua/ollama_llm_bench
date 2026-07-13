"""Proves STORY-027-AC-2 and STORY-027-AC-3 — the LRU cache's hit/miss and
eviction behaviour (§6.5)."""

from ollama_llm_bench.backend.embedding._internal.cache import _EmbeddingCache

_PROVIDER = "p1"
_MODEL = "model-a"


def test_cache_hit_returns_cached_vector() -> None:
    """Proves: STORY-027-AC-2

    A key stored via put() is returned unchanged by a subsequent get() for
    the same (provider_id, model_name, normalised_text) key.
    """
    cache = _EmbeddingCache(max_entries=8)
    vector = (1.0, 2.0, 3.0)
    cache.put(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="hello", vector=vector)

    result = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="hello")

    assert result == vector


def test_cache_miss_returns_none() -> None:
    """Proves: STORY-027-AC-2

    A key never stored is a cache miss, returned as None.
    """
    cache = _EmbeddingCache(max_entries=8)

    result = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="unseen")

    assert result is None


def test_lru_evicts_least_recently_used_on_overflow() -> None:
    """Proves: STORY-027-AC-3

    Given a bound of N, storing N + 1 distinct keys in access order evicts
    the least-recently-used entry: a subsequent request for the evicted key
    is a miss while a request for a still-cached key is a hit.
    """
    max_entries = 3
    cache = _EmbeddingCache(max_entries=max_entries)
    for index in range(max_entries):
        cache.put(
            provider_id=_PROVIDER,
            model_name=_MODEL,
            normalised_text=f"text-{index}",
            vector=(float(index),),
        )

    cache.put(
        provider_id=_PROVIDER, model_name=_MODEL, normalised_text="text-overflow", vector=(9.0,)
    )

    evicted = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="text-0")
    still_cached = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="text-1")
    newest = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="text-overflow")

    assert evicted is None
    assert still_cached == (1.0,)
    assert newest == (9.0,)


def test_lru_get_refreshes_recency_and_protects_from_eviction() -> None:
    """Proves: STORY-027-AC-3

    Re-reading an existing key marks it most-recently-used, so the next
    overflow evicts a different, truly least-recently-used entry instead.
    """
    max_entries = 2
    cache = _EmbeddingCache(max_entries=max_entries)
    cache.put(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="a", vector=(1.0,))
    cache.put(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="b", vector=(2.0,))

    cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="a")  # refresh "a"
    cache.put(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="c", vector=(3.0,))

    evicted_b = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="b")
    kept_a = cache.get(provider_id=_PROVIDER, model_name=_MODEL, normalised_text="a")

    assert evicted_b is None
    assert kept_a == (1.0,)
