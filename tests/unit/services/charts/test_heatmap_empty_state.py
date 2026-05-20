"""Unit tests for Chart9HeatmapAggregator — empty state when all cells are None."""

from __future__ import annotations

from ollama_llm_bench.backend.core.models import BenchmarkResultStatus, RunMode
from ollama_llm_bench.backend.services.charts.aggregations import Chart9HeatmapAggregator


def test_heatmap_performance_run_all_none_cells_returns_empty_state(make_result, make_run, all_filters) -> None:
    # Arrange: results with no judge data (PERFORMANCE run)
    results = [
        make_result(model_name="a", task_id="t1", status=BenchmarkResultStatus.COMPLETED),
        make_result(model_name="b", task_id="t1", status=BenchmarkResultStatus.COMPLETED),
    ]
    run = make_run(run_mode=RunMode.PERFORMANCE)

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""
    assert data.heatmap is None
    assert "performance" in data.empty_state_message.lower()


def test_heatmap_with_judge_scores_returns_heatmap_data(make_result, make_run, all_filters) -> None:
    # Arrange: results with judge scores
    results = [
        make_result(model_name="a", task_id="t1", judge_score=0.8),
        make_result(model_name="b", task_id="t1", judge_score=0.6),
    ]
    run = make_run(run_mode=RunMode.FULL_GRADING)

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert data.empty_state_message == ""


def test_heatmap_with_final_verdict_returns_heatmap_data(make_result, make_run, all_filters) -> None:
    # Arrange: results with final_verdict but no judge_score
    results = [
        make_result(model_name="a", task_id="t1", final_verdict="pass"),
        make_result(model_name="b", task_id="t1", final_verdict="fail"),
    ]
    run = make_run(run_mode=RunMode.PROMPT_EVAL)

    # Act
    data = Chart9HeatmapAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert
    assert data.heatmap is not None
    assert data.empty_state_message == ""
