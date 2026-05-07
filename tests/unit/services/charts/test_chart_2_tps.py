"""Unit tests for Chart2TpsAggregator — average tokens-per-second per model."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart2TpsAggregator


def test_chart2_basic_avg(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", tokens_per_second=10.0),
        make_result(model_name="a", tokens_per_second=20.0),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: mean of [10, 20] = 15.0
    assert abs(data.series_data[0][0] - 15.0) < 0.01


def test_chart2_excludes_zero_tps(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", tokens_per_second=10.0),
        make_result(model_name="a", tokens_per_second=0.0),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: zero-TPS row excluded; only 10.0 counts
    assert data.series_data[0][0] == 10.0


def test_chart2_excludes_null_tps(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", tokens_per_second=30.0),
        make_result(model_name="a", tokens_per_second=None),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.series_data[0][0] == 30.0


def test_chart2_all_null_returns_empty_state(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", tokens_per_second=None)]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart2_sorted_descending_by_mean(make_result, all_filters) -> None:
    # Arrange: "b" is faster — expect "b" first (descending)
    results = [
        make_result(model_name="a", tokens_per_second=5.0),
        make_result(model_name="b", tokens_per_second=50.0),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.category_labels[0] == "b"
    assert data.category_labels[1] == "a"


def test_chart2_inference_error_rows_excluded(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", tokens_per_second=100.0, has_inference_error=True),
        make_result(model_name="a", tokens_per_second=10.0),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: error row excluded; only 10.0 counts
    assert abs(data.series_data[0][0] - 10.0) < 0.01


def test_chart2_footnote_present_when_rows_excluded(make_result, all_filters) -> None:
    # Arrange: one zero-TPS row triggers exclusion footnote
    results = [
        make_result(model_name="a", tokens_per_second=10.0),
        make_result(model_name="a", tokens_per_second=0.0),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "Excluded" in data.footnote
