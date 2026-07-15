"""``QtTaskRunner`` — the ``QThreadPool``-backed ``TaskRunner`` implementation.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter) — the fixed ``maxThreadCount = 4`` pool size
configured once at construction, and "the pool is owned by the adapter and shut down cleanly
at application exit."
"""

from collections.abc import Callable
from concurrent.futures import Future
from typing import Final

from PySide6.QtCore import QThreadPool

from ollama_llm_bench.adapters.qt_runnables._internal.runnable import _BackendUnitRunnable
from ollama_llm_bench.backend.concurrency import CancellationToken

_MAX_THREAD_COUNT: Final[int] = 4

__all__: list[str] = [
    "QtTaskRunner",
]


class QtTaskRunner[T]:
    """Schedules backend work units on a fixed-size ``QThreadPool``.

    Structurally implements the backend's ``TaskRunner`` Protocol
    (``backend/concurrency/protocols.py``) — the backend never imports this class or
    ``PySide6`` directly, only the Protocol. The pool size is fixed at
    ``maxThreadCount = 4`` once at construction (DD-40) and never changed afterwards.
    """

    def __init__(self) -> None:
        """Construct the pool with its fixed worker-thread count."""
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(_MAX_THREAD_COUNT)

    def submit(self, fn: Callable[[], T], *, token: CancellationToken) -> Future[T]:
        """Schedule ``fn`` on the pool and return its result handle.

        Fast-synchronous: returns immediately after handing the runnable to
        ``QThreadPool.start`` — never blocks awaiting ``fn``'s completion.

        Args:
            fn: The zero-argument blocking backend callable to execute.
            token: The run's ``CancellationToken``, carried into ``fn`` unchanged.

        Returns:
            A ``Future`` that resolves with ``fn``'s return value, or captures any
            exception ``fn`` raised, once a pool worker thread runs it.
        """
        future: Future[T] = Future()
        runnable = _BackendUnitRunnable(fn=fn, token=token, future=future)
        self._pool.start(runnable)
        return future

    def shutdown(self) -> None:
        """Block the calling thread until every scheduled unit has finished running.

        Not part of the ``TaskRunner`` Protocol. Called once by the composition
        root during application shutdown — after the dispatcher thread has been
        joined — to drain in-flight pool work cleanly before the process exits.
        """
        self._pool.waitForDone()
