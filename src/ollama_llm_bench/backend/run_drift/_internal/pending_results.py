"""Count a run's still-retryable results by provider or by target (spec §3, §6.1-§6.4).

``resumable_results`` is already pre-filtered by the caller to rows in ``PENDING``
or a retryable terminal-failure status (`ResultsStore.list_resumable_results`), so
no ``ResultStatus`` branching happens here — this module only filters by identity.
"""

from ollama_llm_bench.backend.domain import BenchmarkResult, ModelNameStr, ProviderIdStr

__all__: list[str] = ["count_by_provider", "count_by_target"]


def count_by_provider(results: tuple[BenchmarkResult, ...], provider_id: ProviderIdStr) -> int:
    """Count retryable results whose ``provider_id`` matches (spec §6.1)."""
    return sum(1 for result in results if result.provider_id == provider_id)


def count_by_target(
    results: tuple[BenchmarkResult, ...],
    provider_id: ProviderIdStr,
    model_name: ModelNameStr,
) -> int:
    """Count retryable results matching a ``(provider_id, model_name)`` pair (spec §6.2-§6.4)."""
    return sum(
        1
        for result in results
        if result.provider_id == provider_id and result.model_name == model_name
    )
