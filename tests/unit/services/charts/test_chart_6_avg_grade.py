"""Unit tests for Chart6AvgGradeAggregator — average judge score per model."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart6AvgGradeAggregator


def test_chart6_basic_avg(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", judge_score=0.6),
        make_result(model_name="a", judge_score=1.0),
    ]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: mean of [0.6, 1.0] = 0.8
    assert abs(data.series_data[0][0] - 0.8) < 0.01


def test_chart6_excludes_null_judge_score(make_result, all_filters) -> None:
    # Arrange: one row with score, one without (auto-pass row)
    results = [
        make_result(model_name="a", judge_score=0.8),
        make_result(model_name="a", judge_score=None),
    ]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: only scored row included
    assert abs(data.series_data[0][0] - 0.8) < 0.01


def test_chart6_all_null_scores_returns_empty_state(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", judge_score=None)]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart6_judge_error_rows_excluded(make_result, all_filters) -> None:
    # Arrange: one judge error row with a score, one clean row
    results = [
        make_result(model_name="a", judge_score=0.0, has_judge_error=True),
        make_result(model_name="a", judge_score=1.0),
    ]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: error row excluded, avg = 1.0
    assert abs(data.series_data[0][0] - 1.0) < 0.01


def test_chart6_stdev_present_for_multiple_rows(make_result, all_filters) -> None:
    # Arrange: need >= 2 rows for stdev to be non-zero
    results = [
        make_result(model_name="a", judge_score=0.2),
        make_result(model_name="a", judge_score=0.8),
    ]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: stdev field populated and > 0
    assert len(data.series_stdev) > 0
    assert data.series_stdev[0] > 0.0


def test_chart6_stdev_zero_for_single_row(make_result, all_filters) -> None:
    # Arrange
    results = [make_result(model_name="a", judge_score=0.5)]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: stdev = 0.0 for single point
    assert data.series_stdev[0] == 0.0


def test_chart6_sorted_descending_by_mean(make_result, all_filters) -> None:
    # Arrange: "best" model should appear first
    results = [
        make_result(model_name="worst", judge_score=0.1),
        make_result(model_name="best", judge_score=0.9),
    ]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.category_labels[0] == "best"


def test_chart6_footnote_present_when_null_scores_excluded(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", judge_score=0.5),
        make_result(model_name="a", judge_score=None),
    ]

    # Act
    data = Chart6AvgGradeAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert "Excluded" in data.footnote
