"""Determinism and snapshot immutability (`13_CHART_AGGREGATORS.md` §5, §6.5)."""

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import ChartData, ChartFilters, ChartKind, RunMode, Verdict

_PROVIDER_C_ID = "33333333-3333-4333-8333-333333333333"
_PROVIDER_A_ID = "11111111-1111-4111-8111-111111111111"
_PROVIDER_B_ID = "22222222-2222-4222-8222-222222222222"
_MODEL_NAME = "shared-model-name"


def test_aggregation_is_deterministic_and_snapshot_immutable() -> None:
    """Proves: STORY-033-AC-9

    Given the same `results`/`tasks` inputs, when `AVG_TTFT_PER_MODEL` runs
    twice, then both calls produce an identical `ChartData` with group order
    stable ascending by `(provider_id, model_name)`, and the input
    `results`/`tasks` tuples are unchanged after both calls (§5, §6.5,
    CA-27, CA-30).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1, provider_id=_PROVIDER_C_ID, model_name=_MODEL_NAME, ttft_ms=300
        ),
        make_benchmark_result(
            result_id=2, provider_id=_PROVIDER_A_ID, model_name=_MODEL_NAME, ttft_ms=100
        ),
        make_benchmark_result(
            result_id=3, provider_id=_PROVIDER_B_ID, model_name=_MODEL_NAME, ttft_ms=200
        ),
    )
    tasks = (task,)
    results_before = rows
    tasks_before = tasks
    filters = ChartFilters()

    # Act
    first_result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=tasks,
        filters=filters,
    )
    second_result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=tasks,
        filters=filters,
    )

    # Assert
    assert first_result == second_result
    assert isinstance(first_result, ChartData)
    assert first_result.series[0].values == (100.0, 200.0, 300.0)
    assert rows == results_before
    assert tasks == tasks_before


def test_grading_chart_determinism_across_repeated_calls() -> None:
    """Proves: STORY-033-AC-9

    Given the same `results`/`tasks` inputs for a grading chart, when
    `VERDICT_COUNTS_STACKED` runs twice, then both calls produce an
    identical `ChartData` and the input snapshots are unchanged (§5, CA-27,
    CA-30).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    rows = (
        make_benchmark_result(
            result_id=1, provider_id=_PROVIDER_A_ID, model_name=_MODEL_NAME, verdict=Verdict.PASS
        ),
        make_benchmark_result(
            result_id=2, provider_id=_PROVIDER_B_ID, model_name=_MODEL_NAME, verdict=Verdict.FAIL
        ),
    )
    tasks = (task,)
    results_before = rows
    tasks_before = tasks
    filters = ChartFilters()

    # Act
    first_result = aggregator.compute(
        chart_kind=ChartKind.VERDICT_COUNTS_STACKED,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=tasks,
        filters=filters,
    )
    second_result = aggregator.compute(
        chart_kind=ChartKind.VERDICT_COUNTS_STACKED,
        run_mode=RunMode.GRADED,
        results=rows,
        tasks=tasks,
        filters=filters,
    )

    # Assert
    assert first_result == second_result
    assert rows == results_before
    assert tasks == tasks_before
