"""The ``TaskRunner`` scheduling port owned by this module.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter); ``docs/v3_specification/11_Services_and_
Algorithms/16_CONCURRENCY_MODEL.md`` §6.1 (the ``TaskRunner`` and the worker pool).

This module declares the pure interface only — no concrete scheduling implementation.
The Qt-backed implementation (``QThreadPool`` + ``QRunnable`` wrappers) belongs to
``adapters/qt_runnables/``; a ``concurrent.futures.ThreadPoolExecutor``-backed headless
implementation belongs to a later headless-frontend story; the inline, synchronous
implementation suitable for tests lives in this module's own ``_internal/`` and is
exposed through ``api.py`` as ``make_inline_task_runner``.
"""

from collections.abc import Callable
from concurrent.futures import Future
from typing import Protocol

from ollama_llm_bench.backend.concurrency._internal.cancellation_token import (
    CancellationToken,
)

__all__: list[str] = [
    "RunDispatcher",
    "TaskRunner",
]


class TaskRunner[T](Protocol):
    """Swappable execution port scheduling one blocking unit of backend work.

    The backend never knows *how* a unit is scheduled — only that it can submit
    a callable and observe its completion, exception, or cancellation through a
    standard-library ``concurrent.futures.Future``. No Qt symbol and no
    ``asyncio`` symbol ever appears in this Protocol or in any of its call
    sites within the backend.
    """

    def submit(self, fn: Callable[[], T], *, token: CancellationToken) -> Future[T]:
        """Schedule a blocking unit of backend work and return a result handle.

        Fast-synchronous (never blocks the caller waiting for ``fn`` to
        finish). Never raises — any failure of ``fn`` (including a
        pre-submission cancellation) is captured on the returned ``Future``
        instead. The backend never knows *how* work is scheduled (Qt
        ``QThreadPool``, ``concurrent.futures.ThreadPoolExecutor``, or
        inline) — only that it can submit a callable and observe its
        completion through a standard-library ``Future``.
        """
        ...


class RunDispatcher(Protocol):
    """A single, persistent, adapter-owned execution context for the pipeline's
    dispatch loop (DD-38). Exactly one instance exists per process; it outlives
    every individual run.

    Distinct from ``TaskRunner``: a ``RunDispatcher`` runs the pipeline's own
    serial ``run_phase``/``_dispatch_run`` orchestration loop on the single
    sanctioned standalone thread named ``pipeline-dispatcher`` (DD-38);
    ``TaskRunner`` schedules the individual blocking units that loop submits.
    The backend never knows *how* the dispatcher thread is constructed — only
    that it can hand it a callable to run and later shut it down cleanly.
    """

    def submit(self, fn: Callable[[], None]) -> None:
        """Hand ``fn`` to the dispatcher thread and return immediately.

        Fast-synchronous — never waits for ``fn`` to run or complete.

        Args:
            fn: The zero-argument callable that runs the pipeline's own
                dispatch loop for one run (e.g. ``_dispatch_run``).
        """
        ...

    def shutdown(self, timeout_ms: int) -> None:
        """Stop accepting further work and join the underlying thread.

        Waits up to ``timeout_ms`` for any in-flight ``fn`` to finish, then
        joins the thread. Idempotent; never raises (DD-44) — a still-running
        ``fn`` past the bound is surfaced only via the caller's own
        ``is_running()``/state checks, never as an exception.

        Args:
            timeout_ms: The maximum time, in milliseconds, to wait for
                in-flight work and the thread join to complete.
        """
        ...
