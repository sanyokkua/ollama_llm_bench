"""Unit tests for Chart5PassRateAggregator — pass rate per model."""

from __future__ import annotations

from ollama_llm_bench.backend.core.models import RunMode
from ollama_llm_bench.backend.services.charts.aggregations import Chart5PassRateAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart5_speed_mode_returns_empty_state(make_result, make_run, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", final_verdict="pass")]
    run = make_run(run_mode=RunMode.SPEED)

    # Act
    data = Chart5PassRateAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert: Speed mode does not support pass rate
    assert data.empty_state_message != ""


def test_chart5_basic_pass_rate_100_percent(make_result, all_filters) -> None:
    # Arrange: all pass
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict="pass"),
    ]

    # Act
    data = Chart5PassRateAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert abs(data.series_data[0][0] - 100.0) < 0.01


def test_chart5_basic_pass_rate_50_percent(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict="fail"),
    ]

    # Act
    data = Chart5PassRateAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert abs(data.series_data[0][0] - 50.0) < 0.01


def test_chart5_rows_with_null_verdict_excluded(make_result, all_filters) -> None:
    # Arrange: one row with null verdict, one with pass
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict=None),
    ]

    # Act
    data = Chart5PassRateAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: 1/1 = 100%
    assert abs(data.series_data[0][0] - 100.0) < 0.01


def test_chart5_model_filter_limits_output(make_result) -> None:
    # Arrange: two models, filter only includes "a"
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="b", final_verdict="pass"),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
    )

    # Act
    data = Chart5PassRateAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert
    assert len(data.category_labels) == 1
    assert data.category_labels[0] == "a"


def test_chart5_sorted_descending_by_pass_rate(make_result, all_filters) -> None:
    # Arrange: "b" has 100% pass rate, "a" has 0%
    results = [
        make_result(model_name="a", final_verdict="fail"),
        make_result(model_name="b", final_verdict="pass"),
    ]

    # Act
    data = Chart5PassRateAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: "b" comes first (descending)
    assert data.category_labels[0] == "b"
    assert data.category_labels[1] == "a"


def test_chart5_no_verdict_data_returns_empty_state(make_result, all_filters) -> None:
    # Arrange: only null verdicts
    results = [make_result(model_name="a", final_verdict=None)]

    # Act
    data = Chart5PassRateAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""
