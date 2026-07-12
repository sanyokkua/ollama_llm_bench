"""A configurable fake ProviderCircuitBreaker for downstream module tests."""

from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.domain import ProviderId

__all__: list[str] = ["FakeProviderCircuitBreaker"]


class FakeProviderCircuitBreaker:
    """An in-memory fake with externally settable per-provider state, plus
    call logs for downstream-module test assertions. No real state-machine
    logic behind it — set the values a test scenario needs directly.
    """

    def __init__(self) -> None:
        self._states: dict[ProviderId, CircuitState] = {}
        self._should_skip: dict[ProviderId, bool] = {}
        self._cooldown_remaining: dict[ProviderId, int | None] = {}
        self.recorded_failures: list[ProviderId] = []
        self.recorded_successes: list[ProviderId] = []

    def state(self, provider_id: ProviderId) -> CircuitState:
        """Return whatever ``set_state`` configured, or CLOSED by default."""
        return self._states.get(provider_id, CircuitState.CLOSED)

    def record_failure(self, provider_id: ProviderId) -> None:
        """Record the call for later assertion; no state machine behind it."""
        self.recorded_failures.append(provider_id)

    def record_success(self, provider_id: ProviderId) -> None:
        """Record the call for later assertion; no state machine behind it."""
        self.recorded_successes.append(provider_id)

    def should_skip(self, provider_id: ProviderId) -> bool:
        """Return whatever ``set_should_skip`` configured, or False by default."""
        return self._should_skip.get(provider_id, False)

    def cooldown_remaining_seconds(self, provider_id: ProviderId) -> int | None:
        """Return whatever ``set_cooldown_remaining_seconds`` configured, or None."""
        return self._cooldown_remaining.get(provider_id)

    def set_state(self, provider_id: ProviderId, state: CircuitState) -> None:
        """Test helper: force a provider's ``state()`` return value."""
        self._states[provider_id] = state

    def set_should_skip(self, provider_id: ProviderId, *, should_skip: bool) -> None:
        """Test helper: force a provider's ``should_skip()`` return value."""
        self._should_skip[provider_id] = should_skip

    def set_cooldown_remaining_seconds(
        self, provider_id: ProviderId, remaining_seconds: int | None
    ) -> None:
        """Test helper: force a provider's ``cooldown_remaining_seconds()`` return value."""
        self._cooldown_remaining[provider_id] = remaining_seconds
