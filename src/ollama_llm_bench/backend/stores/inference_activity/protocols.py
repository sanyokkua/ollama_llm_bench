"""The ``InferenceActivityStore`` contract owned by this module.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§13 (Inference Activity Store); ``docs/v3_specification/11_Services_and_Algorithms/
01_SERVICE_INVENTORY.md`` §4.14; ``docs/v3_specification/08_Cross_Cutting/
08-I_edge_cases.md`` EC-RUN-14.
"""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
    InferenceActivityState,
)

__all__: list[str] = [
    "InferenceActivityStore",
]


class InferenceActivityStore(Protocol):
    """Application-wide single-inference gate. Method-only; stdlib + msgspec
    types only — no Qt symbol and no ``psygnal.Signal`` appear on this Protocol
    (08-A §3). State-change notification is published by the concrete store as
    the typed ``_inference_activity_changed`` event on the Qt-free event bus;
    how the concrete store detects a change internally is an implementation
    detail that never crosses this contract.

    All four methods are thread-safe from any thread — both ``QThreadPool``
    worker threads (the pipeline, the Provider Edit Test probe runner) and the
    Qt main thread (UI gating reads) — and never raise. A failed acquire is
    data (``None``), not an exception; a stale/foreign release is a logged
    no-op; ``state``/``is_busy`` always return.
    """

    def try_acquire(
        self,
        activity: InferenceActivity,
        context: InferenceActivityContext,
    ) -> GateLease | None:
        """Atomically acquire the gate (DD-50).

        fast-synchronous; callable from any thread; never raises.

        Args:
            activity: The activity class attempting to acquire the gate.
            context: The context to record for this acquisition (activity,
                start time, and the optional run/provider/model identifiers).

        Returns:
            A ``GateLease`` — the opaque ownership token for this acquisition
            — when the gate was ``IDLE`` and is now held; ``None`` when the
            gate is already held by any other activity. The caller MUST pair
            a successful ``try_acquire`` with ``release(lease)`` in a
            ``try``/``finally`` so the gate is freed even on exception.
        """
        ...

    def release(self, lease: GateLease) -> None:
        """Release the gate IF ``lease`` is the current holder (DD-50).

        fast-synchronous; callable from any thread; never raises; idempotent.
        Ownership is the lease, not the activity enum: a release carrying a
        superseded or foreign lease — e.g. a worker's late ``finally`` after
        the watchdog already released its lease and a new same-class activity
        acquired — is a logged no-op and can never free a successor's hold.

        Args:
            lease: The lease previously returned by a successful
                ``try_acquire`` call.
        """
        ...

    def state(self) -> InferenceActivityState:
        """Return the current state synchronously.

        fast-synchronous; callable from any thread; never raises. The
        returned value is an immutable snapshot; callers do not need to copy
        it.
        """
        ...

    def is_busy(self) -> bool:
        """Convenience: ``state().current != InferenceActivity.IDLE``.

        fast-synchronous; callable from any thread; never raises.
        """
        ...
