"""``_ThreadRunDispatcher`` — the concrete, persistent ``pipeline-dispatcher`` thread.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§4a (the dispatcher thread, DD-38 — "One dispatcher thread exists per process... created
once in the composition root... owned by the adapter layer, and joined at shutdown; not an
ad-hoc per-work thread"). A plain ``threading.Thread`` is explicitly sanctioned here even in
the Qt frontend — DD-38 names it as the single sanctioned standalone thread; no ``QThread``
and no live ``QApplication`` are required to construct it.

``_ThreadRunDispatcher`` is started exactly once, at construction, and loops on a
``queue.Queue`` until ``shutdown`` enqueues its sentinel. ``submit`` is fast-synchronous
(enqueue and return); the loop itself runs each handed-off callable serially, one at a
time, which is exactly the pipeline's own dispatch-loop shape (D-R-16).
"""

from collections.abc import Callable
import queue
import threading
from typing import Final

__all__: list[str] = [
    "_ThreadRunDispatcher",
]

_DISPATCHER_THREAD_NAME: Final[str] = "pipeline-dispatcher"


class _ShutdownSentinel:
    """Marker enqueued by ``shutdown()`` to stop the dispatch loop.

    A dedicated type (rather than ``None``) so the queue's item type stays a
    precise union and the loop's ``isinstance`` check is unambiguous even if
    a future caller ever wanted to submit a callable that itself returns
    ``None`` bound as a value rather than invoked.
    """


_SHUTDOWN: Final[_ShutdownSentinel] = _ShutdownSentinel()


class _ThreadRunDispatcher:
    """The single, persistent, adapter-owned ``pipeline-dispatcher`` thread (DD-38).

    Strictly private to ``adapters/qt_benchmark_flow/`` — constructed only by
    ``api.make_run_dispatcher``. Structurally implements the backend's
    ``RunDispatcher`` Protocol (``backend/concurrency/protocols.py``); the
    backend never imports this class directly, only the Protocol.
    """

    def __init__(self) -> None:
        """Start the dispatcher thread immediately; it runs for the process's lifetime."""
        self._queue: queue.Queue[Callable[[], None] | _ShutdownSentinel] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_loop, name=_DISPATCHER_THREAD_NAME, daemon=False
        )
        self._thread.start()

    def submit(self, fn: Callable[[], None]) -> None:
        """Hand ``fn`` to the dispatcher thread and return immediately.

        Args:
            fn: The zero-argument callable that runs the pipeline's own
                dispatch loop for one run.
        """
        self._queue.put(fn)

    def shutdown(self, timeout_ms: int) -> None:
        """Stop accepting further work and join the dispatcher thread.

        Enqueues the shutdown sentinel behind any already-submitted work,
        then joins the thread within ``timeout_ms``. ``Thread.join`` returns
        silently on timeout without raising (DD-44) — a still-alive thread
        past the bound is surfaced only via the caller's own state checks.

        Args:
            timeout_ms: The maximum time, in milliseconds, to wait for the
                thread to finish and join.
        """
        self._queue.put(_SHUTDOWN)
        self._thread.join(timeout=timeout_ms / 1000)

    def _run_loop(self) -> None:
        """Run on the ``pipeline-dispatcher`` thread for the process's lifetime."""
        while True:
            item = self._queue.get()
            if isinstance(item, _ShutdownSentinel):
                return
            item()
