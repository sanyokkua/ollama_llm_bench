"""`ChartAggregator` — this module's swap point (`13_CHART_AGGREGATORS.md` §2)."""

from typing import Protocol

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    PositiveInt,
    RunMode,
)


class ChartAggregator(Protocol):
    """Computes one of the twelve chart kinds from a run's result snapshot.

    Every call is a pure function of its arguments: fast-synchronous, in-memory
    only, no I/O, no shared mutable state — safe to call from any thread (§10).
    It never raises to the caller for an ordinary data condition — it returns the
    chart kind's empty-state structure instead (§9).
    """

    def compute(  # noqa: PLR0913  # one parameter per §2 input; the shape is fixed by
        # 13_CHART_AGGREGATORS.md §2 and mirrored exactly by every concrete/fake impl
        self,
        *,
        chart_kind: ChartKind,
        run_mode: RunMode,
        results: tuple[BenchmarkResult, ...],
        tasks: tuple[BenchmarkTask, ...],
        filters: ChartFilters,
        min_sample_size: PositiveInt = 5,
    ) -> ChartData | HeatmapData:
        """Aggregate one chart kind over a run's result snapshot (§6, §7).

        fast-synchronous; pure, no I/O, no shared mutable state; safe from any
        thread. Never raises to the caller for an ordinary data condition —
        returns the chart kind's empty-state structure instead.

        Args:
            chart_kind: Which of the twelve aggregators to run.
            run_mode: The mode of the run; gates the six grading-only kinds.
            results: Every result row of the run, as an immutable snapshot from
                the result cache — not re-queried per chart.
            tasks: The run's frozen tasks; supplies `category`, `difficulty`,
                and `task_id` ordering for filtering and the heatmap and
                per-category kinds.
            filters: The active global filter selection plus per-chart options.
            min_sample_size: The minimum-sample-size guard threshold
                (`eval.min_sample_size`, default the spec's default of `5`);
                the caller (a future ResultGateway) resolves it from Settings
                and passes it in, since this module has no Settings dependency
                (`01_MODULE_INVENTORY.md`).

        Returns:
            A `ChartData` for every kind except `HEATMAP_TASK_BY_MODEL`, which
            returns a `HeatmapData`; either may be the kind-specific empty-state
            structure.
        """
        ...
