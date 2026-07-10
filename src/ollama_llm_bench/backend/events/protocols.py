"""The ``EventBus`` and ``Subscription`` service contracts.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§6 (Event Bus). This module declares the pure interface only — no concrete queueing,
threading, or Qt logic. The concrete implementation and its Qt delivery bridge live in
``adapters/qt_event_bus/`` (a later story); this module and its implementers stay
Qt-free.
"""

from collections.abc import Callable
from typing import Protocol

__all__: list[str] = [
    "EventBus",
    "Subscription",
]


class Subscription(Protocol):
    """A handle to one active Event Bus subscription."""

    def cancel(self) -> None:
        """Cancel the subscription.

        fast-synchronous; callable from any thread. Idempotent — calling it more
        than once, or after the owner it was bound to has already been destroyed,
        is a no-op. Never raises.
        """
        ...


class EventBus(Protocol):
    """The application-wide typed publish/subscribe channel.

    Every cross-component, cross-thread message in the application travels on this
    channel (`08-E` §6; `08-J_event_bus_catalog.md`). No service calls a UI object
    directly — a worker thread, the pipeline dispatcher, or UI code all reach other
    parts of the application only by emitting a payload here.
    """

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        """Register ``handler`` to run whenever ``signal_name`` is emitted.

        fast-synchronous; called on the main thread. ``handler`` always runs on
        the main thread regardless of which thread emitted the event. When
        ``owner`` is given, the subscription auto-cancels when the owner is
        destroyed, so a widget or controller never leaks a handler
        (`08-J_event_bus_catalog.md` §2 — a subscription with no owner is a
        programming error rejected at subscribe time by the concrete
        implementation).

        Args:
            signal_name: One of the closed set of leading-underscore signal-name
                constants exported by this package (e.g. ``_run_started``).
            handler: Called with the event's payload Struct when the signal fires.
            owner: The object whose lifetime bounds this subscription, or ``None``
                for a subscription with no owner (rejected at subscribe time by
                the concrete implementation).

        Returns:
            A ``Subscription`` handle for explicit early cancellation.
        """
        ...

    def emit(self, signal_name: str, payload: object) -> None:
        """Publish ``payload`` on ``signal_name``.

        fast-synchronous; safe to call from any thread — this is the
        application's only cross-thread notification channel. Delivery is
        queued onto the main thread; every subscriber handler runs there. Never
        raises to the emitter: an exception thrown inside a handler is caught,
        logged, and isolated by the concrete implementation so one faulty
        subscriber cannot break delivery to the others.

        Args:
            signal_name: One of the closed set of leading-underscore signal-name
                constants exported by this package.
            payload: One of the frozen event Structs catalogued in
                ``08-J_event_bus_catalog.md`` / ``08-Q_event_payload_schemas.md``.
        """
        ...
