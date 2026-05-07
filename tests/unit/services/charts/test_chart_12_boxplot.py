"""Unit tests for Chart12BoxplotAggregator — completion token distribution boxplot."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart12BoxplotAggregator


def test_chart12_box_plot_five_number_summary(make_result, all_filters) -> None:
    # Arrange: 10 data points — enough for true quartile computation (>= 5)
    results = [make_result(model_name="a", completion_tokens=i) for i in range(1, 11)]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: one box set with correct structure
    assert len(data.box_sets) == 1
    _min, q1, median, q3, _max = data.box_sets[0]
    assert _min == 1.0
    assert _max == 10.0
    assert q1 < median < q3


def test_chart12_min_max_are_extremes(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", completion_tokens=i) for i in range(1, 11)]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    _min, _, _, _, _max = data.box_sets[0]

    # Assert
    assert _min == 1.0
    assert _max == 10.0


def test_chart12_fallback_for_small_samples(make_result, all_filters) -> None:
    # Arrange: 3 data points — below the 5-point threshold, uses mean±stdev fallback
    results = [make_result(model_name="a", completion_tokens=i) for i in range(1, 4)]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: box set populated with 5 float values, none NaN
    assert len(data.box_sets) == 1
    assert all(isinstance(v, float) for v in data.box_sets[0])
    import math

    assert all(not math.isnan(v) for v in data.box_sets[0])


def test_chart12_single_value_fallback_stdev_zero(make_result, all_filters) -> None:
    # Arrange: single data point — stdev = 0.0, all five values equal mean
    results = [make_result(model_name="a", completion_tokens=42)]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    _min, _q1, median, _q3, _max = data.box_sets[0]

    # Assert: all 5 values are 42.0
    assert _min == 42.0
    assert _max == 42.0
    assert median == 42.0


def test_chart12_null_completion_tokens_excluded(make_result, all_filters) -> None:
    # Arrange: one null token row
    results = [
        make_result(model_name="a", completion_tokens=10),
        make_result(model_name="a", completion_tokens=None),
    ]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: box set produced from the single valid row
    assert len(data.box_sets) == 1


def test_chart12_inference_error_rows_excluded(make_result, all_filters) -> None:
    # Arrange: error row with extreme value — should not affect box stats
    results = [
        make_result(model_name="a", completion_tokens=9999, has_inference_error=True),
        make_result(model_name="a", completion_tokens=50),
    ]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    _min, _, _, _, _max = data.box_sets[0]

    # Assert: extreme 9999 value not present
    assert _max < 9999.0


def test_chart12_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart12_two_models_produce_two_box_sets(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", completion_tokens=i) for i in range(1, 11)] + [
        make_result(model_name="b", completion_tokens=i * 10) for i in range(1, 11)
    ]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: one box set per model
    assert len(data.box_sets) == 2
    assert len(data.series_labels) == 2
    assert "a" in data.series_labels
    assert "b" in data.series_labels


def test_chart12_series_labels_sorted_alphabetically(make_result, all_filters) -> None:
    # Arrange: add "b" before "a" to verify sort order is not insertion order
    results = [
        make_result(model_name="zebra", completion_tokens=100),
        make_result(model_name="alpha", completion_tokens=50),
    ]

    # Act
    data = Chart12BoxplotAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: sorted alphabetically
    assert data.series_labels[0] == "alpha"
    assert data.series_labels[1] == "zebra"
