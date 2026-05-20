"""Unit tests for Charts 1/2/3 — WAITING_FOR_JUDGE rows are included in inference metrics."""

from __future__ import annotations

from collections.abc import Callable

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkResultStatus
from ollama_llm_bench.backend.services.charts.aggregations import (
    Chart1TtftAggregator,
    Chart2TpsAggregator,
    Chart3TimeAggregator,
)
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_ttft_includes_waiting_for_judge_rows(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange: one COMPLETED, one WAITING_FOR_JUDGE — both have valid ttft_ms
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED, ttft_ms=100),
        make_result(model_name="b", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, ttft_ms=200),
    ]

    # Act
    data = Chart1TtftAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: both models appear
    assert "a" in data.category_labels
    assert "b" in data.category_labels


def test_ttft_excludes_inference_error_rows(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange: one valid, one error
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, ttft_ms=150),
        make_result(
            model_name="b", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, has_inference_error=True, ttft_ms=None
        ),
    ]

    # Act
    data = Chart1TtftAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: only model "a" (no inference error)
    assert "a" in data.category_labels
    assert "b" not in data.category_labels


def test_tps_includes_waiting_for_judge_rows(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED, tokens_per_second=50.0),
        make_result(model_name="b", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, tokens_per_second=75.0),
    ]

    # Act
    data = Chart2TpsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "a" in data.category_labels
    assert "b" in data.category_labels


def test_time_includes_waiting_for_judge_rows(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED, total_time_ms=1000),
        make_result(model_name="b", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, total_time_ms=2000),
    ]

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "a" in data.category_labels
    assert "b" in data.category_labels


def test_time_excludes_not_completed_status(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange: NOT_COMPLETED should not appear
    results = [
        make_result(model_name="a", status=BenchmarkResultStatus.COMPLETED, total_time_ms=500),
        make_result(model_name="b", status=BenchmarkResultStatus.NOT_COMPLETED, total_time_ms=500),
    ]

    # Act
    data = Chart3TimeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "a" in data.category_labels
    assert "b" not in data.category_labels


def test_ttft_uses_has_inference_error_not_status(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Regression: a WAITING_FOR_JUDGE row with has_inference_error=True (as would be
    # set by the buggy _fail_pending_tasks_for_model on a resume run) must be excluded,
    # while one with has_inference_error=False must be included — regardless of status.
    results = [
        make_result(
            model_name="ok", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, ttft_ms=100, has_inference_error=False
        ),
        make_result(
            model_name="bad", status=BenchmarkResultStatus.WAITING_FOR_JUDGE, ttft_ms=100, has_inference_error=True
        ),
    ]

    # Act
    data = Chart1TtftAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: only the row without an inference error appears
    assert "ok" in data.category_labels
    assert "bad" not in data.category_labels
