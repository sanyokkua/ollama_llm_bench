"""The per-chart `COMPLETED`-status pre-filter (`13_CHART_AGGREGATORS.md` §6.3)."""

import pytest

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.protocols import ChartAggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkTask,
    ChartData,
    ChartFilters,
    ChartKind,
    HeatmapData,
    ResultStatus,
    RunMode,
    Verdict,
)

_PROVIDER_A_ID = "11111111-1111-4111-8111-111111111111"
_PROVIDER_B_ID = "22222222-2222-4222-8222-222222222222"
_MODEL_A = "model-a"
_MODEL_B = "model-b"
_RUN_MODE_FOR_KIND = {
    ChartKind.AVG_TTFT_PER_MODEL: RunMode.TASKS,
    ChartKind.AVG_TPS_PER_MODEL: RunMode.TASKS,
    ChartKind.AVG_TIME_PER_MODEL: RunMode.TASKS,
    ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED: RunMode.TASKS,
    ChartKind.PASS_RATE_BY_MODEL: RunMode.GRADED,
    ChartKind.AVG_COSINE_BY_MODEL: RunMode.GRADED,
    ChartKind.VERDICT_COUNTS_STACKED: RunMode.GRADED,
    ChartKind.TIME_VS_TOKENS_SCATTER: RunMode.TASKS,
    ChartKind.HEATMAP_TASK_BY_MODEL: RunMode.GRADED,
    ChartKind.PER_CATEGORY_BAR: RunMode.GRADED,
    ChartKind.SPEED_VS_QUALITY_SCATTER: RunMode.GRADED,
    ChartKind.TOKENS_PER_TASK_BOX: RunMode.TASKS,
}


def _baseline_rows_and_task() -> tuple[tuple[BenchmarkResult, ...], BenchmarkTask]:
    """Two `COMPLETED` rows for two different models, both carrying every
    chart-relevant field, joined to one categorized task."""
    task = make_benchmark_task(category="Cat", task_order=0)
    row_a = make_benchmark_result(
        result_id=1,
        provider_id=_PROVIDER_A_ID,
        model_name=_MODEL_A,
        status=ResultStatus.COMPLETED,
        verdict=Verdict.PASS,
        ttft_ms=100,
        total_time_ms=1000,
        completion_tokens=50,
        tokens_per_second=40.0,
        cosine_similarity=0.9,
    )
    row_b = make_benchmark_result(
        result_id=2,
        provider_id=_PROVIDER_B_ID,
        model_name=_MODEL_B,
        status=ResultStatus.COMPLETED,
        verdict=Verdict.PASS,
        ttft_ms=110,
        total_time_ms=1100,
        completion_tokens=55,
        tokens_per_second=42.0,
        cosine_similarity=0.8,
    )
    return (row_a, row_b), task


def _extra_non_completed_row(result_id: int, status: ResultStatus) -> BenchmarkResult:
    """A row for model A whose every chart-relevant field differs sharply from
    `row_a` above, so that its inclusion — were it not pre-filtered away —
    would change every aggregator's summary."""
    return make_benchmark_result(
        result_id=result_id,
        provider_id=_PROVIDER_A_ID,
        model_name=_MODEL_A,
        status=status,
        verdict=Verdict.PASS,
        ttft_ms=9990,
        total_time_ms=99900,
        completion_tokens=9990,
        tokens_per_second=999.0,
        cosine_similarity=0.1,
    )


def _compute(
    aggregator: ChartAggregator,
    *,
    chart_kind: ChartKind,
    rows: tuple[BenchmarkResult, ...],
    task: BenchmarkTask,
) -> ChartData | HeatmapData:
    return aggregator.compute(
        chart_kind=chart_kind,
        run_mode=_RUN_MODE_FOR_KIND[chart_kind],
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
    )


@pytest.mark.parametrize(
    "chart_kind",
    [
        ChartKind.AVG_TTFT_PER_MODEL,
        ChartKind.AVG_TPS_PER_MODEL,
        ChartKind.AVG_TIME_PER_MODEL,
        ChartKind.PASS_RATE_BY_MODEL,
        ChartKind.AVG_COSINE_BY_MODEL,
        ChartKind.VERDICT_COUNTS_STACKED,
        ChartKind.TIME_VS_TOKENS_SCATTER,
        ChartKind.HEATMAP_TASK_BY_MODEL,
        ChartKind.PER_CATEGORY_BAR,
        ChartKind.SPEED_VS_QUALITY_SCATTER,
        ChartKind.TOKENS_PER_TASK_BOX,
    ],
    ids=lambda kind: kind.value,
)
def test_status_prefilter_per_chart_kind(chart_kind: ChartKind) -> None:
    """Proves: STORY-033-AC-3

    Given a working set of two `COMPLETED` rows (kinds 1, 2, 3, 5, 6, 7, 8,
    9, 10, 11, 12), when a third, sharply different-valued
    `FAILED_INFERENCE` row for the same model is added, then the
    aggregator's output is unchanged — the non-`COMPLETED` row never
    contributes to the summary (§6.3, CA-6).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    baseline_rows, task = _baseline_rows_and_task()
    extra_row = _extra_non_completed_row(3, ResultStatus.FAILED_INFERENCE)

    # Act
    baseline_result = _compute(aggregator, chart_kind=chart_kind, rows=baseline_rows, task=task)
    with_failed_result = _compute(
        aggregator, chart_kind=chart_kind, rows=(*baseline_rows, extra_row), task=task
    )

    # Assert
    assert baseline_result == with_failed_result


def test_status_prefilter_keeps_every_row_for_status_count_chart() -> None:
    """Proves: STORY-033-AC-3

    Given the same working set, when a third, non-`COMPLETED` row for model
    A is added, then `SUCCESS_FAILED_INCOMPLETE_STACKED` (kind 4) counts it
    into model A's *Failed* series — every surviving row contributes,
    counting failures is the point of the chart (§6.3, CA-6).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    baseline_rows, task = _baseline_rows_and_task()
    extra_row = _extra_non_completed_row(3, ResultStatus.FAILED_INFERENCE)

    # Act
    result = _compute(
        aggregator,
        chart_kind=ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
        rows=(*baseline_rows, extra_row),
        task=task,
    )

    # Assert
    assert isinstance(result, ChartData)
    failed_series = next(series for series in result.series if series.name == "Failed")
    assert failed_series.values == (1.0, 0.0)
