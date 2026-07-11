"""The concrete ``InferenceActivityStore`` implementation (DD-50).

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§13; ``docs/v3_specification/08_Cross_Cutting/08-I_edge_cases.md`` EC-RUN-14.

Lock discipline (load-bearing, do not change without re-reading the concurrency
standard): one ``threading.Lock`` guards every field below. The watchdog is
lazy/pull-based — it is checked and, if fired, applied at the top of every
locked public method — never a standalone timer thread (the only sanctioned
standalone thread in this application is the pipeline dispatcher thread;
``16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``). Every method computes
the ``InferenceActivityState`` value(s) to publish while holding the lock, then
calls ``event_bus.emit`` only after the ``with self._lock:`` block has exited —
a synchronous subscriber calling back into this store during ``emit`` must
never re-enter this non-reentrant lock.
"""

from datetime import datetime
import threading
from typing import Final

import structlog

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
    "InferenceActivityGate",
]

_logger = structlog.get_logger("app.stores.inference_activity")

_WATCHDOG_TIMEOUT_MS: Final[dict[InferenceActivity, int]] = {
    InferenceActivity.JUDGE_ANALYSIS: 10 * 60 * 1000,
    InferenceActivity.PROVIDER_TEST: 60 * 1000,
    InferenceActivity.READINESS_PROBE: 30 * 1000,
    # BENCHMARK_RUN and IDLE deliberately absent — no watchdog for either.
}


class InferenceActivityGate:
    """The application-wide single-inference gate (DD-50).

    One internal ``threading.Lock`` makes ``try_acquire`` an atomic
    test-and-set and makes ``state``/``is_busy`` locked reads. Ownership is
    the ``GateLease``, not the ``InferenceActivity`` enum, so a superseded
    lease can never free a successor's hold. A per-activity watchdog
    auto-releases a non-``BENCHMARK_RUN`` holder that outlives its timeout.
    """

    def __init__(self, *, clock: Clock, event_bus: EventBus) -> None:
        """Construct a fresh gate, starting ``IDLE``.

        Args:
            clock: The injected time source: ``now_utc()`` for wall-clock
                timestamps stamped onto leases/contexts, ``monotonic_ms()``
                exclusively for watchdog elapsed-time arithmetic.
            event_bus: The Qt-free event bus this store publishes
                ``_inference_activity_changed`` on for every acquire and every
                release (including a watchdog auto-release).
        """
        self._clock = clock
        self._event_bus = event_bus
        self._lock = threading.Lock()
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
        """Atomically acquire the gate, or return ``None`` if already held."""
        events_to_emit: list[InferenceActivityState] = []
        lease: GateLease | None = None
        with self._lock:
            watchdog_state = self._maybe_watchdog_release_locked()
            if watchdog_state is not None:
                events_to_emit.append(watchdog_state)
            if self._lease is not None:
                self._emit_all(events_to_emit)
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
            events_to_emit.append(InferenceActivityState(current=activity, context=context))
        self._emit_all(events_to_emit)
        return lease

    def release(self, lease: GateLease) -> None:
        """Release the gate if ``lease`` is the current holder; else no-op."""
        events_to_emit: list[InferenceActivityState] = []
        stale = False
        with self._lock:
            watchdog_state = self._maybe_watchdog_release_locked()
            if watchdog_state is not None:
                events_to_emit.append(watchdog_state)
            release_state = self._release_locked(lease)
            if release_state is not None:
                events_to_emit.append(release_state)
            else:
                stale = True
        self._emit_all(events_to_emit)
        if stale:
            _logger.warning(
                "inference_gate_release_noop_stale_lease",
                lease_activity=lease.activity.value,
                lease_id=lease.lease_id,
            )

    def state(self) -> InferenceActivityState:
        """Return the current state, applying the watchdog check first."""
        events_to_emit: list[InferenceActivityState] = []
        with self._lock:
            watchdog_state = self._maybe_watchdog_release_locked()
            if watchdog_state is not None:
                events_to_emit.append(watchdog_state)
            snapshot = InferenceActivityState(current=self._current, context=self._context)
        self._emit_all(events_to_emit)
        return snapshot

    def is_busy(self) -> bool:
        """Convenience: ``state().current != InferenceActivity.IDLE``."""
        return self.state().current != InferenceActivity.IDLE

    def _release_locked(self, lease: GateLease) -> InferenceActivityState | None:
        """Free the gate iff ``lease`` is the current holder.

        Must be called while ``self._lock`` is held.

        Returns:
            The new ``IDLE`` state to emit, or ``None`` if the lease was
            stale/foreign (no-op).
        """
        if self._lease is None or self._lease.lease_id != lease.lease_id:
            return None
        self._current = InferenceActivity.IDLE
        self._context = None
        self._lease = None
        self._armed_monotonic_ms = None
        return InferenceActivityState(current=InferenceActivity.IDLE, context=None)

    def _maybe_watchdog_release_locked(self) -> InferenceActivityState | None:
        """Check-and-expire the watchdog for the current holder, if any.

        Must be called while ``self._lock`` is held.

        Returns:
            The new ``IDLE`` state to emit if the watchdog fired, or ``None``
            if nothing fired.
        """
        if self._lease is None or self._current is InferenceActivity.BENCHMARK_RUN:
            return None
        timeout_ms = _WATCHDOG_TIMEOUT_MS.get(self._current)
        if timeout_ms is None or self._armed_monotonic_ms is None:
            return None
        if self._clock.monotonic_ms() - self._armed_monotonic_ms < timeout_ms:
            return None
        stale_lease, activity, context = self._lease, self._current, self._context
        new_state = self._release_locked(stale_lease)
        _logger.warning(
            "inference_gate_watchdog_fired",
            activity=activity.value,
            started_at=context.started_at if context is not None else None,
            timeout_ms=timeout_ms,
        )
        return new_state

    def _epoch_ms(self) -> int:
        """Derive the current wall-clock unix-ms value from ``Clock.now_utc()``.

        ``Clock`` exposes no direct epoch-ms accessor, so this parses the
        ISO-8601 UTC string it returns. ``monotonic_ms()`` is used exclusively
        for watchdog elapsed-time arithmetic and is never mixed with this
        value.
        """
        return int(datetime.fromisoformat(self._clock.now_utc()).timestamp() * 1000)

    def _emit_all(self, states: list[InferenceActivityState]) -> None:
        """Publish ``_inference_activity_changed`` for each state, in order.

        Called only after ``self._lock`` has been released, so a synchronous
        subscriber calling back into this store can never re-enter the lock.
        """
        for emitted_state in states:
            self._event_bus.emit(
                SIGNAL_INFERENCE_ACTIVITY_CHANGED,
                InferenceActivityChangedEvent(state=emitted_state),
            )
