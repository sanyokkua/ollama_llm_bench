"""Public factory for the Qt-bound ``TaskRunner`` implementation (04_CONCURRENCY_STANDARD §3).

Constructs the application's single ``QtTaskRunner`` — the only place the Qt-free
``backend/concurrency`` ``TaskRunner`` port is bound to a real ``QThreadPool``
(``01_MODULE_INVENTORY.md`` §5).
"""

import icontract
from PySide6.QtCore import QCoreApplication

from ollama_llm_bench.adapters.qt_runnables._internal.task_runner import QtTaskRunner
from ollama_llm_bench.backend.concurrency import TaskRunner

__all__: list[str] = ["make_qt_task_runner"]


@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist — called once from compose.py during start-up",
)
@icontract.ensure(
    lambda result: result is not None,
    "make_qt_task_runner must always return a usable runner — a violation here means "
    "this factory's own wiring is broken, not that a caller passed bad input",
)
def make_qt_task_runner[T]() -> TaskRunner[T]:
    """Construct the application's single Qt-bound ``TaskRunner`` implementation.

    Returns:
        A fresh ``QtTaskRunner``, its ``QThreadPool`` fixed at ``maxThreadCount = 4``.
    """
    return QtTaskRunner()
