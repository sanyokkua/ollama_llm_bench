"""Unit tests for Chart1TtftAggregator — average TTFT per model."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart1TtftAggregator


def test_chart1_avg_ttft_aggregation(make_result, all_filters) -> None:
    # Arrange: two results with different ttft_ms values
    results = [
        make_result(model_name="a", ttft_ms=100),
        make_result(model_name="a", ttft_ms=200),
    ]
    agg = Chart1TtftAggregator()

    # Act
    data = agg.compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: mean of [100, 200] = 150.0
    assert data.category_labels == ("a",)
    assert abs(data.series_data[0][0] - 150.0) < 0.01


def test_chart1_excludes_null_ttft(make_result, all_filters) -> None:
    # Arrange: only the row with ttft_ms set should count
    results = [
        make_result(model_name="a", ttft_ms=100),
        make_result(model_name="a", ttft_ms=None),
    ]
    agg = Chart1TtftAggregator()

    # Act
    data = agg.compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.series_data[0][0] == 100.0


def test_chart1_all_null_returns_empty_state(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", ttft_ms=None)]

    # Act
    data = Chart1TtftAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart1_sorted_ascending_by_mean(make_result, all_filters) -> None:
    # Arrange: model "b" has lower avg TTFT than "a" — expect "b" first
    results = [
        make_result(model_name="a", ttft_ms=200),
        make_result(model_name="b", ttft_ms=50),
    ]
    agg = Chart1TtftAggregator()

    # Act
    data = agg.compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.category_labels[0] == "b"
    assert data.category_labels[1] == "a"


def test_chart1_inference_error_rows_excluded(make_result, all_filters) -> None:
    # Arrange: one row with inference error — should be excluded even if ttft_ms is set
    results = [
        make_result(model_name="a", ttft_ms=100, has_inference_error=True),
        make_result(model_name="a", ttft_ms=200),
    ]
    agg = Chart1TtftAggregator()

    # Act
    data = agg.compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: only the non-error row is included
    assert abs(data.series_data[0][0] - 200.0) < 0.01


def test_chart1_model_filter_excludes_unselected(make_result) -> None:
    # Arrange: two models, but filter only includes "a"
    from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters

    results = [
        make_result(model_name="a", ttft_ms=100),
        make_result(model_name="b", ttft_ms=999),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["reasoning"]),
        included_layers=frozenset(),
    )
    agg = Chart1TtftAggregator()

    # Act
    data = agg.compute_data(run=None, results=results, filters=filters)

    # Assert
    assert data.category_labels == ("a",)


def test_chart1_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart1TtftAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart1_footnote_present_when_rows_excluded(make_result, all_filters) -> None:
    # Arrange: one null ttft row triggers footnote
    results = [
        make_result(model_name="a", ttft_ms=100),
        make_result(model_name="a", ttft_ms=None),
    ]
    agg = Chart1TtftAggregator()

    # Act
    data = agg.compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: footnote mentions excluded rows
    assert "Excluded" in data.footnote
