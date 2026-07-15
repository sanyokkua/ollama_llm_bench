"""Unit tests for ``QtEventBusDeliverer`` (STORY-040-AC-3, STORY-040-AC-4).

These tests run against a real ``QApplication`` (via ``qtbot``) even though they are
scoped to this one module: the relay ``Signal`` is connected with
``Qt.ConnectionType.QueuedConnection``, so delivery requires a running Qt event loop
even for a same-thread ``emit()`` call (see the deliverer module docstring).
"""

from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.adapters.qt_event_bus import make_qt_event_bus_deliverer
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent


class _SubscriptionOwner:
    """A plain, weak-referenceable owner stand-in.

    A bare ``object()`` instance cannot be weakly referenced, so it cannot serve
    as a non-``QObject`` owner (the deliverer's ``weakref.finalize`` path) — an
    ordinary class instance is used instead. The caller must keep a strong
    reference to the instance for as long as the subscription should stay live;
    an owner with no other reference is garbage-collected immediately,
    auto-cancelling the subscription right away.
    """


def test_faulty_handler_is_isolated_and_emit_never_raises(qtbot: QtBot) -> None:
    """Proves: STORY-040-AC-3

    Given two handlers subscribed to the same signal where the first raises an
    exception,
    when the signal is emitted,
    then the first handler's exception is caught and logged, the second handler
    is still invoked, and ``emit`` returns normally to the caller.
    """
    # Arrange
    deliverer = make_qt_event_bus_deliverer()
    second_handler_calls: list[object] = []
    # Owners must outlive the subscribe() calls — an owner with no other strong
    # reference is garbage-collected immediately, which would auto-cancel the
    # subscription before emit() ever runs.
    first_owner = _SubscriptionOwner()
    second_owner = _SubscriptionOwner()

    def _faulty_handler(_payload: object) -> None:
        raise RuntimeError("boom")

    deliverer.subscribe(SIGNAL_GLOBAL_MESSAGE, _faulty_handler, owner=first_owner)
    deliverer.subscribe(SIGNAL_GLOBAL_MESSAGE, second_handler_calls.append, owner=second_owner)
    payload = GlobalMessageEvent(text="hello")

    # Act
    with structlog.testing.capture_logs() as captured_logs:
        deliverer.emit(SIGNAL_GLOBAL_MESSAGE, payload)  # must return normally, not raise
        qtbot.waitUntil(lambda: len(second_handler_calls) == 1, timeout=2000)

    # Assert
    assert second_handler_calls == [payload]
    failure_events = [
        record for record in captured_logs if record["event"] == "event_bus_handler_failed"
    ]
    assert len(failure_events) == 1
    assert failure_events[0]["signal_name"] == SIGNAL_GLOBAL_MESSAGE


def test_subscription_cancel_is_idempotent(qtbot: QtBot) -> None:
    """Proves: STORY-040-AC-4

    Given an active subscription,
    when ``Subscription.cancel()`` is called twice,
    then the first call stops further delivery to the handler and the second
    call is a no-op that does not raise.
    """
    # Arrange
    deliverer = make_qt_event_bus_deliverer()
    handler_calls: list[object] = []
    owner = _SubscriptionOwner()  # kept alive so cancel(), not GC, drives the outcome
    subscription = deliverer.subscribe(SIGNAL_GLOBAL_MESSAGE, handler_calls.append, owner=owner)

    # Act
    subscription.cancel()
    subscription.cancel()  # must not raise
    deliverer.emit(SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="after double cancel"))
    qtbot.wait(150)

    # Assert
    assert handler_calls == []
