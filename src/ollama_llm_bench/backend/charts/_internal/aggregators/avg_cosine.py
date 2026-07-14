"""`AVG_COSINE_BY_MODEL` — kind 6 (`13_CHART_AGGREGATORS.md` §7.6)."""

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
)

_EMPTY_MESSAGE = "No verdicts yet — this run has not reached the cosine stage."


def compute_avg_cosine_by_model(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Mean `cosine_similarity` per model (§7.6, CA-12, CA-13).

    The DD-63 partial-coverage `⚠` flag needs `eval.min_cosine_coverage`, a
    Settings value this Qt-free module has no dependency on
    (`01_MODULE_INVENTORY.md` §4.5); it is left uncomputed here and layered on
    by the future ResultGateway that resolves Settings.
    """
    del tasks_by_id
    fold_ungraded_as_zero = pipeline.read_bool_option(
        filters,
        key="fold_ungraded_as_zero",
        default=False,
        chart_kind=ChartKind.AVG_COSINE_BY_MODEL,
    )

    categories: list[str] = []
    values: list[float | None] = []
    sample_sizes: list[int] = []
    low_sample_flags: list[bool] = []
    for group in pipeline.group_by_model(rows):
        if fold_ungraded_as_zero:
            cosine_values = [
                float(row.cosine_similarity) if row.cosine_similarity is not None else 0.0
                for row in group.rows
            ]
        else:
            cosine_values = [
                float(row.cosine_similarity)
                for row in group.rows
                if row.cosine_similarity is not None
            ]
        if not cosine_values:
            continue
        categories.append(group.label)
        values.append(statistics.mean(cosine_values))
        n = len(cosine_values)
        sample_sizes.append(n)
        low_sample_flags.append(pipeline.sample_flag(n, min_sample_size))

    if not values:
        return pipeline.empty_chart_data(ChartKind.AVG_COSINE_BY_MODEL, message=_EMPTY_MESSAGE)

    series = ChartSeries(
        name="Avg Cosine Score",
        values=tuple(values),
        sample_sizes=tuple(sample_sizes),
        low_sample_flags=tuple(low_sample_flags),
    )
    return ChartData(
        chart_kind=ChartKind.AVG_COSINE_BY_MODEL,
        categories=tuple(categories),
        series=(series,),
        x_axis_title="Model",
        y_axis_title="Cosine Score",
    )
