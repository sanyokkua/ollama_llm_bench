"""Unit tests for Chart7VerdictCountsAggregator — verdict counts stacked by verdict or layer."""

from __future__ import annotations

from collections.abc import Callable

from ollama_llm_bench.backend.core.models import BenchmarkResult
from ollama_llm_bench.backend.services.charts.aggregations import Chart7VerdictCountsAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart7_verdict_mode_default_series_labels(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange: default stack_mode = "verdict"
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict="fail"),
    ]

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: series labels are PASS and FAIL
    assert "PASS" in data.series_labels
    assert "FAIL" in data.series_labels


def test_chart7_verdict_mode_counts(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict="fail"),
    ]

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    pass_idx = list(data.series_labels).index("PASS")
    fail_idx = list(data.series_labels).index("FAIL")

    # Assert
    assert data.series_data[pass_idx][0] == 2.0
    assert data.series_data[fail_idx][0] == 1.0


def test_chart7_stack_by_layer_alternative(make_result: Callable[..., BenchmarkResult]) -> None:
    # Arrange
    results = [
        make_result(model_name="a", final_verdict="pass", resolution_layer="rule_based"),
        make_result(model_name="a", final_verdict="pass", resolution_layer="llm_judge"),
        make_result(model_name="a", final_verdict="fail", resolution_layer="rule_based"),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"stack_mode": "layer"},
    )

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: one series per unique layer
    assert len(data.series_labels) >= 2
    assert "rule_based" in data.series_labels
    assert "llm_judge" in data.series_labels


def test_chart7_layer_mode_counts_per_layer(make_result: Callable[..., BenchmarkResult]) -> None:
    # Arrange: 2 rule_based verdicts, 1 llm_judge verdict
    results = [
        make_result(model_name="a", final_verdict="pass", resolution_layer="rule_based"),
        make_result(model_name="a", final_verdict="fail", resolution_layer="rule_based"),
        make_result(model_name="a", final_verdict="pass", resolution_layer="llm_judge"),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
        extra={"stack_mode": "layer"},
    )

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=filters)
    rule_idx = list(data.series_labels).index("rule_based")
    judge_idx = list(data.series_labels).index("llm_judge")

    # Assert
    assert data.series_data[rule_idx][0] == 2.0
    assert data.series_data[judge_idx][0] == 1.0


def test_chart7_null_verdict_rows_excluded(
    make_result: Callable[..., BenchmarkResult],
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange: null verdict rows should be dropped entirely
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="a", final_verdict=None),
    ]

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    pass_idx = list(data.series_labels).index("PASS")

    # Assert: only 1 pass, null row excluded
    assert data.series_data[pass_idx][0] == 1.0


def test_chart7_empty_results_returns_empty_state(
    all_filters: Callable[[list[BenchmarkResult]], ChartFilters],
) -> None:
    # Arrange
    results: list[BenchmarkResult] = []

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart7_model_filter_applied(make_result: Callable[..., BenchmarkResult]) -> None:
    # Arrange: only include "a"
    results = [
        make_result(model_name="a", final_verdict="pass"),
        make_result(model_name="b", final_verdict="fail"),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
    )

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: "b" not in output
    assert "a" in data.category_labels
    assert "b" not in data.category_labels


def test_chart7_layer_mode_with_no_resolution_layers_returns_empty_state(
    make_result: Callable[..., BenchmarkResult],
) -> None:
    # Arrange: results have final_verdict but resolution_layer=None
    results = [
        make_result(model_name="a", final_verdict="pass", resolution_layer=None),
        make_result(model_name="a", final_verdict="fail", resolution_layer=None),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(),
        included_layers=frozenset(),
        extra={"stack_mode": "layer"},
    )

    # Act
    data = Chart7VerdictCountsAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: layer mode with no resolution data returns empty state
    assert data.empty_state_message != ""
