"""The concrete ``EventBus`` implementation that delivers onto the Qt GUI thread.

Source of truth: ``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md``
§6 (Event Bus), ``docs/v3_specification/08_Cross_Cutting/08-J_event_bus_catalog.md``
§3 (Threading model), and
``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md`` §2, §8.

``QtEventBusDeliverer`` IS the ``QObject`` that owns the subscriber registry and
implements the whole ``EventBus`` contract: ``emit`` from any thread re-delivers to
every subscriber's handler on the Qt GUI thread through one queued ``Signal``/slot
connection, so a handler never needs its own locking and may touch widgets
directly.

**Implementation note on the relay signal's placement.** PySide6 treats *any*
attribute literally named ``emit`` on a ``QObject`` — a method, a property, or an
instance attribute — as an override of the legacy per-object
``QObject.emit(signal, *args)`` dispatch: once such an attribute exists, *every*
``SignalInstance.emit()`` call for *any* signal owned by that same object is
silently redirected through the override instead of performing real Qt signal
activation (verified empirically; this is undocumented Shiboken behaviour, not a
documented Qt/PySide6 API). Because the ``EventBus`` Protocol requires this class
to expose a method literally named ``emit``, the relay ``Signal`` cannot live
directly on ``QtEventBusDeliverer`` itself without breaking its own delivery. The
relay therefore lives on ``_RelayCarrier``, a tiny private ``QObject`` held as an
implementation-only attribute — it is never exposed, never separately
constructed or wired outside this module, and ``QtEventBusDeliverer`` remains the
sole public class and sole ``EventBus`` implementation this module offers.
"""

from collections.abc import Callable
from dataclasses import dataclass
import functools
import threading
import weakref

import icontract
from PySide6.QtCore import QObject, Qt, Signal, Slot
import structlog

from ollama_llm_bench.backend.events import Subscription

log = structlog.get_logger("app.qt_event_bus")


@dataclass
class _Registration:
    """One live subscriber registration for a single signal name.

    Strictly private to this module; never crosses a module boundary.
    """

    handler: Callable[[object], None]
    cancelled: bool = False


class _QtSubscription:
    """The ``Subscription`` handle returned by ``QtEventBusDeliverer.subscribe``."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel_fn = cancel_fn
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the subscription.

        Idempotent — the first call stops further delivery to the handler;
        every subsequent call is a no-op. Never raises.
        """
        if self._cancelled:
            return
        self._cancelled = True
        self._cancel_fn()


class _RelayCarrier(QObject):
    """Private holder for the single generic relay signal.

    See the module docstring for why this signal cannot live directly on
    ``QtEventBusDeliverer``. Never constructed or referenced outside this
    module.
    """

    relay = Signal(str, object)


class QtEventBusDeliverer(QObject):
    """Marshals the Qt-free ``EventBus`` contract onto the Qt GUI thread.

    A single generic relay ``Signal(str, object)`` (held on the private
    ``_RelayCarrier``, see the module docstring) carries every emission,
    connected in ``__init__`` with an explicit
    ``Qt.ConnectionType.QueuedConnection`` so delivery is always asynchronous —
    even a same-thread ``emit()`` call is redelivered through the Qt event loop,
    which avoids reentrancy hazards and guarantees every handler runs on the GUI
    thread regardless of which thread called ``emit``.

    The subscriber registry is a plain ``dict`` guarded by one ``threading.Lock``
    because ``weakref.finalize`` callbacks (the non-``QObject`` owner path) can
    fire on whatever thread the garbage collector runs on, making the registry
    genuinely cross-thread mutable state.
    """

    def __init__(self) -> None:
        super().__init__()
        self._registry: dict[str, list[_Registration]] = {}
        self._lock = threading.Lock()
        self._carrier = _RelayCarrier(self)
        self._carrier.relay.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    @icontract.require(
        lambda owner: owner is not None,
        "owner is required — a subscription with no owner is a programming error "
        "rejected at subscribe time (08-J §2)",
    )
    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        """Register ``handler`` to run on the Qt GUI thread when ``signal_name`` fires.

        Args:
            signal_name: One of the closed set of leading-underscore signal-name
                constants exported by ``backend.events``.
            handler: Called with the event's payload when the signal fires.
            owner: The object whose lifetime bounds this subscription. A
                ``QObject`` owner auto-cancels on its ``destroyed`` signal; any
                other owner auto-cancels via ``weakref.finalize`` when it is
                garbage-collected.

        Returns:
            A ``Subscription`` handle for explicit early cancellation.
        """
        registration = _Registration(handler=handler)
        with self._lock:
            self._registry.setdefault(signal_name, []).append(registration)

        cancel_fn = functools.partial(self._cancel_registration, signal_name, registration)

        if isinstance(owner, QObject):
            owner.destroyed.connect(functools.partial(self._on_owner_destroyed, cancel_fn))
        else:
            weakref.finalize(owner, cancel_fn)

        return _QtSubscription(cancel_fn)

    def emit(  # type: ignore[override]  # EventBus Protocol requires this exact method name;
        # QObject also declares a legacy `emit(signal, *args)` with an incompatible signature.
        # This class intentionally satisfies the EventBus Protocol's `emit`, never QObject's
        # (see the module docstring for why the relay Signal itself lives on `_RelayCarrier`).
        self,
        signal_name: str,
        payload: object,
    ) -> None:
        """Publish ``payload`` on ``signal_name``.

        Safe to call from any thread. Delivery is queued onto the Qt GUI
        thread; every subscriber handler runs there. Never raises to the
        emitter.

        Args:
            signal_name: One of the closed set of leading-underscore signal-name
                constants exported by ``backend.events``.
            payload: One of the frozen event Structs catalogued in
                ``08-J_event_bus_catalog.md`` / ``08-Q_event_payload_schemas.md``.
        """
        self._carrier.relay.emit(signal_name, payload)

    def _cancel_registration(self, signal_name: str, registration: _Registration) -> None:
        """Drop ``registration`` from the registry. Idempotent; thread-safe."""
        with self._lock:
            if registration.cancelled:
                return
            registration.cancelled = True
            handlers = self._registry.get(signal_name)
            if handlers is not None:
                self._registry[signal_name] = [r for r in handlers if r is not registration]

    def _on_owner_destroyed(self, cancel_fn: Callable[[], None], *_args: object) -> None:
        """Slot connected to a ``QObject`` owner's ``destroyed`` signal.

        ``*_args`` absorbs the destroyed ``QObject`` argument Qt may pass;
        ``cancel_fn`` itself is idempotent, so this may run at most once with
        effect.
        """
        cancel_fn()

    @Slot(str, object)
    def _dispatch(self, signal_name: str, payload: object) -> None:
        """Invoke every live handler for ``signal_name`` with ``payload``.

        Runs on the Qt GUI thread (queued-connection delivery). Snapshots the
        live, non-cancelled handler list under the lock before invoking any
        handler, so a handler that cancels itself or subscribes anew mid-dispatch
        never mutates the list being iterated. Each handler runs in isolation —
        an exception is caught and logged so one faulty subscriber never breaks
        delivery to the others or raises back to the emitter.
        """
        with self._lock:
            handlers = [r for r in self._registry.get(signal_name, []) if not r.cancelled]

        for registration in handlers:
            if registration.cancelled:
                continue
            try:
                registration.handler(payload)
            except Exception:  # deliberate handler-isolation boundary (08-E §6); logged below
                log.exception("event_bus_handler_failed", signal_name=signal_name)
