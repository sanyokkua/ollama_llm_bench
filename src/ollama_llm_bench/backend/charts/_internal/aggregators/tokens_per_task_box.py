"""`TOKENS_PER_TASK_BOX` — kind 12 (`13_CHART_AGGREGATORS.md` §7.12).

Representation note: `categories` holds the model labels; five aligned
`ChartSeries` ("min", "q1", "median", "q3", "max") carry the five-number
summary per model. When *Show outliers* is on, one extra, unaligned
`ChartSeries` per model — `"{label} (outliers)"` — carries the outlier
`completion_tokens` values with their `result_ids`, mirroring kind 8's
point-cloud convention (§5 postcondition exempts scatter-shaped series from
category-length alignment).
"""

from collections.abc import Mapping

from ollama_llm_bench.backend.charts._internal import pipeline
from ollama_llm_bench.backend.charts._internal.outliers import (
    five_number_summary,
    partition_outliers,
)
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
_SUMMARY_NAMES = ("min", "q1", "median", "q3", "max")


def compute_tokens_per_task_box(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Per-model five-number summary of `completion_tokens`, outliers always separated (§7.12, CA-23, CA-24)."""
    del tasks_by_id
    show_outliers = pipeline.read_bool_option(
        filters, key="show_outliers", default=True, chart_kind=ChartKind.TOKENS_PER_TASK_BOX
    )

    categories: list[str] = []
    summary_values: dict[str, list[float | None]] = {name: [] for name in _SUMMARY_NAMES}
    sample_sizes: list[int] = []
    low_sample_flags: list[bool] = []
    outlier_series: list[ChartSeries] = []
    for group in pipeline.group_by_model(rows):
        tagged = [
            (float(row.completion_tokens), row.result_id)
            for row in group.rows
            if row.completion_tokens is not None
        ]
        if not tagged:
            continue
        kept, outliers = partition_outliers(tagged)
        remainder = [value for value, _result_id in kept] or [value for value, _result_id in tagged]
        summary = five_number_summary(remainder)
        categories.append(group.label)
        for name, value in zip(_SUMMARY_NAMES, summary, strict=True):
            summary_values[name].append(value)
        n = len(remainder)
        sample_sizes.append(n)
        low_sample_flags.append(pipeline.sample_flag(n, min_sample_size))
        if show_outliers and outliers:
            outlier_series.append(
                ChartSeries(
                    name=f"{group.label} (outliers)",
                    values=tuple(value for value, _result_id in outliers),
                    result_ids=tuple(result_id for _value, result_id in outliers),
                )
            )

    if not categories:
        return pipeline.empty_chart_data(ChartKind.TOKENS_PER_TASK_BOX, message=_EMPTY_MESSAGE)

    summary_series = tuple(
        ChartSeries(
            name=name,
            values=tuple(summary_values[name]),
            sample_sizes=tuple(sample_sizes),
            low_sample_flags=tuple(low_sample_flags),
        )
        for name in _SUMMARY_NAMES
    )
    return ChartData(
        chart_kind=ChartKind.TOKENS_PER_TASK_BOX,
        categories=tuple(categories),
        series=summary_series + tuple(outlier_series),
        x_axis_title="Model",
        y_axis_title="Completion tokens",
    )
