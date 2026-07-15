"""Integration tests for the Qt event bus deliverer crossing real thread and
QObject-lifetime boundaries (STORY-040-AC-1, STORY-040-AC-2).

These cross a real thread boundary and a real Qt object-destruction boundary, so
they live in ``tests/integration/`` rather than the module's colocated unit tests
(``testing-standard-pyqt`` skill; ``07_TESTING_STANDARD.md`` layout).
"""

import gc
import threading

from PySide6.QtCore import QObject
from pytestqt.qtbot import QtBot

from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent


class _SubscriptionOwner:
    """A plain, weak-referenceable owner stand-in — a bare ``object()`` instance
    cannot be weakly referenced, so it cannot serve as a non-``QObject`` owner. The
    caller must keep a strong reference to the instance for as long as the
    subscription should stay live; an owner with no other reference is
    garbage-collected immediately, auto-cancelling the subscription right away."""


def test_emit_from_worker_thread_delivers_on_gui_thread(qtbot: QtBot) -> None:
    """Proves: STORY-040-AC-1

    Given a handler subscribed on the main thread,
    when ``emit(signal_name, payload)`` is called from a non-GUI worker thread,
    then the handler is invoked on the Qt main thread with that payload (never
    on the emitting thread).
    """
    # Arrange
    deliverer = make_qt_event_bus_deliverer()
    main_thread_id = threading.get_ident()
    recorded_thread_ids: list[int] = []

    def _handler(_payload: object) -> None:
        recorded_thread_ids.append(threading.get_ident())

    owner = _SubscriptionOwner()  # kept alive for the test's duration, see class docstring
    deliverer.subscribe(SIGNAL_GLOBAL_MESSAGE, _handler, owner=owner)
    payload = GlobalMessageEvent(text="from worker")
    worker_thread_ids: list[int] = []

    def _emit_from_worker() -> None:
        worker_thread_ids.append(threading.get_ident())
        deliverer.emit(SIGNAL_GLOBAL_MESSAGE, payload)

    worker = threading.Thread(target=_emit_from_worker)

    # Act
    worker.start()
    worker.join(timeout=2)
    qtbot.waitUntil(lambda: len(recorded_thread_ids) == 1, timeout=2000)

    # Assert
    assert recorded_thread_ids == [main_thread_id]
    assert recorded_thread_ids[0] != worker_thread_ids[0]


def test_owner_destruction_auto_cancels_subscription(qtbot: QtBot) -> None:
    """Proves: STORY-040-AC-2

    Given a handler subscribed with an ``owner``,
    when that owner object is destroyed,
    then the subscription auto-cancels and a subsequent ``emit`` on that signal
    does not invoke the handler.
    """
    # Arrange
    deliverer = make_qt_event_bus_deliverer()
    handler_calls: list[object] = []
    owner = QObject()
    deliverer.subscribe(SIGNAL_GLOBAL_MESSAGE, handler_calls.append, owner=owner)

    # Act
    del owner  # immediate C++ destruction; the destroyed signal fires synchronously
    deliverer.emit(SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="after owner destroyed"))
    qtbot.wait(150)

    # Assert
    assert handler_calls == []


def test_non_qobject_owner_finalization_auto_cancels_subscription(qtbot: QtBot) -> None:
    """A non-``QObject`` owner also auto-cancels its subscription, via
    ``weakref.finalize`` rather than the ``destroyed`` signal, once the garbage
    collector reclaims it. Not tied to a named acceptance criterion — closes the
    second owner-lifetime path the deliverer implements (08-J §2)."""
    # Arrange
    deliverer = make_qt_event_bus_deliverer()
    handler_calls: list[object] = []

    class _PlainOwner:
        pass

    owner = _PlainOwner()
    deliverer.subscribe(SIGNAL_GLOBAL_MESSAGE, handler_calls.append, owner=owner)

    # Act
    del owner
    gc.collect()
    deliverer.emit(SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="after gc"))
    qtbot.wait(150)

    # Assert
    assert handler_calls == []
