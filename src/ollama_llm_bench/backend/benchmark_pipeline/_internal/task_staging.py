"""The concrete `RunTaskStager`: a `RunStartRequest` expanded into frozen tasks.

Closes the gap the run-creation path carried until now — `RunStartRequest`
assembled `task_paths`/`performance_config` in the New Benchmark widget and
nothing ever read them, so a run started from the UI executed zero tasks. This
module is the reader: `SYNTHETIC` expands the `PerformanceTaskGenerator` grid,
`TASKS`/`GRADED` load every path through the `TaskFileLoader`.
"""

import msgspec

from ollama_llm_bench.backend.benchmark_pipeline.protocols import RunTaskStager
from ollama_llm_bench.backend.domain.models import BenchmarkTask, RunMode, RunStartRequest
from ollama_llm_bench.backend.performance_task_generator.protocols import PerformanceTaskGenerator
from ollama_llm_bench.backend.task_files.protocols import TaskFileLoader

__all__: list[str] = ["_RunTaskStagerImpl"]


class _RunTaskStagerImpl:
    """Concrete `RunTaskStager` over the two already-implemented task sources."""

    def __init__(
        self,
        *,
        performance_task_generator: PerformanceTaskGenerator,
        task_file_loader: TaskFileLoader,
    ) -> None:
        self._performance_task_generator = performance_task_generator
        self._task_file_loader = task_file_loader

    def build(self, request: RunStartRequest, /) -> tuple[BenchmarkTask, ...]:
        """Expand `request` into its tasks (see `RunTaskStager.build`).

        Renumbers `task_order` over the assembled tuple. The synthetic generator
        already numbers its own grid — for that mode this is the identity — but
        `TaskFileLoader` leaves every task at the default `0`, so without this
        `TasksStore.list_tasks`' `ORDER BY task_order` would return a
        multi-file run's tasks in an arbitrary order and lose the documented
        path-order concatenation.
        """
        staged = (
            self._build_synthetic(request)
            if request.run_mode is RunMode.SYNTHETIC
            else self._build_from_files(request)
        )
        return tuple(
            msgspec.structs.replace(task, task_order=order) for order, task in enumerate(staged)
        )

    def _build_synthetic(self, request: RunStartRequest) -> tuple[BenchmarkTask, ...]:
        """Expand the request's `(input size x output size x repeat)` grid.

        A `SYNTHETIC` request with no `performance_config` stages nothing rather
        than raising: the pipeline never raises to its caller, and an empty run
        settles `COMPLETED` with zero rows exactly as it did before staging
        existed.
        """
        if request.performance_config is None:
            return ()
        return self._performance_task_generator.generate(request.performance_config)

    def _build_from_files(self, request: RunStartRequest) -> tuple[BenchmarkTask, ...]:
        """Concatenate every path's tasks in path order, first `task_id` wins.

        The cross-file de-duplication mirrors the loader's own documented
        within-file rule, so two files declaring the same `task_id` behave the
        same way one file declaring it twice does.
        """
        staged: list[BenchmarkTask] = []
        seen: set[str] = set()
        for source_path in request.task_paths:
            for task in self._task_file_loader.load(source_path):
                if task.task_id in seen:
                    continue
                seen.add(task.task_id)
                staged.append(task)
        return tuple(staged)


def _assert_protocol_conformance(impl: _RunTaskStagerImpl) -> RunTaskStager:
    """Static-typing helper: assert `_RunTaskStagerImpl` satisfies `RunTaskStager`."""
    return impl
