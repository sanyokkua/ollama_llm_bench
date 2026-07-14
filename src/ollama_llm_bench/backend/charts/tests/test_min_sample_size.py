"""The minimum-sample-size guard (`13_CHART_AGGREGATORS.md` §6.5a)."""

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    ChartData,
    ChartFilters,
    ChartKind,
    RunMode,
)

_PROVIDER_LOW_ID = "11111111-1111-4111-8111-111111111111"
_PROVIDER_HIGH_ID = "22222222-2222-4222-8222-222222222222"
_MODEL_LOW = "model-low"
_MODEL_HIGH = "model-high"
_MIN_SAMPLE_SIZE = 5


def _rows_for_low_and_high_sample_groups() -> tuple[BenchmarkResult, ...]:
    low_sample_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_LOW_ID,
            model_name=_MODEL_LOW,
            ttft_ms=100,
        )
        for index in range(1, 4)  # n = 3, below the threshold of 5
    )
    high_sample_rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_HIGH_ID,
            model_name=_MODEL_HIGH,
            ttft_ms=100,
        )
        for index in range(4, 10)  # n = 6, at/above the threshold of 5
    )
    return low_sample_rows + high_sample_rows


def test_low_sample_group_is_flagged() -> None:
    """Proves: STORY-033-AC-4

    Given one per-model group whose completed-row count `n` is below
    `eval.min_sample_size` and one group at or above it, when
    `AVG_TTFT_PER_MODEL` (kind 1) is computed, then the low-sample group
    carries `low_sample_flags[i] is True` with its correct `n`, and the
    well-sampled group carries `False` (§6.5a).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = _rows_for_low_and_high_sample_groups()

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
        min_sample_size=_MIN_SAMPLE_SIZE,
    )

    # Assert
    assert isinstance(result, ChartData)
    series = result.series[0]
    assert series.sample_sizes == (3, 6)
    assert series.low_sample_flags == (True, False)


def test_success_failed_incomplete_stacked_leaves_sample_sizes_empty() -> None:
    """Proves: STORY-033-AC-4

    Given the same working set, when `SUCCESS_FAILED_INCOMPLETE_STACKED`
    (kind 4, a row-level raw count chart) is computed, then its series carry
    no `sample_sizes`/`low_sample_flags` — the guard applies only to
    per-model and per-`(category, model)` statistical aggregates (§6.5a).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = _rows_for_low_and_high_sample_groups()

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
        min_sample_size=_MIN_SAMPLE_SIZE,
    )

    # Assert
    assert isinstance(result, ChartData)
    assert all(series.sample_sizes == () for series in result.series)
    assert all(series.low_sample_flags == () for series in result.series)


def test_time_vs_tokens_scatter_leaves_sample_sizes_empty() -> None:
    """Proves: STORY-033-AC-4

    Given the same working set with `completion_tokens`/`total_time_ms`
    populated, when `TIME_VS_TOKENS_SCATTER` (kind 8, a per-row point cloud)
    is computed, then its series carry no `sample_sizes`/`low_sample_flags`
    — the guard does not apply to a per-row series (§6.5a).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_LOW_ID,
            model_name=_MODEL_LOW,
            completion_tokens=100,
            total_time_ms=2000,
        )
        for index in range(1, 3)
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.TIME_VS_TOKENS_SCATTER,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
        min_sample_size=_MIN_SAMPLE_SIZE,
    )

    # Assert
    assert isinstance(result, ChartData)
    assert all(series.sample_sizes == () for series in result.series)
    assert all(series.low_sample_flags == () for series in result.series)


def test_heatmap_task_by_model_carries_no_sample_size_concept() -> None:
    """Proves: STORY-033-AC-4

    Given the same working set with verdicts populated, when
    `HEATMAP_TASK_BY_MODEL` (kind 9, a cell-level structure) is computed,
    then the resulting `HeatmapData` carries no `sample_sizes`/
    `low_sample_flags` field at all — the guard's data shape does not exist
    on the heatmap DTO (§6.5a).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = _rows_for_low_and_high_sample_groups()

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.HEATMAP_TASK_BY_MODEL,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(),
        min_sample_size=_MIN_SAMPLE_SIZE,
    )

    # Assert
    assert not hasattr(result, "sample_sizes")
    assert not hasattr(result, "low_sample_flags")
