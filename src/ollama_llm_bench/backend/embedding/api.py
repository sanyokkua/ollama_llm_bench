"""Public factory for the Embedding Service, plus the embedding-model classifier."""

import icontract

from ollama_llm_bench.backend.domain import BenchmarkRunSettingEntry, ModelName, ProviderId
from ollama_llm_bench.backend.embedding._internal.parameters import (
    REQUIRED_SETTING_KEYS,
    parse_embedding_parameters,
)
from ollama_llm_bench.backend.embedding._internal.service import _EmbeddingServiceImpl
from ollama_llm_bench.backend.embedding.protocols import EmbeddingService
from ollama_llm_bench.backend.model_helpers import is_embedding_model
from ollama_llm_bench.backend.provider_registry import LLMClient

__all__: list[str] = ["is_embedding_model", "make_embedding_service"]


def _has_all_required_keys(snapshot: tuple[BenchmarkRunSettingEntry, ...]) -> bool:
    present = {entry.setting_key for entry in snapshot}
    return REQUIRED_SETTING_KEYS.issubset(present)


@icontract.require(
    _has_all_required_keys,
    "snapshot must carry all three per-run-overridable embedding-service keys — "
    "RunSnapshotBuilder guarantees this; a missing key means the run-creation "
    "use case has a bug, not that the run itself is misconfigured",
)
@icontract.require(lambda client: client is not None, "client must be constructed by the caller")
def make_embedding_service(
    *,
    client: LLMClient,
    provider_id: ProviderId,
    model_name: ModelName,
    snapshot: tuple[BenchmarkRunSettingEntry, ...],
) -> EmbeddingService:
    """Construct the Embedding Service over one fixed embedding target (§2, §6.1, §7).

    One instance is constructed once at the composition root and shared by
    every consumer for the life of the run (§9); it is bound to the single
    ``EMBEDDING``-role ``(provider_id, model_name)`` pair frozen into the run
    snapshot — the embedding model is never re-resolved mid-run (§6.1).

    Args:
        client: The embedding-capable ``LLMClient`` this service routes every
            ``embed`` call through.
        provider_id: The embedding provider identity, used as part of the
            cache key (§6.5).
        model_name: The embedding model name, used as part of the cache key
            (§6.5).
        snapshot: The run's frozen per-run-overridable settings, read once at
            construction: ``eval.cosine_threshold``,
            ``eval.embedding_cache_max_entries``, and
            ``eval.embedding_consecutive_failures_to_skip``.

    Returns:
        A synchronous, in-memory, run-scoped EmbeddingService bound to
        ``(provider_id, model_name)``.
    """
    parameters = parse_embedding_parameters(snapshot)
    return _EmbeddingServiceImpl(
        client=client, provider_id=provider_id, model_name=model_name, parameters=parameters
    )
