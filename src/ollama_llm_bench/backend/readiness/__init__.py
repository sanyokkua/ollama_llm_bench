"""Readiness probe + aggregator.

Aggregates per-provider health probes and the embedding-model reachability into
one application-readiness snapshot (``READY`` / ``DEGRADED`` / ``NOT_READY`` /
``CHECKING``). Never raises, never runs an automatic billable ``embed()`` call, and
never overlaps a benchmark run (the single-inference gate).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§12; ``docs/v3_specification/11_Services_and_Algorithms/09_READINESS_PROBE.md``.
"""

from ollama_llm_bench.backend.readiness.api import (
    ReadinessEmbeddingSelector,
    ReadinessProviderRegistry,
    ReadinessService,
    make_readiness_service,
)

__all__: list[str] = [
    "ReadinessEmbeddingSelector",
    "ReadinessProviderRegistry",
    "ReadinessService",
    "make_readiness_service",
]
