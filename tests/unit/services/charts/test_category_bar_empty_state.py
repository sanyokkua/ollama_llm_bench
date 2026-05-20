"""Unit tests for Chart10CategoryBarAggregator — empty state when all data is absent."""

from __future__ import annotations

from ollama_llm_bench.backend.core.models import RunMode
from ollama_llm_bench.backend.services.charts.aggregations import Chart10CategoryBarAggregator


def test_category_bar_all_missing_returns_empty_state(make_result, make_run, all_filters) -> None:
    # Arrange: no judge scores or verdicts (PERFORMANCE run)
    results = [
        make_result(model_name="a", task_category="reasoning"),
        make_result(model_name="b", task_category="reasoning"),
    ]
    run = make_run(run_mode=RunMode.PERFORMANCE)

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message != ""
    assert data.series_data == ()
    assert "performance" in data.empty_state_message.lower()


def test_category_bar_partial_data_uses_zero_and_footnote(make_result, make_run, all_filters) -> None:
    # Arrange: model "a" has data, model "b" does not
    results = [
        make_result(model_name="a", task_category="reasoning", judge_score=0.7),
        make_result(model_name="b", task_category="reasoning"),
    ]
    run = make_run(run_mode=RunMode.FULL_GRADING)

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert: series_data is present (not empty state)
    assert data.series_data != ()
    assert data.empty_state_message == ""
    # footnote mentions missing pairs
    assert "1 of 2" in data.footnote


def test_category_bar_all_scored_has_no_footnote(make_result, make_run, all_filters) -> None:
    # Arrange: both models have scores
    results = [
        make_result(model_name="a", task_category="reasoning", judge_score=0.9),
        make_result(model_name="b", task_category="reasoning", judge_score=0.5),
    ]
    run = make_run(run_mode=RunMode.FULL_GRADING)

    # Act
    data = Chart10CategoryBarAggregator().compute_data(run=run, results=results, filters=all_filters(results))

    # Assert
    assert data.empty_state_message == ""
    assert data.footnote == ""
