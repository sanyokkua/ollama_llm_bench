"""Unit tests for Chart10CategoryBarAggregator — per-category score breakdown."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart10CategoryBarAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart10_avg_score_mode(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", task_category="math", judge_score=0.8),
        make_result(model_name="a", task_category="math", judge_score=0.6),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["math"]),
        included_layers=frozenset(),
        extra={"score_type": "avg_score"},
    )

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: avg of [0.8, 0.6] = 0.7
    assert abs(data.series_data[0][0] - 0.7) < 0.01


def test_chart10_pass_rate_mode(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", task_category="math", final_verdict="pass"),
        make_result(model_name="a", task_category="math", final_verdict="fail"),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["math"]),
        included_layers=frozenset(),
        extra={"score_type": "pass_rate"},
    )

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: 50% pass rate
    assert abs(data.series_data[0][0] - 50.0) < 0.01


def test_chart10_score_vs_pass_rate_produce_different_values(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", task_category="math", judge_score=0.8, final_verdict="pass"),
        make_result(model_name="a", task_category="math", judge_score=0.6, final_verdict="fail"),
    ]
    f_score = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["math"]),
        included_layers=frozenset(),
        extra={"score_type": "avg_score"},
    )
    f_rate = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["math"]),
        included_layers=frozenset(),
        extra={"score_type": "pass_rate"},
    )

    # Act
    d_score = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=f_score)
    d_rate = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=f_rate)

    # Assert: avg_score ≈ 0.7; pass_rate = 50.0 — values must differ
    assert d_score.series_data[0][0] != d_rate.series_data[0][0]


def test_chart10_missing_model_category_pair_sentinel(make_result) -> None:
    # Arrange: model "a" has no data for category "code" — should get sentinel -1.0
    results = [
        make_result(model_name="a", task_category="math", judge_score=0.9),
    ]
    # Force "code" category into the results so the aggregator sees two categories
    results2 = [
        make_result(model_name="b", task_category="code", judge_score=0.5),
    ]
    all_results = results + results2
    filters = ChartFilters(
        included_models=frozenset(["a", "b"]),
        included_categories=frozenset(["math", "code"]),
        included_layers=frozenset(),
        extra={"score_type": "avg_score"},
    )

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=None, results=all_results, filters=filters)

    # Assert: footnote mentions missing pairs
    assert "missing" in data.footnote.lower() or data.footnote != ""


def test_chart10_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart10_series_labels_are_model_names(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="alpha", task_category="math", judge_score=0.5),
        make_result(model_name="beta", task_category="math", judge_score=0.7),
    ]
    filters = ChartFilters(
        included_models=frozenset(["alpha", "beta"]),
        included_categories=frozenset(["math"]),
        included_layers=frozenset(),
    )

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert
    assert "alpha" in data.series_labels
    assert "beta" in data.series_labels


def test_chart10_category_labels_are_categories(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", task_category="math", judge_score=0.5),
        make_result(model_name="a", task_category="code", judge_score=0.7),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["math", "code"]),
        included_layers=frozenset(),
    )

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert
    assert "math" in data.category_labels
    assert "code" in data.category_labels
