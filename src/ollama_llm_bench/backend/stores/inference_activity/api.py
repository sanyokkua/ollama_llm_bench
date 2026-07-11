"""Public surface for ``backend/stores/inference_activity/``.

The composition root constructs this store once over the shared ``Clock`` and
``EventBus`` and injects it wherever an ``InferenceActivityStore`` is needed —
the benchmark pipeline, the judge-analysis runner, the Provider Edit Test
probe, and the readiness service each acquire-then-release the returned gate
for the full duration of their inference activity.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§13.
"""

import icontract

from ollama_llm_bench.backend.domain import InferenceActivity
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.stores.inference_activity._internal.gate import (
    InferenceActivityGate,
)
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = [
    "InferenceActivityStore",
    "make_inference_activity_store",
]


@icontract.require(
    lambda clock: clock is not None,
    "clock is a required collaborator wired by compose.py",
)
@icontract.require(
    lambda event_bus: event_bus is not None,
    "event_bus is a required collaborator wired by compose.py",
)
@icontract.ensure(
    lambda result: result.state().current == InferenceActivity.IDLE,
    "a freshly constructed gate always starts IDLE",
)
def make_inference_activity_store(*, clock: Clock, event_bus: EventBus) -> InferenceActivityStore:
    """Construct the application-wide single-inference gate.

    Args:
        clock: The injected time source used for lease timestamps and the
            per-activity watchdog's elapsed-time arithmetic.
        event_bus: The Qt-free event bus this store publishes
            ``_inference_activity_changed`` on for every acquire and release.

    Returns:
        A fresh ``InferenceActivityStore``, starting ``IDLE``.
    """
    return InferenceActivityGate(clock=clock, event_bus=event_bus)
