"""`AVG_TTFT_PER_MODEL` — kind 1 (`13_CHART_AGGREGATORS.md` §7.1)."""

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

_EMPTY_MESSAGE = "No time-to-first-token data — provider streaming is required for this metric."
_UNIT_DOMAIN = ("ms", "seconds")


def compute_avg_ttft_per_model(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Mean `ttft_ms` per model, over non-null values only (§7.1)."""
    del tasks_by_id
    unit = pipeline.read_enum_option(
        filters,
        key="unit",
        domain=_UNIT_DOMAIN,
        default="ms",
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
    )
    drop_outliers = pipeline.read_bool_option(
        filters, key="drop_outliers", default=True, chart_kind=ChartKind.AVG_TTFT_PER_MODEL
    )

    categories: list[str] = []
    values: list[float | None] = []
    sample_sizes: list[int] = []
    low_sample_flags: list[bool] = []
    for group in pipeline.group_by_model(rows):
        ttft_values = [float(row.ttft_ms) for row in group.rows if row.ttft_ms is not None]
        if not ttft_values:
            continue
        mean_ms, n = mean_dropping_outliers(ttft_values, drop_outliers=drop_outliers)
        categories.append(group.label)
        values.append(mean_ms / 1000.0 if unit == "seconds" else mean_ms)
        sample_sizes.append(n)
        low_sample_flags.append(pipeline.sample_flag(n, min_sample_size))

    if not values:
        return pipeline.empty_chart_data(ChartKind.AVG_TTFT_PER_MODEL, message=_EMPTY_MESSAGE)

    series = ChartSeries(
        name="Avg TTFT",
        values=tuple(values),
        sample_sizes=tuple(sample_sizes),
        low_sample_flags=tuple(low_sample_flags),
    )
    return ChartData(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        categories=tuple(categories),
        series=(series,),
        x_axis_title="Model",
        y_axis_title="Time to first token",
        value_unit=unit,
    )
