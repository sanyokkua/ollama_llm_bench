"""Public factories for ``adapters/qt_benchmark_flow/``: the real dispatcher thread and the
thin Qt-side facade over ``backend/benchmark_pipeline`` (08-E §11, 04_CONCURRENCY_STANDARD
§4a).

Constructs the application's single, persistent ``pipeline-dispatcher`` thread (DD-38) and
the ``QtBenchmarkFlow`` facade forwarding every ``BenchmarkFlowApi`` control/query call to
the backend pipeline unchanged (``01_MODULE_INVENTORY.md`` §5).
"""

import icontract

from ollama_llm_bench.adapters.qt_benchmark_flow._internal.dispatcher_thread import (
    _ThreadRunDispatcher,
)
from ollama_llm_bench.adapters.qt_benchmark_flow._internal.facade import QtBenchmarkFlow
from ollama_llm_bench.backend.benchmark_pipeline import BenchmarkFlowApi
from ollama_llm_bench.backend.concurrency import RunDispatcher

__all__: list[str] = [
    "QtBenchmarkFlow",
    "make_qt_benchmark_flow",
    "make_run_dispatcher",
]


@icontract.ensure(
    lambda result: result is not None,
    "make_run_dispatcher must always return a usable dispatcher — a violation here means "
    "this factory's own wiring is broken, not that a caller passed bad input",
)
def make_run_dispatcher() -> RunDispatcher:
    """Construct the application's single, persistent ``pipeline-dispatcher`` thread.

    Called exactly once by the composition root; the returned dispatcher is
    then wired into ``make_benchmark_pipeline`` and reused, unchanged, across
    every run the process handles for its lifetime (DD-38) — never
    reconstructed per run.

    Returns:
        A ``RunDispatcher`` backed by one plain ``threading.Thread`` named
        ``pipeline-dispatcher``, started here.
    """
    return _ThreadRunDispatcher()


@icontract.ensure(
    lambda result: result is not None,
    "make_qt_benchmark_flow must always return a usable facade — a violation here means "
    "this factory's own wiring is broken, not that a caller passed bad input",
)
def make_qt_benchmark_flow(*, pipeline: BenchmarkFlowApi) -> QtBenchmarkFlow:
    """Construct the thin Qt-side facade over the backend benchmark pipeline.

    Args:
        pipeline: The backend ``BenchmarkFlowApi`` implementation every
            facade call forwards to unchanged; already wired with its own
            ``RunDispatcher`` (via ``make_run_dispatcher``) by the
            composition root before this factory runs.

    Returns:
        A ``QtBenchmarkFlow`` forwarding every control/query call to
        ``pipeline``, carrying no business logic of its own.
    """
    return QtBenchmarkFlow(pipeline=pipeline)
