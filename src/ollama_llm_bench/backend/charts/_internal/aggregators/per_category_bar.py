"""`PER_CATEGORY_BAR` — kind 10 (`13_CHART_AGGREGATORS.md` §7.10).

Representation note: `categories` holds the distinct task-category labels (one
group per category, ascending); each model contributes one `ChartSeries`
aligned to that category axis, `None` where the model has no rows in a
category — the standard grouped-bar shape (§5 postcondition).
"""

from collections.abc import Mapping
import statistics

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

_EMPTY_MESSAGE = "No task in this run has a category set."
_METRIC_DOMAIN = ("pass_rate", "avg_cosine", "avg_time", "avg_tps")


def compute_per_category_bar(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """One category-group per `BenchmarkTask.category`, one series per model (§7.10, CA-19, CA-20)."""
    metric = pipeline.read_enum_option(
        filters,
        key="metric",
        domain=_METRIC_DOMAIN,
        default="pass_rate",
        chart_kind=ChartKind.PER_CATEGORY_BAR,
    )
    categories_filter = filters.categories

    groups = pipeline.group_by_category_and_model(rows, tasks_by_id)
    if categories_filter:
        groups = tuple(group for group in groups if group.category in categories_filter)
    if not groups:
        return pipeline.empty_chart_data(ChartKind.PER_CATEGORY_BAR, message=_EMPTY_MESSAGE)

    category_labels = tuple(sorted({group.category for group in groups}))
    models = tuple(
        sorted({group.descriptor for group in groups}, key=lambda d: (d.provider_id, d.model_name))
    )
    labels_by_model = {group.descriptor: group.label for group in groups}
    by_key = {(group.category, group.descriptor): group for group in groups}

    series: list[ChartSeries] = []
    for model in models:
        values: list[float | None] = []
        sample_sizes: list[int] = []
        low_sample_flags: list[bool] = []
        for category in category_labels:
            group = by_key.get((category, model))
            if group is None:
                values.append(None)
                sample_sizes.append(0)
                low_sample_flags.append(True)
                continue
            values.append(_metric_value(group.rows, metric))
            n = len(group.rows)
            sample_sizes.append(n)
            low_sample_flags.append(pipeline.sample_flag(n, min_sample_size))
        series.append(
            ChartSeries(
                name=labels_by_model[model],
                values=tuple(values),
                sample_sizes=tuple(sample_sizes),
                low_sample_flags=tuple(low_sample_flags),
            )
        )

    return ChartData(
        chart_kind=ChartKind.PER_CATEGORY_BAR,
        categories=category_labels,
        series=tuple(series),
        x_axis_title="Category",
        y_axis_title=_metric_axis_title(metric),
    )


def _metric_value(group_rows: tuple[BenchmarkResult, ...], metric: str) -> float | None:
    if metric == "pass_rate":
        return sum(1 for row in group_rows if row.verdict == Verdict.PASS) / len(group_rows)
    if metric == "avg_cosine":
        values = [row.cosine_similarity for row in group_rows if row.cosine_similarity is not None]
        return statistics.mean(values) if values else None
    if metric == "avg_time":
        values = [row.total_time_ms / 1000.0 for row in group_rows if row.total_time_ms is not None]
        return statistics.mean(values) if values else None
    values = [row.tokens_per_second for row in group_rows if row.tokens_per_second is not None]
    return statistics.mean(values) if values else None


def _metric_axis_title(metric: str) -> str:
    return {
        "pass_rate": "Pass rate",
        "avg_cosine": "Avg Cosine Score",
        "avg_time": "Avg time (s)",
        "avg_tps": "Avg tokens/sec",
    }[metric]
