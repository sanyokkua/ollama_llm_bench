"""The five global filters (`13_CHART_AGGREGATORS.md` §6.2)."""

import pytest

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    ChartData,
    ChartFilters,
    ChartKind,
    Difficulty,
    ModelDescriptor,
    ResultStatus,
    RunMode,
    Verdict,
)

_PROVIDER_A_ID = "11111111-1111-4111-8111-111111111111"
_PROVIDER_B_ID = "22222222-2222-4222-8222-222222222222"
_MODEL_A = "model-a"
_MODEL_B = "model-b"


def _kept_row_count(*, filters: ChartFilters) -> int:
    """Run `AVG_TIME_PER_MODEL` (all-mode, COMPLETED-prefiltered) over the shared
    six-row working set and return how many rows survived into the chart's
    single series' sample sizes."""
    aggregator = make_chart_aggregator()
    task_a = make_benchmark_task(task_id="task-a", category="CategoryA", difficulty=Difficulty.EASY)
    task_b = make_benchmark_task(task_id="task-b", category="CategoryB", difficulty=Difficulty.HARD)
    rows = (
        make_benchmark_result(
            result_id=1,
            task_id="task-a",
            provider_id=_PROVIDER_A_ID,
            model_name=_MODEL_A,
            status=ResultStatus.COMPLETED,
            verdict=Verdict.PASS,
        ),
        make_benchmark_result(
            result_id=2,
            task_id="task-b",
            provider_id=_PROVIDER_B_ID,
            model_name=_MODEL_B,
            status=ResultStatus.COMPLETED,
            verdict=Verdict.FAIL,
        ),
        make_benchmark_result(
            result_id=3,
            task_id="task-a",
            provider_id=_PROVIDER_B_ID,
            model_name=_MODEL_B,
            status=ResultStatus.COMPLETED,
            verdict=None,
        ),
        make_benchmark_result(
            result_id=4,
            task_id="task-does-not-exist",
            provider_id=_PROVIDER_A_ID,
            model_name=_MODEL_A,
            status=ResultStatus.COMPLETED,
            verdict=Verdict.PASS,
        ),
    )

    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TIME_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=rows,
        tasks=(task_a, task_b),
        filters=filters,
    )
    assert isinstance(result, ChartData)
    if not result.series:
        return 0
    return sum(result.series[0].sample_sizes)


@pytest.mark.parametrize(
    "filters,expected_kept",
    [
        pytest.param(ChartFilters(), 3, id="all_filters_default_keeps_every_joined_row"),
        pytest.param(
            ChartFilters(
                models=(ModelDescriptor(provider_id=_PROVIDER_A_ID, model_name=_MODEL_A),)
            ),
            1,
            id="models_filter_narrows_to_one_model",
        ),
        pytest.param(
            ChartFilters(statuses=(ResultStatus.COMPLETED,)),
            3,
            id="status_filter_keeps_matching_status",
        ),
        pytest.param(
            ChartFilters(statuses=(ResultStatus.FAILED_INFERENCE,)),
            0,
            id="status_filter_excludes_non_matching_status",
        ),
        pytest.param(ChartFilters(verdicts=("pass",)), 1, id="verdict_filter_keeps_pass_only"),
        pytest.param(
            ChartFilters(verdicts=("ungraded",)), 1, id="verdict_filter_keeps_ungraded_only"
        ),
        pytest.param(
            ChartFilters(categories=("CategoryA",)), 2, id="category_filter_keeps_matching_category"
        ),
        pytest.param(
            ChartFilters(difficulties=(Difficulty.HARD,)),
            1,
            id="difficulty_filter_keeps_matching_difficulty",
        ),
    ],
)
def test_each_global_filter_keeps_matching_rows(filters: ChartFilters, expected_kept: int) -> None:
    """Proves: STORY-033-AC-2

    Given a working result set of three task-joined rows and one row whose
    `task_id` has no matching task, when each of the five global filters is
    applied — Models, Status, Verdict, Category, Difficulty — then only the
    rows whose value is in the selected set are kept, and an "all" (empty)
    selection keeps every task-joined row; the unjoined row is always
    dropped (§6.2, CA-25, CA-26).
    """
    # Act / Assert
    assert _kept_row_count(filters=filters) == expected_kept
