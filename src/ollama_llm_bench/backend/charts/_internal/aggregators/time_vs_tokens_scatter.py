"""`TIME_VS_TOKENS_SCATTER` — kind 8 (`13_CHART_AGGREGATORS.md` §7.8).

Representation note (judgment call): `ChartData` has no dedicated per-point x/y
storage — only `categories` (shared axis-tick labels) and one numeric
`ChartSeries.values` vector per series. Because this is a per-row point cloud
(many points per model, unlike kind 11's one-point-per-model scatter),
`categories` is left empty and each model contributes **two** parallel
series — `"{label} (tokens)"` (x) and `"{label} (seconds)"` (y) — of equal
length, each carrying the same `result_ids` back-references at matching
indices. This satisfies the §5 postcondition that exempts scatter series from
category-length alignment while keeping every point losslessly recoverable.
"""

from collections.abc import Mapping

from ollama_llm_bench.backend.charts._internal import pipeline
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
_AXIS_SCALE_DOMAIN = ("linear", "log")


def compute_time_vs_tokens_scatter(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """One point per completed row with both fields non-null (§7.8, CA-15, CA-16).

    Per-row points, so no minimum-sample-size guard applies (§6.5a).
    """
    del tasks_by_id, min_sample_size
    pipeline.read_enum_option(
        filters,
        key="x_axis_scale",
        domain=_AXIS_SCALE_DOMAIN,
        default="linear",
        chart_kind=ChartKind.TIME_VS_TOKENS_SCATTER,
    )
    pipeline.read_enum_option(
        filters,
        key="y_axis_scale",
        domain=_AXIS_SCALE_DOMAIN,
        default="linear",
        chart_kind=ChartKind.TIME_VS_TOKENS_SCATTER,
    )

    plottable = [
        row for row in rows if row.completion_tokens is not None and row.total_time_ms is not None
    ]
    if not plottable:
        return pipeline.empty_chart_data(ChartKind.TIME_VS_TOKENS_SCATTER, message=_EMPTY_MESSAGE)

    series: list[ChartSeries] = []
    for group in pipeline.group_by_model(tuple(plottable)):
        x_values = tuple(float(row.completion_tokens) for row in group.rows)  # type: ignore[arg-type]
        y_values = tuple(row.total_time_ms / 1000.0 for row in group.rows)  # type: ignore[operator]
        result_ids = tuple(row.result_id for row in group.rows)
        series.append(
            ChartSeries(name=f"{group.label} (tokens)", values=x_values, result_ids=result_ids)
        )
        series.append(
            ChartSeries(name=f"{group.label} (seconds)", values=y_values, result_ids=result_ids)
        )

    return ChartData(
        chart_kind=ChartKind.TIME_VS_TOKENS_SCATTER,
        categories=(),
        series=tuple(series),
        x_axis_title="Completion tokens",
        y_axis_title="Total time",
        value_unit="s",
    )
