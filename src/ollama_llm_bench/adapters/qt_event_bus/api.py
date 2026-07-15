"""Public factory for the Qt-bound ``EventBus`` implementation (08-E §6).

Constructs the application's single ``QtEventBusDeliverer`` — the only place the
Qt-free ``backend/events`` bus is connected to Qt signals
(``01_MODULE_INVENTORY.md`` §5).
"""

import icontract
from PySide6.QtCore import QCoreApplication, QThread

from ollama_llm_bench.adapters.qt_event_bus._internal.deliverer import QtEventBusDeliverer

__all__: list[str] = ["QtEventBusDeliverer", "make_qt_event_bus_deliverer"]


@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist — called once from compose.py during start-up",
)
@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_qt_event_bus_deliverer must be called on the Qt GUI thread — every call site in "
    "this codebase is compose.py; a call from a worker thread is a programmer error",
)
def make_qt_event_bus_deliverer() -> QtEventBusDeliverer:
    """Construct the application's single Qt-bound EventBus implementation.

    Returns:
        A fresh ``QtEventBusDeliverer``, its relay signal already connected with
        a queued connection.
    """
    return QtEventBusDeliverer()
