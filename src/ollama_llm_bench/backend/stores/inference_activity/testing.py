"""A fake ``InferenceActivityStore`` for downstream tests.

Holds the same lease-identity and watchdog semantics as the concrete gate,
against an injected ``Clock`` fake, so a downstream module's tests can
exercise gate-dependent code without wiring the real event bus.
"""

from datetime import datetime
from typing import Final

from ollama_llm_bench.backend.domain import (
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    InferenceActivityState,
)
from ollama_llm_bench.backend.events import (
    SIGNAL_INFERENCE_ACTIVITY_CHANGED,
    EventBus,
    InferenceActivityChangedEvent,
)
from ollama_llm_bench.backend.infra.protocols import Clock

__all__: list[str] = [
    "FakeInferenceActivityStore",
]

_WATCHDOG_TIMEOUT_MS: Final[dict[InferenceActivity, int]] = {
    InferenceActivity.JUDGE_ANALYSIS: 10 * 60 * 1000,
    InferenceActivity.PROVIDER_TEST: 60 * 1000,
    InferenceActivity.READINESS_PROBE: 30 * 1000,
}


class FakeInferenceActivityStore:
    """An in-memory ``InferenceActivityStore`` fake.

    Mirrors the real gate's lease-ownership and watchdog semantics closely
    enough that a shared contract-test suite can pass against both. Not
    thread-safe by design — it is intended for single-threaded test use; the
    real store is the one that guarantees cross-thread safety.

    Args:
        clock: The injected time source (typically a test double) used for
            lease timestamps and watchdog elapsed-time arithmetic.
        event_bus: The event bus this fake publishes
            ``_inference_activity_changed`` on for every acquire and release.
    """

    def __init__(self, *, clock: Clock, event_bus: EventBus) -> None:
        self._clock = clock
        self._event_bus = event_bus
        self._current: InferenceActivity = InferenceActivity.IDLE
        self._context: InferenceActivityContext | None = None
        self._lease: GateLease | None = None
        self._lease_counter: int = 0
        self._armed_monotonic_ms: int | None = None

    def try_acquire(
        self,
        activity: InferenceActivity,
        context: InferenceActivityContext,
    ) -> GateLease | None:
        """Acquire the gate, or return ``None`` if already held."""
        self._maybe_watchdog_release()
        if self._lease is not None:
            return None
        self._lease_counter += 1
        lease = GateLease(
            activity=activity,
            lease_id=self._lease_counter,
            acquired_at=self._epoch_ms(),
        )
        self._current = activity
        self._context = context
        self._lease = lease
        self._armed_monotonic_ms = self._clock.monotonic_ms()
        self._emit(InferenceActivityState(current=activity, context=context))
        return lease

    def release(self, lease: GateLease) -> None:
        """Release the gate if ``lease`` is the current holder; else no-op."""
        self._maybe_watchdog_release()
        self._release(lease)

    def state(self) -> InferenceActivityState:
        """Return the current state, applying the watchdog check first."""
        self._maybe_watchdog_release()
        return InferenceActivityState(current=self._current, context=self._context)

    def is_busy(self) -> bool:
        """Convenience: ``state().current != InferenceActivity.IDLE``."""
        return self.state().current != InferenceActivity.IDLE

    def _release(self, lease: GateLease) -> InferenceActivityState | None:
        if self._lease is None or self._lease.lease_id != lease.lease_id:
            return None
        self._current = InferenceActivity.IDLE
        self._context = None
        self._lease = None
        self._armed_monotonic_ms = None
        new_state = InferenceActivityState(current=InferenceActivity.IDLE, context=None)
        self._emit(new_state)
        return new_state

    def _maybe_watchdog_release(self) -> InferenceActivityState | None:
        if self._lease is None or self._current is InferenceActivity.BENCHMARK_RUN:
            return None
        timeout_ms = _WATCHDOG_TIMEOUT_MS.get(self._current)
        if timeout_ms is None or self._armed_monotonic_ms is None:
            return None
        if self._clock.monotonic_ms() - self._armed_monotonic_ms < timeout_ms:
            return None
        stale_lease = self._lease
        return self._release(stale_lease)

    def _epoch_ms(self) -> int:
        return int(datetime.fromisoformat(self._clock.now_utc()).timestamp() * 1000)

    def _emit(self, state: InferenceActivityState) -> None:
        self._event_bus.emit(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED,
            InferenceActivityChangedEvent(state=state),
        )
