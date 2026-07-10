"""CancellationToken and the TaskRunner scheduling port.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter), §5 (the ``CancellationToken``).

This module gives every other module the two Qt-free, ``asyncio``-free concurrency
primitives the backend depends on to stay synchronous and safely cancellable: the
swappable ``TaskRunner`` scheduling port (``make_inline_task_runner`` for tests; the
Qt-backed and headless implementations live in ``adapters/qt_runnables/`` and a later
headless-frontend story respectively) and the two-level, cooperative
``CancellationToken`` (``make_cancellation_token``).
"""

from ollama_llm_bench.backend.concurrency.api import (
    CancellationToken,
    make_cancellation_token,
    make_inline_task_runner,
)
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner

__all__: list[str] = [
    "CancellationToken",
    "TaskRunner",
    "make_cancellation_token",
    "make_inline_task_runner",
]
