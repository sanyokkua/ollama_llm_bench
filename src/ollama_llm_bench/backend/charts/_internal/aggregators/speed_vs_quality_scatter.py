"""`SPEED_VS_QUALITY_SCATTER` — kind 11 (`13_CHART_AGGREGATORS.md` §7.11).

Representation note: unlike kind 8, this chart plots exactly **one** point per
model, so it fits the standard grouped shape — `categories` holds the model
labels and two aligned `ChartSeries` ("Tokens/sec", the Y-metric name) carry
`x`/`y` per model. `pareto_points` carries the frontier as `(x, y)` pairs,
sorted ascending `x`, per the domain `ChartData.pareto_points` field.
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

_EMPTY_MESSAGE = "Speed vs quality needs at least two models with completed verdicts."
_Y_METRIC_DOMAIN = ("pass_rate", "avg_cosine")
_MIN_MODELS_FOR_FRONTIER = 2


def compute_speed_vs_quality_scatter(
    *,
    rows: tuple[BenchmarkResult, ...],
    tasks_by_id: Mapping[TaskId, BenchmarkTask],
    filters: ChartFilters,
    min_sample_size: int,
) -> ChartData:
    """One point per model — mean TPS vs pass rate/avg cosine — plus the Pareto frontier (§7.11, CA-21, CA-22)."""
    del tasks_by_id
    y_metric = pipeline.read_enum_option(
        filters,
        key="y_metric",
        domain=_Y_METRIC_DOMAIN,
        default="pass_rate",
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
    )

    points: list[tuple[str, float, float, int]] = []
    for group in pipeline.group_by_model(rows):
        graded_rows = [row for row in group.rows if row.verdict is not None]
        if not graded_rows:
            continue
        tps_values = [
            row.tokens_per_second for row in group.rows if row.tokens_per_second is not None
        ]
        x_value = statistics.mean(tps_values) if tps_values else 0.0
        y_value = _y_value(group.rows, y_metric)
        points.append((group.label, x_value, y_value, len(graded_rows)))

    if len(points) < _MIN_MODELS_FOR_FRONTIER:
        return pipeline.empty_chart_data(ChartKind.SPEED_VS_QUALITY_SCATTER, message=_EMPTY_MESSAGE)

    categories = tuple(label for label, _x, _y, _n in points)
    x_series = tuple(x for _label, x, _y, _n in points)
    y_series = tuple(y for _label, _x, y, _n in points)
    sample_sizes = tuple(n for _label, _x, _y, n in points)
    low_sample_flags = tuple(pipeline.sample_flag(n, min_sample_size) for n in sample_sizes)

    frontier = _pareto_frontier([(x, y) for _label, x, y, _n in points])

    return ChartData(
        chart_kind=ChartKind.SPEED_VS_QUALITY_SCATTER,
        categories=categories,
        series=(
            ChartSeries(
                name="Tokens/sec",
                values=x_series,
                sample_sizes=sample_sizes,
                low_sample_flags=low_sample_flags,
            ),
            ChartSeries(
                name=_y_axis_title(y_metric),
                values=y_series,
                sample_sizes=sample_sizes,
                low_sample_flags=low_sample_flags,
            ),
        ),
        x_axis_title="Tokens/sec",
        y_axis_title=_y_axis_title(y_metric),
        pareto_points=frontier,
    )


def _y_value(group_rows: tuple[BenchmarkResult, ...], y_metric: str) -> float:
    if y_metric == "avg_cosine":
        values = [row.cosine_similarity for row in group_rows if row.cosine_similarity is not None]
        return statistics.mean(values) if values else 0.0
    return sum(1 for row in group_rows if row.verdict == Verdict.PASS) / len(group_rows)


def _y_axis_title(y_metric: str) -> str:
    return "Avg Cosine Score" if y_metric == "avg_cosine" else "Pass rate"


def _pareto_frontier(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    frontier = [
        point
        for point in points
        if not any(
            other != point and other[0] > point[0] and other[1] > point[1] for other in points
        )
    ]
    return tuple(sorted(frontier, key=lambda point: point[0]))
