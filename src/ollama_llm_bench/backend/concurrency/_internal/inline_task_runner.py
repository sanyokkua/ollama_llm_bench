"""The inline, synchronous ``TaskRunner`` implementation used by tests.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter — "Tests: an inline runner that executes
the callable synchronously, so backend logic is unit-tested with no threads and no Qt at
all.").

This implementation executes ``fn`` synchronously on the calling thread and returns an
already-resolved ``concurrent.futures.Future``. It never raises directly out of
``submit()`` — any failure, including a pre-submission cancellation, is captured on the
returned ``Future`` instead, exactly like the real Qt-backed and headless runners.
"""

from collections.abc import Callable
from concurrent.futures import Future

from ollama_llm_bench.backend.concurrency._internal.cancellation_token import (
    CancellationToken,
)

__all__: list[str] = [
    "InlineTaskRunner",
]


class InlineTaskRunner[T]:
    """Executes each submitted unit synchronously on the calling thread.

    Suitable for tests only — backend logic is exercised with zero threads
    and zero Qt. Honours ``token`` for a pre-submission cancellation check,
    exactly as the Qt-backed and headless runners must.
    """

    def submit(self, fn: Callable[[], T], *, token: CancellationToken) -> Future[T]:
        """Run ``fn`` immediately on the calling thread and return a resolved ``Future``.

        Suitable for unit tests only — backend logic is exercised with zero
        threads and zero Qt. Executes ``fn`` synchronously, honouring the
        cancellation token for a pre-submission check exactly as the
        Qt-backed and headless runners must. Never blocks the caller
        (since the ``Future`` is already resolved on return).

        Args:
            fn: The zero-argument blocking callable to execute.
            token: The run's cancellation token; checked with
                ``raise_if_cancelled()`` before ``fn`` runs.

        Returns:
            A ``Future`` already carrying ``fn``'s result, or any exception
            ``fn`` raised (including a pre-submission
            ``TaskCancelledError``).
        """
        future: Future[T] = Future()
        try:
            token.raise_if_cancelled()
            result = fn()
        except BaseException as exc:  # noqa: BLE001  # captured on the Future, not swallowed
            future.set_exception(exc)
        else:
            future.set_result(result)
        return future
