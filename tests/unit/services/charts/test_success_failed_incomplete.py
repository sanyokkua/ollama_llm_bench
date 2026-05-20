"""Unit tests for Chart4SuccessFailedAggregator — Incomplete bucket for WAITING_FOR_JUDGE rows."""

from __future__ import annotations

from ollama_llm_bench.backend.core.models import BenchmarkResultStatus
from ollama_llm_bench.backend.services.charts.aggregations import Chart4SuccessFailedAggregator


def test_incomplete_bucket_counts_waiting_for_judge_rows(make_result, all_filters) -> None:
    # Arrange: mix of COMPLETED and WAITING_FOR_JUDGE
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED),
        make_result(model_name="a", status=BenchmarkResultStatus.WAITING_FOR_JUDGE),
        make_result(model_name="a", status=BenchmarkResultStatus.WAITING_FOR_JUDGE),
    ]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = list(data.series_labels)
    assert "Incomplete" in labels
    incomplete_idx = labels.index("Incomplete")
    successful_idx = labels.index("Successful")
    failed_idx = labels.index("Failed")

    # Assert: 1 successful, 0 failed, 2 incomplete
    assert data.series_data[successful_idx][0] == 1.0
    assert data.series_data[failed_idx][0] == 0.0
    assert data.series_data[incomplete_idx][0] == 2.0


def test_all_completed_gives_zero_incomplete(make_result, all_filters) -> None:
    # Arrange: all COMPLETED rows
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED),
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED),
    ]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = list(data.series_labels)
    incomplete_idx = labels.index("Incomplete")

    # Assert
    assert data.series_data[incomplete_idx][0] == 0.0


def test_series_labels_include_all_three_buckets(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a")]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "Successful" in data.series_labels
    assert "Failed" in data.series_labels
    assert "Incomplete" in data.series_labels


def test_counts_sum_to_total_per_model(make_result, all_filters) -> None:
    # Arrange: 2 models, various statuses
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED),
        make_result(model_name="a", status=BenchmarkResultStatus.WAITING_FOR_JUDGE),
        make_result(model_name="a", has_inference_error=True),
        make_result(model_name="b", status=BenchmarkResultStatus.COMPLETED),
    ]

    # Act
    data = Chart4SuccessFailedAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = list(data.series_labels)
    successful_idx = labels.index("Successful")
    failed_idx = labels.index("Failed")
    incomplete_idx = labels.index("Incomplete")
    model_idx = list(data.category_labels).index("a")

    # Assert: sums to 3 for model "a"
    total = (
        data.series_data[successful_idx][model_idx]
        + data.series_data[failed_idx][model_idx]
        + data.series_data[incomplete_idx][model_idx]
    )
    assert total == 3.0
