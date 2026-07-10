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
