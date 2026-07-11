"""The pure per-batch aggregation fold (§6.5).

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``
§6.5 (Aggregation into the overall verdict).
"""

from ollama_llm_bench.backend.domain import AppReadinessSnapshot, ProviderHealth, ReadinessState

__all__: list[str] = [
    "aggregate",
]


def aggregate(
    health_results: tuple[ProviderHealth, ...], *, embedding_ok: bool
) -> AppReadinessSnapshot:
    """Fold per-provider health and the embedding result into one snapshot.

    A provider counts as healthy purely on ``reachable``, regardless of
    ``discovery_supported`` or ``model_count`` (STORY-016-AC-3): a provider
    with no discovery endpoint (Anthropic-style), one that lists zero
    models, and one whose listing call itself failed are all still healthy
    when reachable.

    Args:
        health_results: One ``ProviderHealth`` per enabled provider probed
            in this batch.
        embedding_ok: Whether the handshake-only embedding probe succeeded.

    Returns:
        The aggregate snapshot per the table in STORY-016-AC-2:
        zero enabled providers, or every enabled provider unreachable,
        yields ``NOT_READY``; every provider reachable with the embedding
        model reachable yields ``READY``; every provider reachable but the
        embedding model unreachable, or only some providers reachable,
        yields ``DEGRADED``.
    """
    enabled_count = len(health_results)
    healthy_count = sum(1 for health in health_results if health.reachable)
    overall = _fold_overall(
        enabled_count=enabled_count, healthy_count=healthy_count, embedding_ok=embedding_ok
    )
    return AppReadinessSnapshot(
        overall=overall, per_provider=health_results, embedding_reachable=embedding_ok
    )


def _fold_overall(*, enabled_count: int, healthy_count: int, embedding_ok: bool) -> ReadinessState:
    """Apply the four-state fold table (`09_READINESS_PROBE.md` §6.5)."""
    if enabled_count == 0 or healthy_count == 0:
        return ReadinessState.NOT_READY
    if healthy_count == enabled_count:
        return ReadinessState.READY if embedding_ok else ReadinessState.DEGRADED
    return ReadinessState.DEGRADED
