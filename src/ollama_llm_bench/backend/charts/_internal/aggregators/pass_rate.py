"""`PASS_RATE_BY_MODEL` — kind 5 (`13_CHART_AGGREGATORS.md` §7.5)."""

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
    Verdict,
)

_EMPTY_MESSAGE = "No verdicts yet — this run has not reached the judge stage."


def compute_pass_rate_by_model(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """`count(verdict == PASS) / denominator` per model (§7.5, CA-9..CA-11)."""
    del tasks_by_id
    ungraded_counts_as_not_pass = pipeline.read_bool_option(
        filters,
        key="count_ungraded_as_not_pass",
        default=True,
        chart_kind=ChartKind.PASS_RATE_BY_MODEL,
    )

    categories: list[str] = []
    values: list[float | None] = []
    sample_sizes: list[int] = []
    low_sample_flags: list[bool] = []
    for group in pipeline.group_by_model(rows):
        graded_rows = [row for row in group.rows if row.verdict is not None]
        passed = sum(1 for row in graded_rows if row.verdict == Verdict.PASS)
        denominator = len(group.rows) if ungraded_counts_as_not_pass else len(graded_rows)
        if denominator == 0:
            continue
        categories.append(group.label)
        values.append(passed / denominator)
        sample_sizes.append(denominator)
        low_sample_flags.append(pipeline.sample_flag(denominator, min_sample_size))

    if not values:
        return pipeline.empty_chart_data(ChartKind.PASS_RATE_BY_MODEL, message=_EMPTY_MESSAGE)

    series = ChartSeries(
        name="Pass rate",
        values=tuple(values),
        sample_sizes=tuple(sample_sizes),
        low_sample_flags=tuple(low_sample_flags),
    )
    return ChartData(
        chart_kind=ChartKind.PASS_RATE_BY_MODEL,
        categories=tuple(categories),
        series=(series,),
        x_axis_title="Model",
        y_axis_title="Pass rate",
    )
