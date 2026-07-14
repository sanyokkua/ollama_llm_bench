"""ChartKind -> aggregator dispatch table and the concrete ChartAggregator (section 6)."""

from collections.abc import Callable

from ollama_llm_bench.backend.charts._internal import pipeline
from ollama_llm_bench.backend.charts._internal.aggregators import (
    avg_cosine as _avg_cosine,
    avg_time as _avg_time,
    avg_tps as _avg_tps,
    avg_ttft as _avg_ttft,
    heatmap_task_by_model as _heatmap_task_by_model,
    pass_rate as _pass_rate,
    per_category_bar as _per_category_bar,
    speed_vs_quality_scatter as _speed_vs_quality_scatter,
    success_failed_incomplete as _success_failed_incomplete,
    time_vs_tokens_scatter as _time_vs_tokens_scatter,
    tokens_per_task_box as _tokens_per_task_box,
    verdict_counts as _verdict_counts,
)
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

_Aggregator = Callable[..., ChartData | HeatmapData]

_DISPATCH: dict[ChartKind, _Aggregator] = {
    ChartKind.AVG_TTFT_PER_MODEL: _avg_ttft.compute_avg_ttft_per_model,
    ChartKind.AVG_TPS_PER_MODEL: _avg_tps.compute_avg_tps_per_model,
    ChartKind.AVG_TIME_PER_MODEL: _avg_time.compute_avg_time_per_model,
    ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED: (
        _success_failed_incomplete.compute_success_failed_incomplete_stacked
    ),
    ChartKind.PASS_RATE_BY_MODEL: _pass_rate.compute_pass_rate_by_model,
    ChartKind.AVG_COSINE_BY_MODEL: _avg_cosine.compute_avg_cosine_by_model,
    ChartKind.VERDICT_COUNTS_STACKED: _verdict_counts.compute_verdict_counts_stacked,
    ChartKind.TIME_VS_TOKENS_SCATTER: _time_vs_tokens_scatter.compute_time_vs_tokens_scatter,
    ChartKind.HEATMAP_TASK_BY_MODEL: _heatmap_task_by_model.compute_heatmap_task_by_model,
    ChartKind.PER_CATEGORY_BAR: _per_category_bar.compute_per_category_bar,
    ChartKind.SPEED_VS_QUALITY_SCATTER: (
        _speed_vs_quality_scatter.compute_speed_vs_quality_scatter
    ),
    ChartKind.TOKENS_PER_TASK_BOX: _tokens_per_task_box.compute_tokens_per_task_box,
}
"""Total over every `ChartKind` member — the twelve per-kind aggregator functions."""


class _ChartAggregatorImpl:
    """Concrete, stateless `ChartAggregator` (§6): runs the mode gate, then the
    shared global-filter/status-prefilter steps, then dispatches to the
    matching per-kind aggregator, which itself uses `pipeline.py`'s grouping
    and option-reading helpers."""

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
        if pipeline.is_grading_chart(chart_kind) and run_mode != RunMode.GRADED:
            return pipeline.empty_chart_for(chart_kind, message=pipeline.MODE_GATE_MESSAGE)

        tasks_by_id = pipeline.index_tasks_by_id(tasks)
        survived = pipeline.apply_global_filters(
            results=results, tasks_by_id=tasks_by_id, filters=filters
        )
        rows_for_chart = pipeline.apply_status_prefilter(survived, chart_kind)

        aggregator = _DISPATCH[chart_kind]
        return aggregator(
            rows=rows_for_chart,
            tasks_by_id=tasks_by_id,
            filters=filters,
            min_sample_size=min_sample_size,
        )
