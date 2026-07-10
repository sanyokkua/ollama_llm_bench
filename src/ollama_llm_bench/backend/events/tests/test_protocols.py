"""Tests proving the ``EventBus``/``Subscription`` Protocol-shape acceptance criterion.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§6 (Event Bus). This module tests the Protocol's declared shape only — no concrete
implementation exists yet (owned by ``adapters/qt_event_bus/``, a later story).
"""

import abc
import inspect
from typing import get_type_hints

from ollama_llm_bench.backend.events import EventBus, Subscription


def test_event_bus_and_subscription_protocol_shape() -> None:
    """Proves: STORY-003-AC-1

    Given the ``backend.events`` public surface,
    when the ``EventBus`` and ``Subscription`` types are inspected,
    then both are ``typing.Protocol`` types (never ``abc.ABC``), ``EventBus`` declares
    exactly ``subscribe(signal_name, handler, owner=None) -> Subscription`` and
    ``emit(signal_name, payload) -> None``, and ``Subscription`` declares exactly
    ``cancel() -> None``.
    """
    # Arrange
    event_bus_public_methods = {
        name
        for name, _ in inspect.getmembers(EventBus, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    subscription_public_methods = {
        name
        for name, _ in inspect.getmembers(Subscription, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    # Act
    subscribe_signature = inspect.signature(EventBus.subscribe)
    emit_signature = inspect.signature(EventBus.emit)
    cancel_signature = inspect.signature(Subscription.cancel)

    # Assert
    assert getattr(EventBus, "_is_protocol", False) is True
    assert getattr(Subscription, "_is_protocol", False) is True
    assert not issubclass(EventBus, abc.ABC)
    assert not issubclass(Subscription, abc.ABC)
    assert event_bus_public_methods == {"subscribe", "emit"}
    assert subscription_public_methods == {"cancel"}
    assert list(subscribe_signature.parameters) == ["self", "signal_name", "handler", "owner"]
    assert subscribe_signature.parameters["owner"].default is None
    assert subscribe_signature.return_annotation is Subscription
    assert list(emit_signature.parameters) == ["self", "signal_name", "payload"]
    assert emit_signature.return_annotation is None
    assert list(cancel_signature.parameters) == ["self"]
    assert cancel_signature.return_annotation is None
    assert get_type_hints(EventBus.emit)["payload"] is object
