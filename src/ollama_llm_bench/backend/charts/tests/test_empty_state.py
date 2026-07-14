"""Empty-state resolution (`13_CHART_AGGREGATORS.md` §6.7, §7)."""

import pytest

from ollama_llm_bench.backend.charts import make_chart_aggregator
from ollama_llm_bench.backend.charts.tests.conftest import (
    make_benchmark_result,
    make_benchmark_task,
)
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    ChartFilters,
    ChartKind,
    ModelDescriptor,
    ResultStatus,
    RunMode,
)

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "model-a"

_NO_ROWS: tuple[BenchmarkResult, ...] = ()
_FIELD_MISSING_ROWS = (
    make_benchmark_result(
        result_id=1,
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        ttft_ms=None,
        total_time_ms=None,
        completion_tokens=None,
        tokens_per_second=None,
        cosine_similarity=None,
        verdict=None,
    ),
)


@pytest.mark.parametrize(
    "chart_kind,run_mode,rows,task_category,options,expected_message",
    [
        pytest.param(
            ChartKind.AVG_TTFT_PER_MODEL,
            RunMode.TASKS,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {},
            "No time-to-first-token data — provider streaming is required for this metric.",
            id="avg_ttft_every_ttft_null",
        ),
        pytest.param(
            ChartKind.AVG_TPS_PER_MODEL,
            RunMode.TASKS,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {},
            "No completed inferences yet.",
            id="avg_tps_every_tps_null",
        ),
        pytest.param(
            ChartKind.AVG_TIME_PER_MODEL,
            RunMode.TASKS,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {},
            "No completed inferences yet.",
            id="avg_time_every_total_time_null",
        ),
        pytest.param(
            ChartKind.SUCCESS_FAILED_INCOMPLETE_STACKED,
            RunMode.TASKS,
            _NO_ROWS,
            "General Knowledge",
            {},
            "No results yet.",
            id="success_failed_incomplete_no_rows",
        ),
        pytest.param(
            ChartKind.PASS_RATE_BY_MODEL,
            RunMode.GRADED,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {"count_ungraded_as_not_pass": False},
            "No verdicts yet — this run has not reached the judge stage.",
            id="pass_rate_no_verdicts",
        ),
        pytest.param(
            ChartKind.AVG_COSINE_BY_MODEL,
            RunMode.GRADED,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {},
            "No verdicts yet — this run has not reached the cosine stage.",
            id="avg_cosine_no_scores",
        ),
        pytest.param(
            ChartKind.VERDICT_COUNTS_STACKED,
            RunMode.GRADED,
            _NO_ROWS,
            "General Knowledge",
            {},
            "No verdicts yet — this run has not reached the judge stage.",
            id="verdict_counts_no_completed_rows",
        ),
        pytest.param(
            ChartKind.TIME_VS_TOKENS_SCATTER,
            RunMode.TASKS,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {},
            "No completed inferences yet.",
            id="time_vs_tokens_every_field_null",
        ),
        pytest.param(
            ChartKind.HEATMAP_TASK_BY_MODEL,
            RunMode.GRADED,
            _NO_ROWS,
            "General Knowledge",
            {},
            "The heatmap needs at least one completed task per model.",
            id="heatmap_no_completed_pairs",
        ),
        pytest.param(
            ChartKind.PER_CATEGORY_BAR,
            RunMode.GRADED,
            _FIELD_MISSING_ROWS,
            "",
            {},
            "No task in this run has a category set.",
            id="per_category_bar_no_category",
        ),
        pytest.param(
            ChartKind.SPEED_VS_QUALITY_SCATTER,
            RunMode.GRADED,
            _NO_ROWS,
            "General Knowledge",
            {},
            "Speed vs quality needs at least two models with completed verdicts.",
            id="speed_vs_quality_fewer_than_two_models",
        ),
        pytest.param(
            ChartKind.TOKENS_PER_TASK_BOX,
            RunMode.TASKS,
            _FIELD_MISSING_ROWS,
            "General Knowledge",
            {},
            "No completed inferences yet.",
            id="tokens_per_task_box_every_field_null",
        ),
    ],
)
def test_empty_state_message_per_kind(  # noqa: PLR0913  # one column per table dimension
    chart_kind: ChartKind,
    run_mode: RunMode,
    rows: tuple[BenchmarkResult, ...],
    task_category: str,
    options: dict[str, str | bool],
    expected_message: str,
) -> None:
    """Proves: STORY-033-AC-8

    Given, per chart kind, either no surviving row or a row set whose
    required field is `None` on every row, when the aggregator runs, then
    it returns the kind-specific empty-state structure carrying that kind's
    exact §7 message and raises no exception (§6.7, CA-2, CA-11, CA-28;
    EC-RES-1's general "no surviving rows" case is the `_NO_ROWS` cases
    above). CA-29 (an out-of-domain per-chart option) is covered by
    `test_chart_options.py`, not this table — no case here supplies an
    out-of-domain option value.
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task(category=task_category)

    # Act
    result = aggregator.compute(
        chart_kind=chart_kind,
        run_mode=run_mode,
        results=rows,
        tasks=(task,),
        filters=ChartFilters(options=options),
    )

    # Assert
    assert result.empty_state_message == expected_message


def test_no_row_survives_global_filters_is_empty_state() -> None:
    """Proves: STORY-033-AC-8

    Given a filter set under which no row survives the global filters (a
    Models selection matching no row), when the aggregator runs, then it
    returns the kind-specific empty-state structure and raises no exception
    (§6.7, §9, EC-RES-1).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task()
    row = make_benchmark_result(
        result_id=1, provider_id=_PROVIDER_ID, model_name=_MODEL_NAME, status=ResultStatus.COMPLETED
    )
    non_matching_provider_id = "22222222-2222-4222-8222-222222222222"

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=(row,),
        tasks=(task,),
        filters=ChartFilters(
            models=(
                ModelDescriptor(provider_id=non_matching_provider_id, model_name="other-model"),
            )
        ),
    )

    # Assert
    assert result.empty_state_message == (
        "No time-to-first-token data — provider streaming is required for this metric."
    )


def test_out_of_domain_task_id_row_is_dropped_without_exception() -> None:
    """Proves: STORY-033-AC-8

    Given a result row referencing a `task_id` absent from `tasks`, when
    the aggregator runs, then that row is dropped and the chart falls back
    to its empty state — no exception is raised (§9, CA-28).
    """
    # Arrange
    aggregator = make_chart_aggregator()
    task = make_benchmark_task(task_id="known-task")
    orphan_row = make_benchmark_result(
        result_id=1, task_id="unknown-task", provider_id=_PROVIDER_ID, model_name=_MODEL_NAME
    )

    # Act
    result = aggregator.compute(
        chart_kind=ChartKind.AVG_TTFT_PER_MODEL,
        run_mode=RunMode.TASKS,
        results=(orphan_row,),
        tasks=(task,),
        filters=ChartFilters(),
    )

    # Assert
    assert result.empty_state_message == (
        "No time-to-first-token data — provider streaming is required for this metric."
    )
