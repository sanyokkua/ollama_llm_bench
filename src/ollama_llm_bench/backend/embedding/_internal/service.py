"""The concrete EmbeddingService: normalise -> cache -> provider call -> cosine (§6)."""

import structlog

from ollama_llm_bench.backend.domain import CosineScore, CosineThreshold, ModelName, ProviderId
from ollama_llm_bench.backend.embedding._internal.cache import _EmbeddingCache
from ollama_llm_bench.backend.embedding._internal.math import compute_cosine
from ollama_llm_bench.backend.embedding._internal.parameters import _EmbeddingParameters
from ollama_llm_bench.backend.errors import AppError
from ollama_llm_bench.backend.provider_registry import LLMClient

log = structlog.get_logger(__name__)

_EMPTY_VECTOR: tuple[float, ...] = ()


class _EmbeddingServiceImpl:
    """Synchronous, single-owner (worker-thread-only per §9), lock-free.

    Bound at construction to one fixed ``(provider_id, model_name)`` embedding
    target and one ``LLMClient`` (§6.1) — the embedding model never changes
    mid-instance.
    """

    def __init__(
        self,
        *,
        client: LLMClient,
        provider_id: ProviderId,
        model_name: ModelName,
        parameters: _EmbeddingParameters,
    ) -> None:
        self._client = client
        self._provider_id = provider_id
        self._model_name = model_name
        self._parameters = parameters
        self._cache = _EmbeddingCache(max_entries=parameters.cache_max_entries)
        self._consecutive_failures = 0
        self._short_circuited = False

    def embed(self, text: str) -> tuple[float, ...]:
        """Normalise, check the cache, call the provider on a miss (§6.2, §8, DD-70)."""
        normalised_text = text.strip()
        cached = self._cache.get(
            provider_id=self._provider_id,
            model_name=self._model_name,
            normalised_text=normalised_text,
        )
        if cached is not None:
            return cached
        if self._short_circuited:
            return _EMPTY_VECTOR
        return self._call_provider(normalised_text)

    def cosine(self, text_a: str, text_b: str) -> CosineScore:
        """Embed both texts and compute the clamped whole-text cosine (§6.3, §6.4)."""
        vector_a = self.embed(text_a)
        vector_b = self.embed(text_b)
        return compute_cosine(vector_a, vector_b)

    def cosine_threshold(self) -> CosineThreshold:
        """Return the run-frozen ``eval.cosine_threshold`` value (§6.4)."""
        return self._parameters.cosine_threshold

    def is_short_circuited(self) -> bool:
        """Whether DD-70's consecutive-failure short-circuit has tripped (§7)."""
        return self._short_circuited

    def _call_provider(self, normalised_text: str) -> tuple[float, ...]:
        """Call the provider for one normalised text, tracking DD-70 failures (§8)."""
        try:
            vector = self._client.embed(normalised_text)
        except AppError as exc:
            log.warning(
                "embedding_call_failed",
                provider_id=self._provider_id,
                model_name=self._model_name,
                error_type=type(exc).__name__,
            )
            return self._record_failure()
        if not vector or not _has_nonzero_component(vector):
            log.warning(
                "embedding_call_returned_degenerate_vector",
                provider_id=self._provider_id,
                model_name=self._model_name,
            )
            return self._record_failure()
        self._consecutive_failures = 0
        self._cache.put(
            provider_id=self._provider_id,
            model_name=self._model_name,
            normalised_text=normalised_text,
            vector=vector,
        )
        return vector

    def _record_failure(self) -> tuple[float, ...]:
        """Bump the consecutive-failure counter and maybe trip DD-70's short-circuit."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._parameters.consecutive_failures_to_skip:
            if not self._short_circuited:
                log.warning(
                    "embedding_short_circuited",
                    provider_id=self._provider_id,
                    model_name=self._model_name,
                    consecutive_failures=self._consecutive_failures,
                )
            self._short_circuited = True
        return _EMPTY_VECTOR


def _has_nonzero_component(vector: tuple[float, ...]) -> bool:
    """Whether a vector has at least one non-zero component (a malformed/empty-embedding guard)."""
    return any(component != 0.0 for component in vector)
