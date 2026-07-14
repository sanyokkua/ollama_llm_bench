"""`AVG_TPS_PER_MODEL` — kind 2 (`13_CHART_AGGREGATORS.md` §7.2)."""

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

_EMPTY_MESSAGE = "No completed inferences yet."
_AGGREGATION_DOMAIN = ("mean", "median")


def compute_avg_tps_per_model(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """Mean or median `tokens_per_second` per model (§7.2, SPEC-047, SPEC-093, MISS-08).

    Each model's group carries its own `estimated_flags`/`reasoning_flags` entry
    (parallel to `values`) rather than a single series-wide hint, so the UI can
    mark the `≈`/`⧉` markers on exactly the model(s) whose group includes a
    `tokens_estimated`/`has_thinking_block` row — not the first model in the
    series to have either flag.
    """
    del tasks_by_id
    aggregation = pipeline.read_enum_option(
        filters,
        key="aggregation",
        domain=_AGGREGATION_DOMAIN,
        default="mean",
        chart_kind=ChartKind.AVG_TPS_PER_MODEL,
    )

    categories: list[str] = []
    values: list[float | None] = []
    estimated_flags: list[bool] = []
    reasoning_flags: list[bool] = []
    sample_sizes: list[int] = []
    low_sample_flags: list[bool] = []
    for group in pipeline.group_by_model(rows):
        tps_rows = [row for row in group.rows if row.tokens_per_second is not None]
        if not tps_rows:
            continue
        tps_values = [float(row.tokens_per_second) for row in tps_rows if row.tokens_per_second]
        statistic = (
            statistics.median(tps_values)
            if aggregation == "median"
            else statistics.mean(tps_values)
        )
        categories.append(group.label)
        values.append(statistic)
        estimated_flags.append(any(row.tokens_estimated for row in tps_rows))
        reasoning_flags.append(any(row.has_thinking_block for row in tps_rows))
        n = len(tps_rows)
        sample_sizes.append(n)
        low_sample_flags.append(pipeline.sample_flag(n, min_sample_size))

    if not values:
        return pipeline.empty_chart_data(ChartKind.AVG_TPS_PER_MODEL, message=_EMPTY_MESSAGE)

    series = ChartSeries(
        name="Avg TPS",
        values=tuple(values),
        sample_sizes=tuple(sample_sizes),
        low_sample_flags=tuple(low_sample_flags),
        estimated_flags=tuple(estimated_flags),
        reasoning_flags=tuple(reasoning_flags),
    )
    return ChartData(
        chart_kind=ChartKind.AVG_TPS_PER_MODEL,
        categories=tuple(categories),
        series=(series,),
        x_axis_title="Model",
        y_axis_title="Tokens per second",
        value_unit="tok/s",
    )
