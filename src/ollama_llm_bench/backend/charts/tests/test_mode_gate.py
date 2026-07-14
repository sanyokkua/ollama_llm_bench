"""The grading-chart mode gate (`13_CHART_AGGREGATORS.md` §6.1)."""

import pytest

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    RunMode,
    Verdict,
)

_MODE_GATE_MESSAGE = "This chart is available only for graded runs."
_GRADING_KINDS = (
    ChartKind.PASS_RATE_BY_MODEL,
    ChartKind.AVG_COSINE_BY_MODEL,
    ChartKind.VERDICT_COUNTS_STACKED,
    ChartKind.HEATMAP_TASK_BY_MODEL,
    ChartKind.PER_CATEGORY_BAR,
    ChartKind.SPEED_VS_QUALITY_SCATTER,
)


def _is_structurally_empty_with_no_theme_colour(result: ChartData | HeatmapData) -> bool:
    """Return whether `result` carries no series/cells and — for `ChartData` —
    no series with a non-`None` `color_hint` (EC-RES-4: the aggregator never
    resolves a theme colour, only an optional raw hint string)."""
    if isinstance(result, HeatmapData):
        return not result.cells
    return not result.series and all(series.color_hint is None for series in result.series)


@pytest.mark.parametrize("chart_kind", _GRADING_KINDS, ids=lambda kind: kind.value)
@pytest.mark.parametrize("run_mode", [RunMode.SYNTHETIC, RunMode.TASKS], ids=["synthetic", "tasks"])
def test_grading_chart_in_non_graded_mode_is_empty_state(
    chart_kind: ChartKind, run_mode: RunMode
) -> None:
    """Proves: STORY-033-AC-6

    Given each of the six grading-only chart kinds requested for a
    `SYNTHETIC` or `TASKS` run, when the aggregator runs, then it returns
    the empty-state structure with `"This chart is available only for
    graded runs."` and performs no further aggregation work — a fully
    populated but ungraded row set is supplied so a non-empty result would
    prove the mode gate did not fire first (§6.1, CA-8). The returned
    structure also carries no theme-resolved colour, only a raw
    `color_hint` or `None` (EC-RES-4).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    row = make_benchmark_result(verdict=Verdict.PASS, cosine_similarity=0.9)

    # Act
    result = aggregator.compute(
        chart_kind=chart_kind,
        run_mode=run_mode,
        results=(row,),
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result.empty_state_message == _MODE_GATE_MESSAGE
    assert _is_structurally_empty_with_no_theme_colour(result)
