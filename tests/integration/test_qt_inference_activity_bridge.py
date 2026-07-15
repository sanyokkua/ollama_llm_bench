"""Integration tests for ``QtInferenceActivityBridge`` crossing a real thread boundary
(STORY-043-AC-1).

Wires the real ``InferenceActivityStore`` gate (``backend/stores/inference_activity``,
STORY-015) to the real ``QtEventBusDeliverer`` (``adapters/qt_event_bus``, STORY-040) and
exercises the ``any -> UI`` threading rule genuinely: the gate is acquired and released from
a background ``threading.Thread``, never from the Qt GUI thread. This crosses real thread and
Qt-delivery boundaries, so it lives in ``tests/integration/`` rather than the module's
colocated unit tests (``testing-standard-pyqt`` skill; ``07_TESTING_STANDARD.md`` layout).
"""

import threading

from PySide6.QtCore import QCoreApplication, QThread
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.adapters.qt_inference_activity_bridge import (
    make_qt_inference_activity_bridge,
)
from ollama_llm_bench.backend.domain import (
    GateLease,
    InferenceActivity,
    InferenceActivityContext,
)
from ollama_llm_bench.backend.events import InferenceActivityChangedEvent
from ollama_llm_bench.backend.infra import make_system_clock
from ollama_llm_bench.backend.stores.inference_activity import make_inference_activity_store

_EXPECTED_EVENT_COUNT_AFTER_ACQUIRE_AND_RELEASE = 2


class _SubscriptionOwner:
    """A plain, weak-referenceable owner stand-in — a bare ``object()`` instance cannot be
    weakly referenced, so it cannot serve as a non-``QObject`` owner (the deliverer's
    ``weakref.finalize`` path). The caller must keep a strong reference to the instance for
    as long as the subscription should stay live."""


def test_gate_change_forwards_one_typed_event_on_gui_thread(qtbot: QtBot) -> None:
    """Proves: STORY-043-AC-1

    Given the bridge is wired to a real gate's ``_inference_activity_changed``
    publications through the real Qt event-bus deliverer,
    when the gate is acquired from a background thread,
    then the bridge delivers exactly one typed ``InferenceActivityChangedEvent`` carrying
    the new state onto the Qt GUI thread; and when the gate is released from a background
    thread too, a second, distinct event arrives — no coalescing across acquire and release.
    """
    # Arrange
    event_bus = make_qt_event_bus_deliverer()
    store = make_inference_activity_store(clock=make_system_clock(), event_bus=event_bus)
    bridge = make_qt_inference_activity_bridge(store=store, event_bus=event_bus)
    owner = _SubscriptionOwner()  # kept alive for the test's duration, see class docstring
    received_events: list[InferenceActivityChangedEvent] = []
    received_threads: list[QThread] = []

    def _handler(event: InferenceActivityChangedEvent) -> None:
        received_events.append(event)
        received_threads.append(QThread.currentThread())

    bridge.subscribe(_handler, owner=owner)
    context = InferenceActivityContext(activity=InferenceActivity.PROVIDER_TEST, started_at=0)
    acquired_lease: list[GateLease | None] = []

    def _acquire_on_worker() -> None:
        acquired_lease.append(store.try_acquire(InferenceActivity.PROVIDER_TEST, context))

    acquire_worker = threading.Thread(target=_acquire_on_worker)

    # Act — acquire from a background thread
    acquire_worker.start()
    acquire_worker.join(timeout=2)
    qtbot.waitUntil(lambda: len(received_events) == 1, timeout=2000)

    # Assert — exactly one typed event, carrying the new state, on the Qt GUI thread
    gui_thread = QCoreApplication.instance().thread()  # type: ignore[union-attr]
    assert len(received_events) == 1
    assert received_events[0].state.current == InferenceActivity.PROVIDER_TEST
    assert received_threads[0] is gui_thread

    lease = acquired_lease[0]
    assert lease is not None
    release_worker = threading.Thread(target=lambda: store.release(lease))

    # Act — release from a background thread too
    release_worker.start()
    release_worker.join(timeout=2)
    qtbot.waitUntil(
        lambda: len(received_events) == _EXPECTED_EVENT_COUNT_AFTER_ACQUIRE_AND_RELEASE,
        timeout=2000,
    )

    # Assert — a second, distinct event; no coalescing across acquire and release
    assert len(received_events) == _EXPECTED_EVENT_COUNT_AFTER_ACQUIRE_AND_RELEASE
    assert received_events[1] is not received_events[0]
    assert received_events[1].state.current == InferenceActivity.IDLE
    assert received_threads[1] is gui_thread
