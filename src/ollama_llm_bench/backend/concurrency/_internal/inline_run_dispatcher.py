"""The inline, synchronous ``RunDispatcher`` implementation used by tests.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§4a (the dispatcher thread, DD-38 — "One dispatcher thread exists per process... created
once in the composition root... not an ad-hoc per-work thread").

This implementation executes ``fn`` synchronously on the calling thread, so the pipeline's
own lifecycle logic is unit-tested with no threads and no Qt at all — mirroring
``InlineTaskRunner``'s role for the ``TaskRunner`` port. The real, persistent
``pipeline-dispatcher`` thread implementation lives in ``adapters/qt_benchmark_flow/``.
"""

from collections.abc import Callable

__all__: list[str] = [
    "InlineRunDispatcher",
]


class InlineRunDispatcher:
    """Runs every submitted unit of work synchronously on the calling thread.

    Suitable for tests only — the pipeline's dispatch loop is exercised with
    zero threads and zero Qt. ``shutdown`` is a no-op since every submitted
    ``fn`` has already completed by the time ``submit`` returns.
    """

    def submit(self, fn: Callable[[], None]) -> None:
        """Run ``fn`` immediately on the calling thread.

        Args:
            fn: The zero-argument callable to execute synchronously.
        """
        fn()

    def shutdown(self, timeout_ms: int) -> None:
        """No-op: every submitted unit has already run to completion by now.

        Args:
            timeout_ms: Unused; accepted only to satisfy the ``RunDispatcher``
                Protocol's signature.
        """
        del timeout_ms
