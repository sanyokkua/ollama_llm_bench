"""Mutable per-provider bookkeeping — never crosses the module boundary (§6.1)."""

from dataclasses import dataclass

from ollama_llm_bench.backend.circuit_breaker.models import CircuitState


@dataclass(slots=True)
class _ProviderRecord:
    """One provider's breaker bookkeeping (§6.1).

    ``cooldown_started_ms`` is set only while ``TRIPPED`` (and carried forward
    into ``PROBING`` until a fresh trip resets it); it is ``None`` while
    ``CLOSED``. ``probe_slot_claimed`` tracks whether the one post-cooldown
    probe task has already been admitted (§6.5) and is reset on every fresh
    ``TRIPPED -> PROBING`` transition.
    """

    state: CircuitState
    consecutive_failures: int
    cooldown_started_ms: int | None
    probe_slot_claimed: bool
