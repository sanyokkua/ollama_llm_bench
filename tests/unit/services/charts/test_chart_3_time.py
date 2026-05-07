"""Unit tests for Chart3TimeAggregator — total inference time per model."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart3TimeAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart3_basic_avg(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", total_time_ms=100),
        make_result(model_name="a", total_time_ms=200),
    ]

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: mean of [100, 200] = 150.0
    assert abs(data.series_data[0][0] - 150.0) < 0.01


def test_chart3_outlier_toggle_reduces_average(make_result, all_filters) -> None:
    # Arrange: 10 values 1..10, top 10% = 1 value dropped (10)
    results = [make_result(model_name="a", total_time_ms=i) for i in range(1, 11)]
    agg = Chart3TimeAggregator()

    # Act — without outlier exclusion
    data_normal = agg.compute_data(run=None, results=results, filters=all_filters(results))

    # Act — with outlier exclusion
    filters_with_outlier = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"exclude_outliers": True},
    )
    data_trimmed = agg.compute_data(run=None, results=results, filters=filters_with_outlier)

    # Assert: trimmed mean must be lower than full mean
    assert data_trimmed.series_data[0][0] < data_normal.series_data[0][0]


def test_chart3_outlier_footnote_present_when_enabled(make_result) -> None:
    # Arrange: 10 values so at least 1 is dropped
    results = [make_result(model_name="a", total_time_ms=i * 100) for i in range(1, 11)]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"exclude_outliers": True},
    )

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert
    assert "Dropped" in data.footnote


def test_chart3_no_outlier_no_footnote(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", total_time_ms=100)]

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: no rows dropped, footnote empty
    assert data.footnote == ""


def test_chart3_null_total_time_excluded(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", total_time_ms=500),
        make_result(model_name="a", total_time_ms=None),
    ]

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: only the 500ms row counts
    assert abs(data.series_data[0][0] - 500.0) < 0.01


def test_chart3_per_run_filter_isolation(make_result, all_filters) -> None:
    # Two ChartFilters instances on same data must not share state
    results = [
        make_result(model_name="a", total_time_ms=100),
        make_result(model_name="b", total_time_ms=200),
    ]
    agg = Chart3TimeAggregator()
    f1 = all_filters(results)
    f2 = all_filters(results)

    # Act
    d1 = agg.compute_data(run=None, results=results, filters=f1)
    d2 = agg.compute_data(run=None, results=results, filters=f2)

    # Assert: identical filters produce identical outputs
    assert d1.series_data == d2.series_data


def test_chart3_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart3_sorted_ascending_by_mean(make_result, all_filters) -> None:
    # Arrange: "fast" model should appear first
    results = [
        make_result(model_name="slow", total_time_ms=1000),
        make_result(model_name="fast", total_time_ms=10),
    ]

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.category_labels[0] == "fast"
