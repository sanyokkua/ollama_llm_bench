"""The concrete ProviderCircuitBreaker: the three-state machine of §6.2-§6.5."""

import math

from ollama_llm_bench.backend.circuit_breaker._internal.parameters import _BreakerParameters
from ollama_llm_bench.backend.circuit_breaker._internal.state import _ProviderRecord
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.domain import ProviderId
from ollama_llm_bench.backend.infra import Clock

_MS_PER_SECOND = 1000


class _ProviderCircuitBreakerImpl:
    """Synchronous, single-owner (dispatcher-thread-only per §9), lock-free."""

    def __init__(self, *, parameters: _BreakerParameters, clock: Clock) -> None:
        self._parameters = parameters
        self._clock = clock
        self._providers: dict[ProviderId, _ProviderRecord] = {}

    def state(self, provider_id: ProviderId) -> CircuitState:
        """Return the current breaker state for a provider (§6.2)."""
        if not self._parameters.enabled:
            return CircuitState.CLOSED
        record = self._get_or_create_record(provider_id)
        self._maybe_transition_to_probing(record)
        return record.state

    def record_failure(self, provider_id: ProviderId) -> None:
        """Record a provider failure; may trip the breaker (§6.4)."""
        if not self._parameters.enabled:
            return
        record = self._get_or_create_record(provider_id)
        if record.state is CircuitState.CLOSED:
            record.consecutive_failures += 1
            if record.consecutive_failures >= self._parameters.failure_threshold:
                self._trip(record)
        elif record.state is CircuitState.PROBING:
            # The dedicated lightweight liveness probe failed — re-trip for a fresh cooldown window.
            self._trip(record)
        # A record_failure while TRIPPED is skipped-task bookkeeping; it neither
        # extends nor shortens the cooldown.

    def record_success(self, provider_id: ProviderId) -> None:
        """Record a provider success; closes a probing breaker (§6.4)."""
        if not self._parameters.enabled:
            return
        record = self._get_or_create_record(provider_id)
        if record.state is CircuitState.PROBING:
            record.state = CircuitState.CLOSED
            record.consecutive_failures = 0
            record.cooldown_started_ms = None
        elif record.state is CircuitState.CLOSED:
            record.consecutive_failures = 0
        # A record_success while TRIPPED cannot occur in correct pipeline usage
        # (a tripped provider is skipped); accepted as a safe no-op.

    def should_skip(self, provider_id: ProviderId) -> bool:
        """Whether the pipeline should skip this provider right now (§6.2, §6.5).

        Returns exactly what ``state()`` implies, and is idempotent: repeated
        calls with no intervening ``record_success``/``record_failure``
        return the same value. Like ``state()`` and
        ``cooldown_remaining_seconds``, it evaluates the lazy TRIPPED ->
        PROBING transition, so it is dispatcher-thread-only. ``PROBING``
        always returns ``True``: it admits no benchmark task (DD-71,
        ADR-0013). Liveness is decided elsewhere, by the pipeline's dedicated
        ``run_provider_probe`` call issued before each row.
        """
        if not self._parameters.enabled:
            return False
        record = self._get_or_create_record(provider_id)
        self._maybe_transition_to_probing(record)
        return record.state is not CircuitState.CLOSED

    def cooldown_remaining_seconds(self, provider_id: ProviderId) -> int | None:
        """Seconds left in a tripped provider's cooldown, or ``None`` (§6.5)."""
        if not self._parameters.enabled:
            return None
        record = self._get_or_create_record(provider_id)
        self._maybe_transition_to_probing(record)
        if record.state is not CircuitState.TRIPPED or record.cooldown_started_ms is None:
            return None
        cooldown_ms = self._parameters.cooldown_seconds * _MS_PER_SECOND
        elapsed_ms = self._clock.monotonic_ms() - record.cooldown_started_ms
        remaining_ms = cooldown_ms - elapsed_ms
        return math.ceil(remaining_ms / _MS_PER_SECOND)

    def _trip(self, record: _ProviderRecord) -> None:
        """Move a record to TRIPPED and stamp a fresh cooldown window (§6.4, §6.5)."""
        record.state = CircuitState.TRIPPED
        record.cooldown_started_ms = self._clock.monotonic_ms()

    def _maybe_transition_to_probing(self, record: _ProviderRecord) -> None:
        """Lazily evaluate the TRIPPED -> PROBING move (§6.5).

        Called at the top of every query method; never called from
        ``record_failure``/``record_success`` (the pipeline always queries
        ``should_skip`` before dispatch, so those always observe an
        already-current state, per §6.4's pseudocode).
        """
        if record.state is not CircuitState.TRIPPED or record.cooldown_started_ms is None:
            return
        cooldown_ms = self._parameters.cooldown_seconds * _MS_PER_SECOND
        elapsed_ms = self._clock.monotonic_ms() - record.cooldown_started_ms
        if elapsed_ms >= cooldown_ms:
            record.state = CircuitState.PROBING

    def _get_or_create_record(self, provider_id: ProviderId) -> _ProviderRecord:
        if provider_id not in self._providers:
            self._providers[provider_id] = _ProviderRecord(
                state=CircuitState.CLOSED,
                consecutive_failures=0,
                cooldown_started_ms=None,
            )
        return self._providers[provider_id]
