"""Public factory for ``adapters/qt_inference_activity_bridge/`` (08-E §13, 08-Q §8.2).

Constructs the application's single ``QtInferenceActivityBridge`` — the sole UI-facing
gateway over the application-wide single-inference gate
(``01_MODULE_INVENTORY.md`` §5).
"""

import icontract

from ollama_llm_bench.adapters.qt_inference_activity_bridge._internal.bridge import (
    QtInferenceActivityBridge,
)
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.stores.inference_activity import InferenceActivityStore

__all__: list[str] = ["QtInferenceActivityBridge", "make_qt_inference_activity_bridge"]


@icontract.require(
    lambda store: store is not None,
    "store is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda event_bus: event_bus is not None,
    "event_bus is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_qt_inference_activity_bridge must always return a usable bridge — a violation "
    "here means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_qt_inference_activity_bridge(
    *, store: InferenceActivityStore, event_bus: EventBus
) -> QtInferenceActivityBridge:
    """Construct the UI-facing gateway over the single-inference gate.

    Args:
        store: The application-wide single-inference gate this bridge reads
            for the immediate-check ``is_inference_busy()`` gateway.
        event_bus: The Qt-marshalling event bus this bridge subscribes to for
            the store's ``_inference_activity_changed`` publications.

    Returns:
        A ``QtInferenceActivityBridge`` forwarding every gate change as a
        typed ``InferenceActivityChangedEvent`` on the Qt GUI thread, and
        exposing the synchronous ``is_inference_busy()`` gateway.
    """
    return QtInferenceActivityBridge(store=store, event_bus=event_bus)
