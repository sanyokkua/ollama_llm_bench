"""Tests for the Retry Selection dialog (STORY-057)."""

import pytest

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultStatus, Verdict
from ollama_llm_bench.ui.common_dialogs._internal.retry_selection_select import (
    filter_group_for,
    select_retry_selection_view_model,
    visible_rows,
)
from ollama_llm_bench.ui.common_dialogs.models import RetryFilterOption


def _result(
    result_id: int, status: ResultStatus, verdict: Verdict | None = None
) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=1,
        task_id=f"task-{result_id}",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=status,
        verdict=verdict,
        created_at="2026-07-19T10:00:00Z",
    )


@pytest.mark.parametrize(
    ("status", "expected_group", "expected_checked"),
    [
        (ResultStatus.FAILED_INFERENCE, RetryFilterOption.ONLY_FAILED, True),
        (ResultStatus.FAILED_PROVIDER, RetryFilterOption.ONLY_FAILED, True),
        (ResultStatus.FAILED_TIMEOUT, RetryFilterOption.ONLY_FAILED, True),
        (ResultStatus.FAILED_JUDGE_TIMEOUT, RetryFilterOption.ONLY_FAILED, True),
        (ResultStatus.ERRORED, RetryFilterOption.ONLY_FAILED, True),
        (ResultStatus.PENDING, RetryFilterOption.ONLY_INCOMPLETE, True),
        (ResultStatus.RUNNING_INFERENCE, RetryFilterOption.ONLY_INCOMPLETE, True),
        (ResultStatus.AWAITING_JUDGE_CHECK, RetryFilterOption.ONLY_INCOMPLETE, True),
        (ResultStatus.COMPLETED, RetryFilterOption.ONLY_COMPLETED, False),
    ],
)
def test_pre_selection_rule_by_group(
    status: ResultStatus,
    expected_group: RetryFilterOption,
    expected_checked: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
) -> None:
    """Proves: STORY-057-AC-5

    Failed/incomplete rows are pre-checked; completed rows are unchecked;
    every row's filter_group matches its status bucket.
    """
    # Arrange / Act
    view_model = select_retry_selection_view_model(run_id=1, results=(_result(1, status),))
    # Assert
    row = view_model.rows[0]
    assert row.filter_group == expected_group
    assert row.is_checked is expected_checked


def test_default_filter_is_only_failed_and_shows_only_that_group() -> None:
    """Proves: STORY-057-AC-5

    visible_rows(..., filter_option=ONLY_FAILED) returns only the Failed group.
    """
    # Arrange
    rows = select_retry_selection_view_model(
        run_id=1,
        results=(
            _result(1, ResultStatus.FAILED_INFERENCE),
            _result(2, ResultStatus.PENDING),
            _result(3, ResultStatus.COMPLETED),
        ),
    ).rows
    # Act
    shown = visible_rows(rows, filter_option=RetryFilterOption.ONLY_FAILED)
    # Assert
    assert [r.result_id for r in shown] == [1]


@pytest.mark.parametrize(
    ("status", "expected_group"),
    [
        (ResultStatus.FAILED_JUDGE_TIMEOUT, RetryFilterOption.ONLY_FAILED),
        (ResultStatus.FAILED_INFERENCE, RetryFilterOption.ONLY_FAILED),
        (ResultStatus.FAILED_PROVIDER, RetryFilterOption.ONLY_FAILED),
        (ResultStatus.FAILED_TIMEOUT, RetryFilterOption.ONLY_FAILED),
        (ResultStatus.ERRORED, RetryFilterOption.ONLY_FAILED),
        (ResultStatus.RUNNING_INFERENCE, RetryFilterOption.ONLY_INCOMPLETE),
        (ResultStatus.COMPLETED, RetryFilterOption.ONLY_COMPLETED),
    ],
)
def test_filter_group_for_maps_every_status(
    status: ResultStatus, expected_group: RetryFilterOption
) -> None:
    """Proves: STORY-057-AC-6

    Table-driven: filter_group_for classifies every ResultStatus into its
    §4 Result Status Grouping bucket.
    """
    assert filter_group_for(status) == expected_group
