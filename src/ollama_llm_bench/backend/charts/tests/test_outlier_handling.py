"""The IQR x 1.5 outlier rule and the box-plot exception (`13_CHART_AGGREGATORS.md` §6.6)."""

import pytest

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

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "model-a"

# A cluster of clean values plus one long-tail outlier, the same shape used by
# `test_chart_snapshots.py`'s box-plot fixture — the outlier (1000) sits well
# beyond `Q3 + 1.5*IQR` computed from the full set.
_TTFT_VALUES_WITH_OUTLIER = (10, 12, 14, 16, 18, 20, 1000)
_MEAN_WITH_OUTLIER = sum(_TTFT_VALUES_WITH_OUTLIER) / len(_TTFT_VALUES_WITH_OUTLIER)
_MEAN_WITHOUT_OUTLIER = sum(_TTFT_VALUES_WITH_OUTLIER[:-1]) / (len(_TTFT_VALUES_WITH_OUTLIER) - 1)


def _rows_with_outlier() -> tuple[BenchmarkResult, ...]:
    return tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            ttft_ms=value,
        )
        for index, value in enumerate(_TTFT_VALUES_WITH_OUTLIER, start=1)
    )


@pytest.mark.parametrize(
    "drop_outliers,expected_mean",
    [
        pytest.param(True, _MEAN_WITHOUT_OUTLIER, id="toggle_on_excludes_outlier"),
        pytest.param(False, _MEAN_WITH_OUTLIER, id="toggle_off_includes_outlier"),
    ],
)
def test_iqr_outlier_dropped_when_toggle_on_box_plot_keeps(
    drop_outliers: bool,  # noqa: FBT001  # pytest.mark.parametrize table column, not a call-site flag
    expected_mean: float,
) -> None:
    """Proves: STORY-033-AC-5

    Given a group containing one value beyond `Q3 + 1.5*IQR`, when
    `AVG_TTFT_PER_MODEL` (kind 1, an outlier-toggle chart) runs with the
    toggle on, then the outlier is excluded from the group's mean; with the
    toggle off, the outlier is included (§6.6, CA-5).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = _rows_with_outlier()

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(options={"drop_outliers": drop_outliers}),
    )

    # Assert
    assert isinstance(result, ChartData)
    assert result.series[0].values[0] == expected_mean


def test_box_plot_geometry_excludes_outlier_but_never_drops_it_from_group() -> None:
    """Proves: STORY-033-AC-5

    Given the same outlier-bearing group, when `TOKENS_PER_TASK_BOX`
    (kind 12) runs with *Show outliers* ON, then the five-number summary is
    computed over the non-outlier values only, and the outlier is never
    dropped from the model — it is emitted in a separate outlier series
    with its `result_id` (§6.6, §7.12, CA-23).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            completion_tokens=value,
        )
        for index, value in enumerate(_TTFT_VALUES_WITH_OUTLIER, start=1)
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.TOKENS_PER_TASK_BOX,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(options={"show_outliers": True}),
    )

    # Assert
    assert isinstance(result, ChartData)
    max_series = next(series for series in result.series if series.name == "max")
    outlier_series = next(series for series in result.series if series.name.endswith("(outliers)"))
    assert max_series.values == (20.0,)
    assert outlier_series.values == (1000.0,)
    assert outlier_series.result_ids == (7,)


def test_box_plot_outlier_toggle_off_emits_no_outlier_series() -> None:
    """Proves: STORY-033-AC-5

    Given the same outlier-bearing group, when `TOKENS_PER_TASK_BOX`
    (kind 12) runs with *Show outliers* OFF, then no outlier series is
    emitted and the box geometry is unchanged (§7.12, CA-24).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = tuple(
        make_benchmark_result(
            result_id=index,
            provider_id=_PROVIDER_ID,
            model_name=_MODEL_NAME,
            completion_tokens=value,
        )
        for index, value in enumerate(_TTFT_VALUES_WITH_OUTLIER, start=1)
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.TOKENS_PER_TASK_BOX,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(options={"show_outliers": False}),
    )

    # Assert
    assert isinstance(result, ChartData)
    assert not any(series.name.endswith("(outliers)") for series in result.series)
    max_series = next(series for series in result.series if series.name == "max")
    assert max_series.values == (20.0,)
