"""Public surface for ``backend/concurrency/``: ``CancellationToken`` and ``TaskRunner``.

Source of truth: ``docs/v3_specification/16_Engineering_Standards/04_CONCURRENCY_STANDARD.md``
§3 (the ``TaskRunner`` port and the Qt adapter), §5 (the ``CancellationToken``);
``docs/v3_specification/11_Services_and_Algorithms/16_CONCURRENCY_MODEL.md`` §6.1, §6.3.
"""

import icontract

from ollama_llm_bench.backend.concurrency._internal.cancellation_token import (
    CancellationToken,
)
from ollama_llm_bench.backend.concurrency._internal.inline_task_runner import (
    InlineTaskRunner,
)
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.infra.protocols import Clock

__all__: list[str] = [
    "CancellationToken",
    "make_cancellation_token",
    "make_inline_task_runner",
]


@icontract.ensure(
    lambda result: not result.is_cancelled,
    "a freshly constructed CancellationToken must always start at level NONE — a "
    "violation here means this factory's own wiring is broken, not that a caller "
    "passed bad input",
)
def make_cancellation_token(*, clock: Clock) -> CancellationToken:
    """Construct a fresh ``CancellationToken`` for exactly one run.

    A token is single-use per run: construct one here for each new run,
    thread it through every unit of that run, and never reuse or share it
    across runs — it is never a process-wide singleton.

    Args:
        clock: The injected time source used for hard-cancel hook
            bookkeeping.

    Returns:
        A new, uncancelled ``CancellationToken`` at level ``NONE``.
    """
    return CancellationToken(clock=clock)


@icontract.ensure(
    lambda result: result is not None,
    "make_inline_task_runner must always return a usable runner — a violation here "
    "means this factory's own wiring is broken, not that a caller passed bad input",
)
def make_inline_task_runner[T]() -> TaskRunner[T]:
    """Construct the inline, synchronous ``TaskRunner`` implementation for tests.

    Executes each submitted unit immediately on the calling thread — no
    threads, no Qt, no ``asyncio``. The Qt-backed and headless
    ``ThreadPoolExecutor``-backed runners belong to ``adapters/qt_runnables/``
    and a later headless-frontend story respectively.

    Returns:
        A ``TaskRunner`` that runs every submitted unit synchronously.
    """
    return InlineTaskRunner()
