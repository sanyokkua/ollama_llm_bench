"""Mutable per-provider bookkeeping — never crosses the module boundary (§6.1)."""

from dataclasses import dataclass

from ollama_llm_bench.backend.circuit_breaker.models import CircuitState


@dataclass(slots=True)
class _ProviderRecord:
    """One provider's breaker bookkeeping (§6.1).

    ``cooldown_started_ms`` is set only while ``TRIPPED`` (and carried forward
    into ``PROBING`` until a fresh trip resets it); it is ``None`` while
    ``CLOSED``. There is no probe-slot field: ``PROBING`` admits no benchmark
    task (DD-71, ADR-0013) — liveness is decided by the pipeline's dedicated
    lightweight probe (``_internal.provider_probe.run_provider_probe``), never
    by an admission bit on this record.
    """

    state: CircuitState
    consecutive_failures: int
    cooldown_started_ms: int | None
