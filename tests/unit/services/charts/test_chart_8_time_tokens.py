"""Unit tests for Chart8TimeTokensAggregator — completion tokens vs total time scatter."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart8TimeTokensAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart8_basic_scatter(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", completion_tokens=50, total_time_ms=2000)]

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: one scatter point with correct coordinates
    assert len(data.scatter_points) == 1
    x, y, label = data.scatter_points[0]
    assert x == 50.0
    assert abs(y - 2.0) < 0.01  # 2000ms → 2.0s
    assert label == "a"


def test_chart8_log_scale_flag_propagated(make_result) -> None:
    # Arrange
    results = [make_result(model_name="a", completion_tokens=100, total_time_ms=1000)]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"log_scale": True},
    )

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: log_scale is passed through in extra
    assert data.extra.get("log_scale") is True


def test_chart8_log_scale_false_by_default(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", completion_tokens=100, total_time_ms=500)]

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.extra.get("log_scale") is False


def test_chart8_multiple_rows_averaged_per_model(make_result, all_filters) -> None:
    # Arrange: two rows for model "a" — should produce one averaged scatter point
    results = [
        make_result(model_name="a", completion_tokens=100, total_time_ms=1000),
        make_result(model_name="a", completion_tokens=200, total_time_ms=3000),
    ]

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: one point, averaged values
    assert len(data.scatter_points) == 1
    x, y, _label = data.scatter_points[0]
    assert abs(x - 150.0) < 0.01  # avg tokens
    assert abs(y - 2.0) < 0.01  # avg time_s: (1+3)/2 = 2.0


def test_chart8_inference_error_rows_excluded(make_result, all_filters) -> None:
    # Arrange: one error row with huge time — should not distort the result
    results = [
        make_result(model_name="a", completion_tokens=50, total_time_ms=100, has_inference_error=True),
        make_result(model_name="a", completion_tokens=50, total_time_ms=500),
    ]

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    _x, y, _ = data.scatter_points[0]

    # Assert: only the 500ms row is included
    assert abs(y - 0.5) < 0.01


def test_chart8_null_tokens_excluded(make_result, all_filters) -> None:
    # Arrange: one row with null completion_tokens
    results = [
        make_result(model_name="a", completion_tokens=None, total_time_ms=100),
        make_result(model_name="a", completion_tokens=80, total_time_ms=400),
    ]

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    x, _, _ = data.scatter_points[0]

    # Assert: null row excluded
    assert x == 80.0


def test_chart8_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart8_two_models_produce_two_scatter_points(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", completion_tokens=100, total_time_ms=1000),
        make_result(model_name="b", completion_tokens=200, total_time_ms=2000),
    ]

    # Act
    data = Chart8TimeTokensAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert len(data.scatter_points) == 2
    labels = {pt[2] for pt in data.scatter_points}
    assert labels == {"a", "b"}
