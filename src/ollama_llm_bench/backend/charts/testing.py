"""A configurable fake `ChartAggregator` for downstream module tests."""

from ollama_llm_bench.backend.charts._internal.pipeline import empty_chart_for
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

__all__: list[str] = ["FakeChartAggregator"]


class FakeChartAggregator:
    """An in-memory fake recording every `compute()` call and returning a
    pre-configured structure via `set_result`, defaulting to the kind's own
    empty-state structure (with an empty message) when unconfigured.
    """

    def __init__(self) -> None:
        self._results: dict[ChartKind, ChartData | HeatmapData] = {}
        self.recorded_calls: list[dict[str, object]] = []

    def compute(  # noqa: PLR0913  # mirrors the ChartAggregator Protocol's fixed §2 shape
        self,
        *,
        chart_kind: ChartKind,
        run_mode: RunMode,
        results: tuple[BenchmarkResult, ...],
        tasks: tuple[BenchmarkTask, ...],
        filters: ChartFilters,
        min_sample_size: PositiveInt = 5,
    ) -> ChartData | HeatmapData:
        """Record the call and return whatever `set_result` configured, or the
        kind's empty-state structure by default."""
        self.recorded_calls.append(
            {
                "chart_kind": chart_kind,
                "run_mode": run_mode,
                "results": results,
                "tasks": tasks,
                "filters": filters,
                "min_sample_size": min_sample_size,
            }
        )
        if chart_kind in self._results:
            return self._results[chart_kind]
        return empty_chart_for(chart_kind, message="")

    def set_result(self, chart_kind: ChartKind, structure: ChartData | HeatmapData) -> None:
        """Test helper: force a chart kind's `compute()` return value."""
        self._results[chart_kind] = structure
