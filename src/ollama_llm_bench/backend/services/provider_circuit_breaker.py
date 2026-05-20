"""Per-provider stuck-detection circuit breaker with sliding-window multi-model logic."""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

HEALTHY: Literal["healthy"] = "healthy"
TRIPPED: Literal["tripped"] = "tripped"
PROBING: Literal["probing"] = "probing"

type ProviderState = Literal["healthy", "tripped", "probing"]

_DEFAULT_FAILURE_THRESHOLD: int = 3
_DEFAULT_WINDOW_S: float = 600.0
_DEFAULT_PROBE_INTERVAL_S: float = 60.0


@dataclass(slots=True, kw_only=True)
class _FailureRecord:
    timestamp: float
    model_name: str
    reason: str


@dataclass(slots=True, kw_only=True)
class _ProviderState:
    failures: deque[_FailureRecord] = field(default_factory=deque)
    state: str = HEALTHY
    last_failure_time: float = 0.0
    trip_logged: bool = False


class ProviderCircuitBreaker:
    """Multi-provider sliding-window circuit breaker.

    Trips a provider after ``failure_threshold`` failures spanning at least 2
    distinct models within a ``window_s`` second window.  Once tripped, tasks
    for that provider are skipped until either:
    - ``probe_interval_s`` seconds pass, at which point one probe is allowed
      (``should_dispatch`` returns True while state is "probing").
    - ``record_success`` is called, which fully resets the circuit.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        window_s: float = _DEFAULT_WINDOW_S,
        probe_interval_s: float = _DEFAULT_PROBE_INTERVAL_S,
    ) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._window_s = max(0.001, window_s)
        self._probe_interval_s = max(0.001, probe_interval_s)
        self._providers: dict[str, _ProviderState] = {}
        self._lock = threading.Lock()

    def _get_or_create(self, provider_id: str) -> _ProviderState:
        """Return or create the per-provider state record (caller holds lock)."""
        if provider_id not in self._providers:
            self._providers[provider_id] = _ProviderState()
        return self._providers[provider_id]

    def _purge_old(self, ps: _ProviderState) -> None:
        """Remove failure records outside the sliding window (caller holds lock)."""
        cutoff = time.monotonic() - self._window_s
        while ps.failures and ps.failures[0].timestamp < cutoff:
            ps.failures.popleft()

    def record_failure(self, provider_id: str, *, model_name: str, reason: str) -> None:
        """Record an inference failure for a provider.

        Trips the circuit when at least ``failure_threshold`` failures from at
        least 2 distinct models accumulate within the sliding window.

        Args:
            provider_id: Provider identifier.
            model_name: Model that failed.
            reason: Short description of the failure cause.
        """
        with self._lock:
            ps = self._get_or_create(provider_id)
            now = time.monotonic()
            ps.failures.append(_FailureRecord(timestamp=now, model_name=model_name, reason=reason))
            ps.last_failure_time = now
            self._purge_old(ps)

            if ps.state == HEALTHY:
                distinct_models = {r.model_name for r in ps.failures}
                if len(ps.failures) >= self._failure_threshold and len(distinct_models) >= 2:
                    ps.state = TRIPPED
                    if not ps.trip_logged:
                        ps.trip_logged = True
                        logger.warning(
                            "provider_circuit_tripped",
                            extra={
                                "provider_id": provider_id,
                                "failure_count": len(ps.failures),
                                "distinct_models": len(distinct_models),
                                "last_reason": reason,
                            },
                        )

    def record_success(self, provider_id: str) -> None:
        """Record a successful inference, resetting the circuit to healthy.

        Args:
            provider_id: Provider identifier.
        """
        with self._lock:
            ps = self._get_or_create(provider_id)
            prev = ps.state
            ps.failures.clear()
            ps.state = HEALTHY
            ps.last_failure_time = 0.0
            ps.trip_logged = False
            if prev != HEALTHY:
                logger.info(
                    "provider_circuit_recovered",
                    extra={"provider_id": provider_id, "prev_state": prev},
                )

    def state(self, provider_id: str) -> ProviderState:
        """Return the current circuit state for a provider.

        When the circuit is tripped and ``probe_interval_s`` seconds have
        elapsed since the last failure, returns ``"probing"`` so the caller
        can dispatch a single probe attempt.  The internal stored state
        remains ``"tripped"``; the transition is time-derived.

        Args:
            provider_id: Provider identifier.

        Returns:
            ``"healthy"``, ``"tripped"``, or ``"probing"``.
        """
        with self._lock:
            ps = self._get_or_create(provider_id)
            if ps.state == TRIPPED:
                elapsed = time.monotonic() - ps.last_failure_time
                if elapsed >= self._probe_interval_s:
                    logger.info(
                        "provider_circuit_probe_allowed",
                        extra={"provider_id": provider_id, "elapsed_s": round(elapsed, 1)},
                    )
                    return PROBING
                return TRIPPED
            return HEALTHY

    def should_dispatch(self, provider_id: str) -> bool:
        """Return True when a task may be dispatched to this provider.

        Args:
            provider_id: Provider identifier.

        Returns:
            True for ``"healthy"`` or ``"probing"``, False for ``"tripped"``.
        """
        return self.state(provider_id) != TRIPPED

    def reset(self, provider_id: str) -> None:
        """Fully reset the circuit state for a provider (e.g., after Resume).

        Args:
            provider_id: Provider identifier.
        """
        self.record_success(provider_id)
