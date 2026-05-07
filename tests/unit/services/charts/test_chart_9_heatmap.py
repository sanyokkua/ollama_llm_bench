"""Unit tests for Chart9HeatmapAggregator — task x model score heatmap."""

from __future__ import annotations

from ollama_llm_bench.backend.services.charts.aggregations import Chart9HeatmapAggregator
from ollama_llm_bench.backend.services.charts.base_chart import ChartFilters


def test_chart9_heatmap_nan_cells_for_null_verdict_and_score(make_result, all_filters) -> None:
    # Arrange: no score and no verdict — cell should be None
    results = [make_result(model_name="a", task_id="t1", judge_score=None, final_verdict=None)]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert data.heatmap.cells.get(("t1", "a")) is None


def test_chart9_pass_verdict_maps_to_1(make_result, all_filters) -> None:
    # Arrange: no score, but pass verdict → 1.0
    results = [make_result(model_name="a", task_id="t1", judge_score=None, final_verdict="pass")]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert data.heatmap.cells.get(("t1", "a")) == 1.0


def test_chart9_fail_verdict_maps_to_0(make_result, all_filters) -> None:
    # Arrange: no score, fail verdict → 0.0
    results = [make_result(model_name="a", task_id="t1", judge_score=None, final_verdict="fail")]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert data.heatmap.cells.get(("t1", "a")) == 0.0


def test_chart9_judge_score_takes_priority_over_verdict(make_result, all_filters) -> None:
    # Arrange: both score and verdict — score wins
    results = [make_result(model_name="a", task_id="t1", judge_score=0.75, final_verdict="pass")]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: 0.75 not 1.0
    assert data.heatmap is not None
    assert data.heatmap.cells.get(("t1", "a")) == 0.75


def test_chart9_row_labels_are_task_ids_in_non_compact_mode(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="a", task_id="t1"),
        make_result(model_name="a", task_id="t2"),
    ]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert "t1" in data.heatmap.row_labels
    assert "t2" in data.heatmap.row_labels


def test_chart9_compact_mode_uses_task_categories(make_result) -> None:
    # Arrange
    results = [
        make_result(model_name="a", task_id="t1", task_category="math"),
        make_result(model_name="a", task_id="t2", task_category="code"),
    ]
    filters = ChartFilters(
        included_models=frozenset(["a"]),
        included_categories=frozenset(["math", "code"]),
        included_layers=frozenset(),
        extra={"compact_view": True},
    )

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=filters)

    # Assert: row labels are categories, not task IDs
    assert data.heatmap is not None
    assert "math" in data.heatmap.row_labels
    assert "code" in data.heatmap.row_labels


def test_chart9_col_labels_are_model_names(make_result, all_filters) -> None:
    # Arrange
    results = [
        make_result(model_name="alpha", task_id="t1"),
        make_result(model_name="beta", task_id="t1"),
    ]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert "alpha" in data.heatmap.col_labels
    assert "beta" in data.heatmap.col_labels


def test_chart9_empty_results_returns_empty_state(all_filters) -> None:
    # Arrange
    results = []

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""


def test_chart9_missing_task_for_model_produces_none_cell(make_result, all_filters) -> None:
    # Arrange: model "b" has no result for "t1"
    results = [
        make_result(model_name="a", task_id="t1", judge_score=0.9),
        make_result(model_name="b", task_id="t2", judge_score=0.5),
    ]

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=None, results=results, filters=all_filters(results))

    # Assert: "t1" x "b" cell is None (model b never ran task t1)
    assert data.heatmap is not None
    assert data.heatmap.cells.get(("t1", "b")) is None
