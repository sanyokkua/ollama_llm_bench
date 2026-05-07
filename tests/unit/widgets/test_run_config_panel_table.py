"""Unit tests for RunConfigPanel table population and Resume button status-awareness."""

from typing import cast

import pytest
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import BenchmarkRun, BenchmarkRunStatus, RunMode
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.run_config_panel import RunConfigPanel, _format_timestamp

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run(
    run_id: int,
    *,
    status: BenchmarkRunStatus = BenchmarkRunStatus.NOT_COMPLETED,
    run_mode: RunMode = RunMode.FULL_GRADING,
    timestamp: str = "2024-06-15T12:30:00",
    completed_tasks: int = 0,
    total_tasks: int = 0,
) -> BenchmarkRun:
    return BenchmarkRun(
        run_id=run_id,
        timestamp=timestamp,
        judge_model="llama3",
        status=status,
        run_mode=run_mode,
        completed_tasks=completed_tasks,
        total_tasks=total_tasks,
    )


def _build_panel(qapp: QApplication, mocker: MockerFixture, runs: list[BenchmarkRun]) -> RunConfigPanel:
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_svc = mocker.Mock()
    mock_svc.get_bool.return_value = True
    mock_svc.get.return_value = "0"
    mock_ctrl._app_settings_service = mock_svc
    mock_ctrl.get_provider_names.return_value = []
    mock_ctrl.get_healthy_provider_ids.return_value = []
    mock_ctrl.get_recent_runs.return_value = runs
    return RunConfigPanel(controller=cast(RunConfigController, mock_ctrl))


def _get_cell_text(panel: RunConfigPanel, row: int, col: int) -> str:
    model = panel._runs_table.model()
    assert isinstance(model, QStandardItemModel)
    item = model.item(row, col)
    assert item is not None
    return item.text()


# ---------------------------------------------------------------------------
# _format_timestamp unit tests
# ---------------------------------------------------------------------------


def test_format_timestamp_valid_iso_returns_formatted_string() -> None:
    assert _format_timestamp("2024-06-15T12:30:00") == "2024-06-15 12:30"


def test_format_timestamp_invalid_string_returns_raw() -> None:
    assert _format_timestamp("not-a-date") == "not-a-date"


def test_format_timestamp_empty_string_returns_empty() -> None:
    assert _format_timestamp("") == ""


# ---------------------------------------------------------------------------
# Table population tests
# ---------------------------------------------------------------------------


def test_runs_table_populates_mode_label(qapp: QApplication, mocker: MockerFixture) -> None:
    runs = [
        _make_run(1, run_mode=RunMode.PERFORMANCE),
        _make_run(2, run_mode=RunMode.SPEED),
        _make_run(3, run_mode=RunMode.FULL_GRADING),
    ]
    panel = _build_panel(qapp, mocker, runs)

    assert _get_cell_text(panel, 0, 1) == "System Benchmark"
    assert _get_cell_text(panel, 1, 1) == "Task Performance"
    assert _get_cell_text(panel, 2, 1) == "Comprehensive Evaluation"


def test_runs_table_populates_status_label(qapp: QApplication, mocker: MockerFixture) -> None:
    runs = [
        _make_run(1, status=BenchmarkRunStatus.NOT_COMPLETED),
        _make_run(2, status=BenchmarkRunStatus.COMPLETED),
        _make_run(3, status=BenchmarkRunStatus.FAILED),
    ]
    panel = _build_panel(qapp, mocker, runs)

    assert _get_cell_text(panel, 0, 3) == "In progress / Stopped"
    assert _get_cell_text(panel, 1, 3) == "Completed"
    assert _get_cell_text(panel, 2, 3) == "Failed"


def test_runs_table_populates_tasks_count(qapp: QApplication, mocker: MockerFixture) -> None:
    runs = [
        _make_run(1, completed_tasks=0, total_tasks=0),
        _make_run(2, completed_tasks=50, total_tasks=100),
        _make_run(3, completed_tasks=234, total_tasks=234),
    ]
    panel = _build_panel(qapp, mocker, runs)

    assert _get_cell_text(panel, 0, 4) == "—"
    assert _get_cell_text(panel, 1, 4) == "50 / 100"
    assert _get_cell_text(panel, 2, 4) == "234 / 234"


# ---------------------------------------------------------------------------
# Resume button status-awareness tests
# ---------------------------------------------------------------------------


def test_resume_button_enabled_for_not_completed_row(qapp: QApplication, mocker: MockerFixture) -> None:
    runs = [_make_run(1, status=BenchmarkRunStatus.NOT_COMPLETED)]
    panel = _build_panel(qapp, mocker, runs)

    panel._runs_table.selectRow(0)

    assert panel._resume_btn.isEnabled() is True


def test_resume_button_disabled_for_completed_row(qapp: QApplication, mocker: MockerFixture) -> None:
    runs = [_make_run(1, status=BenchmarkRunStatus.COMPLETED)]
    panel = _build_panel(qapp, mocker, runs)

    panel._runs_table.selectRow(0)

    assert panel._resume_btn.isEnabled() is False
    assert "finished" in panel._resume_btn.toolTip()


def test_resume_button_disabled_for_failed_row(qapp: QApplication, mocker: MockerFixture) -> None:
    runs = [_make_run(1, status=BenchmarkRunStatus.FAILED)]
    panel = _build_panel(qapp, mocker, runs)

    panel._runs_table.selectRow(0)

    assert panel._resume_btn.isEnabled() is False
    assert "not resumable" in panel._resume_btn.toolTip()
