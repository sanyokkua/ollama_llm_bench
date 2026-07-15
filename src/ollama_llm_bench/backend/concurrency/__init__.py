"""CancellationToken, the TaskRunner scheduling port, and the RunDispatcher port.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter), §4a (the dispatcher thread, DD-38), §5
(the ``CancellationToken``).

This module gives every other module the Qt-free, ``asyncio``-free concurrency
primitives the backend depends on to stay synchronous and safely cancellable: the
swappable ``TaskRunner`` scheduling port (``make_inline_task_runner`` for tests; the
Qt-backed and headless implementations live in ``adapters/qt_runnables/`` and a later
headless-frontend story respectively), the ``RunDispatcher`` port for the pipeline's
single, persistent dispatch thread (``make_inline_run_dispatcher`` for tests; the real,
adapter-owned ``pipeline-dispatcher`` thread lives in ``adapters/qt_benchmark_flow/``),
and the two-level, cooperative ``CancellationToken`` (``make_cancellation_token``).
"""

from ollama_llm_bench.backend.concurrency.api import (
    CancellationToken,
    make_cancellation_token,
    make_inline_run_dispatcher,
    make_inline_task_runner,
)
from ollama_llm_bench.backend.concurrency.protocols import RunDispatcher, TaskRunner

__all__: list[str] = [
    "CancellationToken",
    "RunDispatcher",
    "TaskRunner",
    "make_cancellation_token",
    "make_inline_run_dispatcher",
    "make_inline_task_runner",
]
