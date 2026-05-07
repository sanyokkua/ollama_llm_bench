"""Unit tests for Chart11SpeedQualityAggregator — speed vs quality scatter."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart11SpeedQualityAggregator


def test_chart11_basic_scatter(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", tokens_per_second=15.0, judge_score=0.9)]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert len(data.scatter_points) == 1
    x, y, label = data.scatter_points[0]
    assert x == 15.0
    assert y == 0.9
    assert label == "a"


def test_chart11_bubble_size_proportional_to_count(make_result, all_filters) -> None:
    # Arrange: "b" has 2 rows, "a" has 1
    results = [
        make_result(model_name="a", tokens_per_second=10.0, judge_score=0.8),
        make_result(model_name="b", tokens_per_second=20.0, judge_score=0.9),
        make_result(model_name="b", tokens_per_second=25.0, judge_score=0.7),
    ]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    counts = data.extra.get("counts_per_model", {})

    # Assert: "b" has more samples than "a"
    assert counts.get("b", 0) > counts.get("a", 0)


def test_chart11_null_tps_excluded(make_result, all_filters) -> None:
    # Arrange: one row with null TPS — should not appear in scatter
    results = [
        make_result(model_name="a", tokens_per_second=None, judge_score=0.8),
        make_result(model_name="b", tokens_per_second=20.0, judge_score=0.5),
    ]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = {pt[2] for pt in data.scatter_points}

    # Assert: "a" excluded, only "b" in scatter
    assert "b" in labels
    assert "a" not in labels


def test_chart11_zero_tps_excluded(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", tokens_per_second=0.0, judge_score=0.8),
        make_result(model_name="b", tokens_per_second=10.0, judge_score=0.5),
    ]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = {pt[2] for pt in data.scatter_points}

    # Assert
    assert "b" in labels
    assert "a" not in labels


def test_chart11_null_judge_score_excluded(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", tokens_per_second=15.0, judge_score=None),
        make_result(model_name="b", tokens_per_second=15.0, judge_score=0.7),
    ]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = {pt[2] for pt in data.scatter_points}

    # Assert
    assert "b" in labels
    assert "a" not in labels


def test_chart11_judge_error_rows_excluded(make_result, all_filters) -> None:
    # Arrange: judge_error row should be excluded
    results = [
        make_result(model_name="a", tokens_per_second=10.0, judge_score=0.1, has_judge_error=True),
        make_result(model_name="b", tokens_per_second=20.0, judge_score=0.9),
    ]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))
    labels = {pt[2] for pt in data.scatter_points}

    # Assert
    assert "b" in labels
    assert "a" not in labels


def test_chart11_multiple_rows_averaged_per_model(make_result, all_filters) -> None:
    # Arrange: two rows for same model — must be averaged into one point
    results = [
        make_result(model_name="a", tokens_per_second=10.0, judge_score=0.6),
        make_result(model_name="a", tokens_per_second=30.0, judge_score=1.0),
    ]

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: one point, averaged
    assert len(data.scatter_points) == 1
    x, y, _ = data.scatter_points[0]
    assert abs(x - 20.0) < 0.01  # avg TPS
    assert abs(y - 0.8) < 0.01  # avg score


def test_chart11_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart11SpeedQualityAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""
