"""UI-facing gateway over the application-wide single-inference gate (STORY-043).

Forwards the `InferenceActivityStore`'s `_inference_activity_changed` publications — already
marshalled onto the Qt GUI thread by `adapters/qt_event_bus/` — to typed subscribers, and
exposes the immediate-check `is_inference_busy()` read. Carries no gate logic of its own.
"""

from ollama_llm_bench.adapters.qt_inference_activity_bridge.api import (
    QtInferenceActivityBridge,
    make_qt_inference_activity_bridge,
)

__all__: list[str] = ["QtInferenceActivityBridge", "make_qt_inference_activity_bridge"]
