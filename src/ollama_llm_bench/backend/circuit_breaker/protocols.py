"""ProviderCircuitBreaker — this module's swap point (08-E §18)."""

from typing import Protocol

from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.domain import ProviderId


class ProviderCircuitBreaker(Protocol):
    """Per-provider failure circuit breaker for the benchmark pipeline (§6.1)."""

    def state(self, provider_id: ProviderId) -> CircuitState:
        """Return the current breaker state for a provider.

        fast-synchronous; never raises. An unseen ``provider_id`` reads as
        implicit ``CLOSED``.
        """
        ...

    def record_failure(self, provider_id: ProviderId) -> None:
        """Record a provider failure; may trip the breaker.

        fast-synchronous; never raises.
        """
        ...

    def record_success(self, provider_id: ProviderId) -> None:
        """Record a provider success; closes a probing breaker.

        fast-synchronous; never raises.
        """
        ...

    def should_skip(self, provider_id: ProviderId) -> bool:
        """Whether the pipeline should skip this provider right now.

        fast-synchronous; never raises. Returns exactly what ``state()``
        implies, and is idempotent: repeated calls with no intervening
        ``record_success``/``record_failure`` return the same value. Like
        ``state()`` and ``cooldown_remaining_seconds``, it evaluates the lazy
        TRIPPED -> PROBING transition, so it is dispatcher-thread-only.
        ``PROBING`` admits no benchmark task and always returns ``True``: the
        provider's liveness is decided by a dedicated lightweight call the
        pipeline issues before each row (DD-71, ADR-0013), never by admitting
        an ordinary task through this method.
        """
        ...

    def cooldown_remaining_seconds(self, provider_id: ProviderId) -> int | None:
        """Seconds left in a tripped provider's cooldown, or ``None``.

        fast-synchronous; never raises.
        """
        ...
