"""Tests for the Resume Summary dialog (STORY-057)."""

import pytest

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ResultStatus,
    RunMode,
    RunStatus,
    Verdict,
)
from ollama_llm_bench.backend.run_drift import DriftKind, DriftSeverity, DriftWarning
from ollama_llm_bench.ui.common_dialogs._internal.resume_summary_select import (
    select_resume_summary_view_model,
)

_RUN = BenchmarkRun(
    run_id=1,
    run_name="My Run",
    timestamp="2026-07-19T10:00:00Z",
    run_mode=RunMode.TASKS,
    status=RunStatus.STOPPED,
    total_tasks=3,
    completed_tasks=1,
    total_elapsed_ms=1000,
    schema_version=1,
    created_at="2026-07-19T10:00:00Z",
)


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


def _blocking_warning(*, pending_results_affected: int = 2) -> DriftWarning:
    return DriftWarning(
        kind=DriftKind.PROVIDER_NOW_UNREACHABLE,
        severity=DriftSeverity.BLOCKING,
        headline="Provider unreachable",
        detail="The provider could not be reached.",
        pending_results_affected=pending_results_affected,
    )


@pytest.mark.parametrize(
    ("status", "expected_checked"),
    [
        (ResultStatus.PENDING, True),
        (ResultStatus.FAILED_INFERENCE, True),
        (ResultStatus.FAILED_PROVIDER, True),
        (ResultStatus.FAILED_TIMEOUT, True),
        (ResultStatus.FAILED_JUDGE_TIMEOUT, True),
        (ResultStatus.ERRORED, True),
        (ResultStatus.RUNNING_INFERENCE, True),
        (ResultStatus.AWAITING_JUDGE_CHECK, True),
    ],
)
def test_task_picker_precheck_per_status(
    status: ResultStatus,
    expected_checked: bool,  # noqa: FBT001  # pytest.mark.parametrize table column
) -> None:
    """Proves: STORY-057-AC-3

    Every not-yet-completed status is pre-checked and enabled with no drift present.
    """
    # Arrange / Act
    view_model = select_resume_summary_view_model(
        run=_RUN, resumable_results=(_result(1, status),), drift_warnings=()
    )
    # Assert
    row = view_model.task_rows[0]
    assert row.is_checked is expected_checked
    assert row.is_enabled is True


def test_completed_task_row_is_unchecked_but_enabled() -> None:
    """Proves: STORY-057-AC-3

    A COMPLETED row (re-run candidate the user explicitly picks) is listed
    unchecked but still tickable.
    """
    # Arrange / Act
    view_model = select_resume_summary_view_model(
        run=_RUN,
        resumable_results=(_result(1, ResultStatus.COMPLETED, verdict=Verdict.FAIL),),
        drift_warnings=(),
    )
    # Assert
    row = view_model.task_rows[0]
    assert row.is_checked is False
    assert row.is_enabled is True
    assert row.status_chip_label == "Completed · FAIL"


def test_blocking_drift_disables_not_yet_completed_rows_until_override() -> None:
    """Proves: STORY-057-AC-2

    An unresolved BLOCKING warning disables (and unchecks) every
    not-yet-completed row; the caller re-derives with override=True once
    "Resume anyway" is ticked.
    """
    # Arrange / Act
    view_model = select_resume_summary_view_model(
        run=_RUN,
        resumable_results=(_result(1, ResultStatus.PENDING),),
        drift_warnings=(_blocking_warning(),),
    )
    # Assert
    row = view_model.task_rows[0]
    assert row.is_enabled is False
    assert row.is_checked is False
    assert view_model.blocking_warnings == (_blocking_warning(),)


def test_blocking_drift_override_re_enables_rows() -> None:
    """Proves: STORY-057-AC-2

    Passing override=True (the ticked "Resume anyway" checkbox) restores the
    ordinary pre-check rule despite the unresolved BLOCKING warning.
    """
    # Arrange / Act
    view_model = select_resume_summary_view_model(
        run=_RUN,
        resumable_results=(_result(1, ResultStatus.PENDING),),
        drift_warnings=(_blocking_warning(),),
        drift_override_confirmed=True,
    )
    # Assert
    row = view_model.task_rows[0]
    assert row.is_enabled is True
    assert row.is_checked is True


def test_warning_only_drift_never_disables_rows() -> None:
    """Proves: STORY-057-AC-2

    A WARNING-severity-only warning set never gates rows or the button.
    """
    # Arrange
    warning = DriftWarning(
        kind=DriftKind.JUDGE_MODEL_UNAVAILABLE,
        severity=DriftSeverity.WARNING,
        headline="Judge model uncertain",
        detail="",
        pending_results_affected=0,
    )
    # Act
    view_model = select_resume_summary_view_model(
        run=_RUN, resumable_results=(_result(1, ResultStatus.PENDING),), drift_warnings=(warning,)
    )
    # Assert
    row = view_model.task_rows[0]
    assert row.is_enabled is True
    assert row.is_checked is True
    assert view_model.warning_warnings == (warning,)
    assert view_model.blocking_warnings == ()
