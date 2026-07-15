"""Unit test for ``QtInferenceActivityBridge.is_inference_busy()`` (STORY-043-AC-2).

No ``QApplication`` is needed: the bridge carries no Qt state of its own, and
``is_inference_busy()`` is a plain synchronous forward to the store's ``is_busy()``. Uses
the existing ``FakeInferenceActivityStore`` (``backend/stores/inference_activity/testing.py``,
STORY-015) plus a ``mocker.Mock(spec=EventBus)`` — the fake store still requires a real
``EventBus``-shaped collaborator to emit through, but this test never asserts on emission.
"""

from typing import cast

from pytest_mock import MockerFixture

from ollama_llm_bench.adapters.qt_inference_activity_bridge import (
    make_qt_inference_activity_bridge,
)
from ollama_llm_bench.backend.domain import InferenceActivity, InferenceActivityContext
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.stores.inference_activity.testing import FakeInferenceActivityStore


def test_is_inference_busy_reflects_current_gate_state(mocker: MockerFixture) -> None:
    """Proves: STORY-043-AC-2

    Given the gate is idle, ``is_inference_busy()`` returns ``False``; given a
    controller then acquires the gate, the same call returns ``True``; given the
    gate is released again, the call returns ``False`` once more — the immediate
    check reflects the current gate state synchronously.
    """
    # Arrange
    clock = cast("Clock", mocker.Mock(spec=Clock))
    clock.now_utc.return_value = "2026-01-01T00:00:00+00:00"  # type: ignore[attr-defined]
    clock.monotonic_ms.return_value = 0  # type: ignore[attr-defined]
    event_bus = cast("EventBus", mocker.Mock(spec=EventBus))
    store = FakeInferenceActivityStore(clock=clock, event_bus=event_bus)
    bridge = make_qt_inference_activity_bridge(store=store, event_bus=event_bus)
    context = InferenceActivityContext(activity=InferenceActivity.PROVIDER_TEST, started_at=0)

    # Act / Assert — idle before any acquisition
    assert bridge.is_inference_busy() is False

    # Act / Assert — busy once acquired
    lease = store.try_acquire(InferenceActivity.PROVIDER_TEST, context)
    assert lease is not None
    assert bridge.is_inference_busy() is True

    # Act / Assert — idle again once released
    store.release(lease)
    assert bridge.is_inference_busy() is False
