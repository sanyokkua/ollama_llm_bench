"""Resume Run footer button tests (STORY-057-AC-1)."""

from typing import cast

from PySide6.QtWidgets import QPushButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ResultStatus,
    RunMode,
    RunStatus,
)
from ollama_llm_bench.ui.resume_benchmark._internal.controller import ResumeBenchmarkController
from ollama_llm_bench.ui.resume_benchmark._internal.view import ResumeBenchmarkView
from ollama_llm_bench.ui.resume_benchmark.tests.test_controller import (
    _FakeFileSystemActions,
    _FakeNativePickers,
    _FakeResumeGateway,
    _RecordingEventBus,
)

_RESUMABLE_RUN_ID = 1
_COMPLETED_RUN_ID = 2


def _run(run_id: int, *, status: RunStatus) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        run_name=f"Run {run_id}",
        timestamp="2024-01-01T00:00:00+00:00",
        run_mode=RunMode.TASKS,
        status=status,
        total_tasks=1,
        completed_tasks=0 if status is not RunStatus.COMPLETED else 1,
        total_elapsed_ms=0,
        schema_version=1,
        created_at="2024-01-01T00:00:00+00:00",
    )


def _result(result_id: int, run_id: int, status: ResultStatus) -> BenchmarkResult:
    return BenchmarkResult(
        result_id=result_id,
        run_id=run_id,
        task_id=f"task-{result_id}",
        provider_id="11111111-1111-4111-8111-111111111111",
        provider_name="Test Provider",
        model_name="test-model",
        status=status,
        created_at="2024-01-01T00:00:00+00:00",
    )


def test_resume_button_enabled_only_for_resumable_not_executing(qtbot: QtBot) -> None:
    """Proves: STORY-057-AC-1

    The Resume Run button is enabled for a resumable, non-executing selected
    row, and disabled with a "fully completed" reason for a COMPLETED run.
    Covers EC-RUN-5, EC-RUN-6.
    """
    # Arrange
    gateway = _FakeResumeGateway(
        runs=(
            _run(_RESUMABLE_RUN_ID, status=RunStatus.STOPPED),
            _run(_COMPLETED_RUN_ID, status=RunStatus.COMPLETED),
        ),
        results_by_run_id={
            _RESUMABLE_RUN_ID: (_result(1, _RESUMABLE_RUN_ID, ResultStatus.PENDING),),
            _COMPLETED_RUN_ID: (_result(2, _COMPLETED_RUN_ID, ResultStatus.COMPLETED),),
        },
    )
    controller = ResumeBenchmarkController(
        gateway=gateway,
        event_bus=_RecordingEventBus(),
        native_pickers=_FakeNativePickers(),
        file_system_actions=_FakeFileSystemActions(),
    )
    view = ResumeBenchmarkView(controller=controller)
    controller.bind(view)
    controller.load_initial_rows()
    qtbot.addWidget(view)
    resume_button = cast(
        "QPushButton", view.findChild(QPushButton, "resume_benchmark.resume_button")
    )
    # Act -- select the resumable run
    controller.on_row_selected(_RESUMABLE_RUN_ID)
    # Assert
    assert resume_button.isEnabled()
    # Act -- select the COMPLETED run
    controller.on_row_selected(_COMPLETED_RUN_ID)
    # Assert
    assert not resume_button.isEnabled()
    assert "fully completed" in resume_button.toolTip()
