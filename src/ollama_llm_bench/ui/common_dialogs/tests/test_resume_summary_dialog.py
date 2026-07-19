"""Tests for the Resume Summary dialog (STORY-057)."""

from collections.abc import Callable

from PySide6.QtCore import Qt
import pytest
from pytestqt.qtbot import QtBot
import structlog

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ResultId,
    ResultStatus,
    RunId,
    RunMode,
    RunStatus,
    Verdict,
)
from ollama_llm_bench.backend.events import Subscription
from ollama_llm_bench.backend.run_drift import DriftKind, DriftSeverity, DriftWarning
from ollama_llm_bench.ui.common_dialogs._internal.resume_summary_select import (
    select_resume_summary_view_model,
)
from ollama_llm_bench.ui.common_dialogs._internal.resume_summary_view import ResumeSummaryDialog


class _RecordingEventBus:
    """A minimal ``EventBus`` structural fake recording every emitted payload."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def subscribe(
        self,
        signal_name: str,
        handler: Callable[[object], None],
        owner: object | None = None,
    ) -> Subscription:
        raise NotImplementedError

    def emit(self, signal_name: str, payload: object) -> None:
        self.emitted.append((signal_name, payload))


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


class _FakeResumeSummaryGateway:
    def __init__(self) -> None:
        self.reset_result_ids: tuple[ResultId, ...] | None = None
        self.resumed_run_id: RunId | None = None

    def get_run(self, run_id: RunId) -> BenchmarkRun:
        return _RUN

    def resumable_results(self, run_id: RunId) -> tuple[BenchmarkResult, ...]:
        return (_result(1, ResultStatus.PENDING),)

    def detect_drift(self, run_id: RunId) -> tuple[DriftWarning, ...]:
        return ()

    def reset_results(self, result_ids: tuple[ResultId, ...]) -> int:
        self.reset_result_ids = result_ids
        return len(result_ids)

    def resume_run(self, run_id: RunId) -> None:
        self.resumed_run_id = run_id


def test_resume_summary_dialog_constructs_and_shows_with_no_error_logs(qtbot: QtBot) -> None:
    """Proves: STORY-057-AC-7

    ``ResumeSummaryDialog`` constructs and shows with no error/critical logs.
    """
    # Arrange
    gateway = _FakeResumeSummaryGateway()
    view_model = select_resume_summary_view_model(
        run=_RUN, resumable_results=(_result(1, ResultStatus.PENDING),), drift_warnings=()
    )
    bus = _RecordingEventBus()
    # Act
    with structlog.testing.capture_logs() as logs:
        dialog = ResumeSummaryDialog(gateway=gateway, event_bus=bus, view_model=view_model)
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.wait(0)
    # Assert
    assert dialog.isVisible()
    assert not any(entry["log_level"] in {"error", "critical"} for entry in logs)


def test_resume_resets_only_checked_and_calls_resume_run(qtbot: QtBot) -> None:
    """Proves: STORY-057-AC-4

    Clicking Resume Run resets only the checked tasks and calls
    ``ResumeGateway.resume_run(run_id)``; an unchecked task is untouched.
    """
    # Arrange
    gateway = _FakeResumeSummaryGateway()
    bus = _RecordingEventBus()
    view_model = select_resume_summary_view_model(
        run=_RUN,
        resumable_results=(_result(1, ResultStatus.PENDING), _result(2, ResultStatus.PENDING)),
        drift_warnings=(),
    )
    dialog = ResumeSummaryDialog(gateway=gateway, event_bus=bus, view_model=view_model)
    qtbot.addWidget(dialog)
    dialog.show()
    # Act -- uncheck the second task, then click Resume Run
    second_item = dialog.task_item_by_result_id[2]
    second_item.setCheckState(Qt.CheckState.Unchecked)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        dialog.resume_button, Qt.MouseButton.LeftButton
    )
    # Assert
    assert gateway.reset_result_ids == (1,)
    assert gateway.resumed_run_id == _RUN.run_id


def test_blocking_drift_gates_resume_behind_checkbox(qtbot: QtBot) -> None:
    """Proves: STORY-057-AC-2

    The Resume Run button is disabled with a BLOCKING warning present, and
    enables once the "Resume anyway" checkbox is ticked.
    """
    # Arrange
    gateway = _FakeResumeSummaryGateway()
    bus = _RecordingEventBus()
    view_model = select_resume_summary_view_model(
        run=_RUN,
        resumable_results=(_result(1, ResultStatus.PENDING),),
        drift_warnings=(_blocking_warning(),),
    )
    dialog = ResumeSummaryDialog(gateway=gateway, event_bus=bus, view_model=view_model)
    qtbot.addWidget(dialog)
    dialog.show()
    # Assert -- disabled before ticking
    assert not dialog.resume_button.isEnabled()
    # Act
    override_checkbox = dialog.override_checkbox
    assert override_checkbox is not None
    qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
        override_checkbox, Qt.MouseButton.LeftButton
    )
    # Assert -- enabled after ticking
    assert dialog.resume_button.isEnabled()
