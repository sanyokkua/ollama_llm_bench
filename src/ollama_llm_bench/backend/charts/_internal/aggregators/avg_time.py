"""`AVG_TIME_PER_MODEL` — kind 3 (`13_CHART_AGGREGATORS.md` §7.3)."""

from collections.abc import Mapping

from ollama_llm_bench.backend.charts._internal import pipeline
from ollama_llm_bench.backend.charts._internal.outliers import mean_dropping_outliers
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    ChartSeries,
    TaskId,
)

_EMPTY_MESSAGE = "No completed inferences yet."
_Y_AXIS_SCALE_DOMAIN = ("linear", "log")


def compute_avg_time_per_model(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Mean `total_time_ms / 1000` per model, in seconds (§7.3).

    The Y-axis scale option is a presentation hint (§6.4) validated here but
    not stored — `ChartData` carries no rendering-scale field.
    """
    del tasks_by_id
    drop_outliers = pipeline.read_bool_option(
        filters, key="drop_outliers", default=True, chart_kind=ChartKind.AVG_TIME_PER_MODEL
    )
    pipeline.read_enum_option(
        filters,
        key="y_axis_scale",
        domain=_Y_AXIS_SCALE_DOMAIN,
        default="linear",
        chart_kind=ChartKind.AVG_TIME_PER_MODEL,
    )

    categories: list[str] = []
    values: list[float | None] = []
    sample_sizes: list[int] = []
    low_sample_flags: list[bool] = []
    for group in pipeline.group_by_model(rows):
        time_values = [
            float(row.total_time_ms) for row in group.rows if row.total_time_ms is not None
        ]
        if not time_values:
            continue
        mean_ms, n = mean_dropping_outliers(time_values, drop_outliers=drop_outliers)
        categories.append(group.label)
        values.append(mean_ms / 1000.0)
        sample_sizes.append(n)
        low_sample_flags.append(pipeline.sample_flag(n, min_sample_size))

    if not values:
        return pipeline.empty_chart_data(ChartKind.AVG_TIME_PER_MODEL, message=_EMPTY_MESSAGE)

    series = ChartSeries(
        name="Avg time",
        values=tuple(values),
        sample_sizes=tuple(sample_sizes),
        low_sample_flags=tuple(low_sample_flags),
    )
    return ChartData(
        chart_kind=ChartKind.AVG_TIME_PER_MODEL,
        categories=tuple(categories),
        series=(series,),
        x_axis_title="Model",
        y_axis_title="Total time",
        value_unit="s",
    )
