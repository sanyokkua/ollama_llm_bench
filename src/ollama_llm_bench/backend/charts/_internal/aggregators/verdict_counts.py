"""`VERDICT_COUNTS_STACKED` — kind 7 (`13_CHART_AGGREGATORS.md` §7.7)."""

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


def compute_verdict_counts_stacked(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Per-model Pass/Fail/Ungraded verdict counts (§7.7, CA-14).

    Row-level counts, so no minimum-sample-size guard applies (§6.5a) — the
    same reasoning as kind 4's raw status counts.
    """
    del tasks_by_id, min_sample_size
    hidden = _hidden_series(filters)

    if not rows:
        return pipeline.empty_chart_data(ChartKind.VERDICT_COUNTS_STACKED, message=_EMPTY_MESSAGE)

    groups = pipeline.group_by_model(rows)
    categories = tuple(group.label for group in groups)
    passed = [
        float(sum(1 for row in group.rows if row.verdict == Verdict.PASS)) for group in groups
    ]
    failed = [
        float(sum(1 for row in group.rows if row.verdict == Verdict.FAIL)) for group in groups
    ]
    ungraded = [float(sum(1 for row in group.rows if row.verdict is None)) for group in groups]

    series = tuple(
        ChartSeries(name=name, values=tuple(values))
        for name, values in (("Pass", passed), ("Fail", failed), ("Ungraded", ungraded))
        if name not in hidden
    )
    return ChartData(
        chart_kind=ChartKind.VERDICT_COUNTS_STACKED,
        categories=categories,
        series=series,
        x_axis_title="Model",
        y_axis_title="Result count",
    )


def _hidden_series(filters: ChartFilters) -> frozenset[str]:
    raw = filters.options.get("hidden_series")
    if isinstance(raw, str) and raw:
        return frozenset(raw.split(","))
    return frozenset()
