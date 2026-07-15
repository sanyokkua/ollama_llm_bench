"""``QtInferenceActivityBridge`` — the UI-facing gateway over the single-inference gate.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§13 (Inference Activity Store) and
``docs/v3_specification/08_Cross_Cutting/08-Q_event_payload_schemas.md`` §8.2
(``InferenceActivityChangedEvent``).

``QtInferenceActivityBridge`` carries no gate logic of its own — the
``InferenceActivityStore`` (``backend/stores/inference_activity/``) remains the single
owner of acquire/release, and the ``qt_event_bus`` deliverer (``adapters/qt_event_bus/``)
already marshals every ``EventBus`` emission onto the Qt GUI thread. This class is a thin
plain-Python forwarder, not a ``QObject``: it forwards the store's
``_inference_activity_changed`` publications to a typed subscription and exposes an
immediate-check ``is_inference_busy()`` read so a controller can decide in place whether to
disable its inference trigger. The UI never imports the store and never subscribes to a
backend reactive primitive directly (08-E §13).
"""

from collections.abc import Callable
from typing import cast

from ollama_llm_bench.backend.events import EventBus, InferenceActivityChangedEvent, Subscription
from ollama_llm_bench.backend.events.models import SIGNAL_INFERENCE_ACTIVITY_CHANGED
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = ["QtInferenceActivityBridge"]


class QtInferenceActivityBridge:
    """Marshals the single-inference gate onto the Qt GUI thread for UI observers.

    Holds the ``InferenceActivityStore`` (for the immediate-check read) and the
    ``EventBus`` (for typed subscription to the gate's change publications,
    already delivered on the Qt GUI thread by ``adapters/qt_event_bus/``).
    """

    def __init__(self, *, store: InferenceActivityStore, event_bus: EventBus) -> None:
        """Store the gate and the event bus this bridge forwards through.

        Args:
            store: The application-wide single-inference gate whose current
                busy-state ``is_inference_busy()`` reads synchronously.
            event_bus: The Qt-marshalling event bus this bridge subscribes to
                for ``_inference_activity_changed`` publications.
        """
        self._store = store
        self._event_bus = event_bus

    def subscribe(
        self,
        handler: Callable[[InferenceActivityChangedEvent], None],
        *,
        owner: object,
    ) -> Subscription:
        """Register ``handler`` to run on the Qt GUI thread on every gate change.

        Every gate acquire and release forwards as exactly one typed
        ``InferenceActivityChangedEvent`` — no coalescing (08-Q §8.2).

        Args:
            handler: Called with the typed event carrying the gate's new
                ``InferenceActivityState``.
            owner: The object whose lifetime bounds this subscription, passed
                through to the underlying ``EventBus.subscribe`` unchanged.

        Returns:
            A ``Subscription`` handle for explicit early cancellation.
        """

        def _dispatch(payload: object) -> None:
            handler(cast("InferenceActivityChangedEvent", payload))

        return self._event_bus.subscribe(
            SIGNAL_INFERENCE_ACTIVITY_CHANGED,
            _dispatch,
            owner=owner,
        )

    def is_inference_busy(self) -> bool:
        """Return the gate's current busy-state synchronously.

        fast-synchronous; callable from the Qt GUI thread for an in-place
        check (e.g. to decide whether to disable an inference trigger).

        Returns:
            ``True`` while the gate holds any activity; ``False`` when idle.
        """
        return self._store.is_busy()
