"""`SUCCESS_FAILED_INCOMPLETE_STACKED` — kind 4 (`13_CHART_AGGREGATORS.md` §7.4)."""

from collections.abc import Callable, Mapping

from ollama_llm_bench.backend.charts._internal import pipeline
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    ChartSeries,
    ResultStatus,
    TaskId,
)

_EMPTY_MESSAGE = "No results yet."

_FAILED_STATUSES = frozenset(
    {
        ResultStatus.FAILED_INFERENCE,
        ResultStatus.FAILED_PROVIDER,
        ResultStatus.FAILED_TIMEOUT,
        ResultStatus.FAILED_JUDGE_TIMEOUT,
        ResultStatus.ERRORED,
    }
)
_INCOMPLETE_STATUSES = frozenset(
    {
        ResultStatus.PENDING,
        ResultStatus.RUNNING_INFERENCE,
        ResultStatus.AWAITING_KEYWORD_CHECK,
        ResultStatus.AWAITING_COSINE_CHECK,
        ResultStatus.AWAITING_JUDGE_CHECK,
    }
)


def compute_success_failed_incomplete_stacked(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Per-model Succeeded/Failed/Incomplete counts over every surviving row (§7.4).

    Row-level counts, so no minimum-sample-size guard applies (§6.5a).
    """
    del tasks_by_id, min_sample_size
    hidden = _hidden_series(filters)

    if not rows:
        return pipeline.empty_chart_data(
            ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED, message=_EMPTY_MESSAGE
        )

    groups = pipeline.group_by_model(rows)
    categories = tuple(group.label for group in groups)
    succeeded = [
        _count(group.rows, lambda r: r.status == ResultStatus.COMPLETED) for group in groups
    ]
    failed = [_count(group.rows, lambda r: r.status in _FAILED_STATUSES) for group in groups]
    incomplete = [
        _count(group.rows, lambda r: r.status in _INCOMPLETE_STATUSES) for group in groups
    ]

    series = tuple(
        ChartSeries(name=name, values=tuple(values))
        for name, values in (
            ("Succeeded", succeeded),
            ("Failed", failed),
            ("Incomplete", incomplete),
        )
        if name not in hidden
    )
    return ChartData(
        chart_kind=ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
        categories=categories,
        series=series,
        x_axis_title="Model",
        y_axis_title="Task count",
    )


def _count(
    group_rows: tuple[BenchmarkResult, ...], predicate: Callable[[BenchmarkResult], bool]
) -> float:
    return float(sum(1 for row in group_rows if predicate(row)))


def _hidden_series(filters: ChartFilters) -> frozenset[str]:
    raw = filters.options.get("hidden_series")
    if isinstance(raw, str) and raw:
        return frozenset(raw.split(","))
    return frozenset()
