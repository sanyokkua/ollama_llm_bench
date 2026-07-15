"""The ``QRunnable`` wrapper completing a backend unit's ``Future`` on the worker thread.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter), §4a (the dispatcher thread — why the
completion path carries no Qt signal), §5 (the ``CancellationToken``);
``docs/v3_specification/08_Cross_Cutting/08-E_interfaces_contracts.md`` §4 (the threading
contract).

``_BackendUnitRunnable.run()`` executes a backend callable exactly once and completes the
unit's thread-safe stdlib ``Future`` directly on the worker thread that ``QThreadPool``
schedules it onto. No Qt signal participates in this path: the dispatcher thread that blocks
in ``Future.result()`` runs no Qt event loop, so a queued signal aimed at it would never be
delivered — Qt's role in this path is the thread pool only.
"""

from collections.abc import Callable
from concurrent.futures import Future

from PySide6.QtCore import QRunnable, Slot

from ollama_llm_bench.backend.concurrency import CancellationToken

__all__: list[str] = [
    "_BackendUnitRunnable",
]


class _BackendUnitRunnable[T](QRunnable):
    """Adapts a backend callable and its ``CancellationToken`` into a pool-schedulable unit.

    Strictly private to ``adapters/qt_runnables/`` — constructed only by
    ``_internal/task_runner.py``. Completes ``future`` by calling
    ``set_result``/``set_exception`` directly on whatever thread ``QThreadPool`` runs
    ``run()`` on; no ``Signal`` is declared anywhere on this class, so nothing in the
    completion path depends on a Qt event loop being alive on the reading thread.
    """

    def __init__(self, *, fn: Callable[[], T], token: CancellationToken, future: Future[T]) -> None:
        """Store the unit's callable, cancellation token, and result handle.

        Args:
            fn: The zero-argument blocking backend callable to execute.
            token: The run's ``CancellationToken``, stored as the exact object passed
                to ``submit`` — never copied or wrapped — so ``fn`` can poll the same
                token instance for cooperative cancellation.
            future: The result handle to complete once ``fn`` finishes or raises.
        """
        super().__init__()
        self._fn = fn
        self._token = token
        self._future = future

    @Slot()
    def run(self) -> None:
        """Execute the backend callable and complete ``future`` on this worker thread.

        Checks ``token.raise_if_cancelled()`` at the safe checkpoint before starting
        the unit, then runs ``fn``. Any exception it raises — including a
        pre-start ``TaskCancelledError`` — is captured on ``future`` via
        ``set_exception``; a successful result is captured via ``set_result``.
        Never raises out of this method: ``QThreadPool`` has no mechanism to observe
        an exception escaping a running ``QRunnable``.
        """
        try:
            self._token.raise_if_cancelled()
            result = self._fn()
        except BaseException as exc:  # noqa: BLE001  # allowlisted TaskRunner boundary
            self._future.set_exception(exc)
        else:
            self._future.set_result(result)
