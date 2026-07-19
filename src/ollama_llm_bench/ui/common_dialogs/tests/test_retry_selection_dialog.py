"""Tests for the Retry Selection dialog (STORY-057)."""

from PySide6.QtCore import Qt
import pytest
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import BenchmarkResult, ResultId, ResultStatus, RunId, Verdict
from ollama_llm_bench.ui.common_dialogs._internal.retry_selection_select import (
    filter_group_for,
    select_retry_selection_view_model,
    visible_rows,
)
from ollama_llm_bench.ui.common_dialogs._internal.retry_selection_view import RetrySelectionDialog
from ollama_llm_bench.ui.common_dialogs.models import RetryFilterOption

_TARGET_RUN_ID = 7


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


class _FakeRetrySelectionGateway:
    def __init__(self) -> None:
        self.reset_result_ids: tuple[ResultId, ...] | None = None
        self.resumed_run_id: RunId | None = None

    def list_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return ()

    def reset_results_for_retry(self, result_ids: tuple[ResultId, ...]) -> int:
        self.reset_result_ids = tuple(sorted(result_ids))
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        self.resumed_run_id = run_id


def test_retry_selection_dialog_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-057-AC-7

    ``RetrySelectionDialog`` constructs and shows with no error/critical logs.
    """
    # Arrange
    gateway = _FakeRetrySelectionGateway()
    view_model = select_retry_selection_view_model(
        run_id=1, results=(_result(1, ResultStatus.FAILED_INFERENCE),)
    )
    # Act
    with structlog.testing.capture_logs() as logs:
        dialog = RetrySelectionDialog(gateway=gateway, view_model=view_model)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_default_filter_preselection_and_confirm_resets_and_resumes(qtbot: QtBot) -> None:
    """Proves: STORY-057-AC-5

    The Filter defaults to Only failed; failed/incomplete rows are
    pre-checked, completed rows unchecked; confirming calls
    ``reset_results_for_retry`` with the checked ids, then ``resume_run``.
    """
    # Arrange
    gateway = _FakeRetrySelectionGateway()
    view_model = select_retry_selection_view_model(
        run_id=_TARGET_RUN_ID,
        results=(
            _result(1, ResultStatus.FAILED_INFERENCE),
            _result(2, ResultStatus.PENDING),
            _result(3, ResultStatus.COMPLETED),
        ),
    )
    dialog = RetrySelectionDialog(gateway=gateway, view_model=view_model)
    qtbot.addWidget(dialog)
    dialog.show()
    # Assert -- default filter is Only failed, showing only result 1
    assert dialog.filter_combo.currentData() == RetryFilterOption.ONLY_FAILED
    assert dialog.table.rowCount() == 1
    # Act
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.retry_button, Qt.MouseButton.LeftButton
    )
    # Assert -- 1 and 2 were pre-checked (3 was not), regardless of visibility
    assert gateway.reset_result_ids == (1, 2)
    assert gateway.resumed_run_id == _TARGET_RUN_ID
