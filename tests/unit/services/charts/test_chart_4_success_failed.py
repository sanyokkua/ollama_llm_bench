"""Unit tests for Chart4SuccessFailedAggregator — success vs failed counts per model."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart4SuccessFailedAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart4_failed_count_combines_inference_and_judge_errors(make_result, all_filters) -> None:
    # Arrange: one inference error, one judge error, one clean success
    results = [
        make_result(model_name="a", has_inference_error=True),
        make_result(model_name="a", has_judge_error=True),
        make_result(model_name="a"),
    ]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    successful_idx = list(data.series_labels).index("Successful")
    failed_idx = list(data.series_labels).index("Failed")

    # Assert
    assert data.series_data[successful_idx][0] == 1
    assert data.series_data[failed_idx][0] == 2


def test_chart4_inference_only_filter(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", has_inference_error=True),
        make_result(model_name="a", has_judge_error=True),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"error_type": "inference_only"},
    )

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=filters)
    failed_idx = list(data.series_labels).index("Failed")

    # Assert: only the inference error row counted as failed
    assert data.series_data[failed_idx][0] == 1


def test_chart4_judge_only_filter(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", has_inference_error=True),
        make_result(model_name="a", has_judge_error=True),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"error_type": "judge_only"},
    )

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=filters)
    failed_idx = list(data.series_labels).index("Failed")

    # Assert: only the judge error row counted as failed
    assert data.series_data[failed_idx][0] == 1


def test_chart4_no_errors_all_successful(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a"),
        make_result(model_name="a"),
        make_result(model_name="a"),
    ]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    successful_idx = list(data.series_labels).index("Successful")
    failed_idx = list(data.series_labels).index("Failed")

    # Assert
    assert data.series_data[successful_idx][0] == 3
    assert data.series_data[failed_idx][0] == 0


def test_chart4_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart4_model_filter_excludes_unselected_model(make_result) -> None:
    # Arrange: two models, filter only includes "a"
    results = [
        make_result(model_name="a"),
        make_result(model_name="b", has_inference_error=True),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
    )

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: only model "a" present
    assert "a" in data.category_labels
    assert "b" not in data.category_labels


def test_chart4_series_labels_contain_successful_and_failed(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a")]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "Successful" in data.series_labels
    assert "Failed" in data.series_labels
