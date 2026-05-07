"""Unit tests for UI state locking during active benchmarks.

Covers RunConfigPanel tab/start-button locking, ResultWidget save-checkbox
locking, and the Settings dialog guard in MainWindow.
"""

from typing import cast
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import AppContext, BenchmarkFlowApi, EventBus
from ollama_llm_bench.backend.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.main_window import MainWindow
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget
from ollama_llm_bench.ui.widgets.panels.run_config_panel import RunConfigPanel

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
# RunConfigPanel fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def run_config_panel(qapp: QApplication, mocker: MockerFixture) -> RunConfigPanel:
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_svc = mocker.Mock()
    mock_svc.get_bool.return_value = True
    mock_svc.get.return_value = "0"
    mock_ctrl._app_settings_service = mock_svc
    mock_ctrl.get_provider_names.return_value = []
    mock_ctrl.get_healthy_provider_ids.return_value = []
    mock_ctrl.get_recent_runs.return_value = []
    return RunConfigPanel(controller=cast(RunConfigController, mock_ctrl))


# ---------------------------------------------------------------------------
# ResultWidget fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def result_widget(qapp: QApplication, mocker: MockerFixture) -> ResultWidget:
    mock_ctrl = cast(MagicMock, mocker.Mock(spec=ResultWidgetControllerApi))
    mock_ctrl.get_also_save_to_default.return_value = False
    return ResultWidget(controller=mock_ctrl)


# ---------------------------------------------------------------------------
# MainWindow fixture — CentralWidget patched out to avoid heavy init
# ---------------------------------------------------------------------------


@pytest.fixture
def main_window(qapp: QApplication, mocker: MockerFixture) -> MainWindow:
    mock_central_cls = mocker.patch("ollama_llm_bench.ui.main_window.CentralWidget")
    mock_central_cls.return_value = QWidget()
    mock_ctx = cast(MagicMock, mocker.Mock(spec=AppContext))
    mock_ctx.get_event_bus.return_value = mocker.Mock(spec=EventBus)
    mock_ctx.get_benchmark_flow_api.return_value = mocker.Mock(spec=BenchmarkFlowApi)
    return MainWindow(ctx=mock_ctx)


# ---------------------------------------------------------------------------
# Group A — RunConfigPanel: tab widget and start button lock when running
# ---------------------------------------------------------------------------


def test_on_benchmark_status_changed_disables_tab_widget_when_running(
    run_config_panel: RunConfigPanel,
) -> None:
    run_config_panel._on_benchmark_status_changed(True)

    assert not run_config_panel._tab_widget.isEnabled()


def test_on_benchmark_status_changed_disables_start_button_when_running(
    run_config_panel: RunConfigPanel,
) -> None:
    run_config_panel._on_benchmark_status_changed(True)

    assert not run_config_panel._start_btn.isEnabled()


# ---------------------------------------------------------------------------
# Group B — RunConfigPanel: Resume tab initial state
# ---------------------------------------------------------------------------


def test_resume_button_initially_disabled(run_config_panel: RunConfigPanel) -> None:
    assert not run_config_panel._resume_btn.isEnabled()


def test_refresh_runs_button_is_present(run_config_panel: RunConfigPanel) -> None:
    assert run_config_panel._refresh_runs_btn is not None


# ---------------------------------------------------------------------------
# Group C — RunConfigPanel: tab widget and start button re-enable when idle
# ---------------------------------------------------------------------------


def test_on_benchmark_status_changed_enables_tab_widget_when_stopped(
    run_config_panel: RunConfigPanel,
) -> None:
    run_config_panel._on_benchmark_status_changed(True)
    run_config_panel._on_benchmark_status_changed(False)

    assert run_config_panel._tab_widget.isEnabled()


def test_on_benchmark_status_changed_enables_start_button_when_stopped(
    run_config_panel: RunConfigPanel,
) -> None:
    from ollama_llm_bench.backend.core.models import RunMode

    run_config_panel._run_mode_widget.set_mode(RunMode.PERFORMANCE)
    run_config_panel._on_benchmark_status_changed(True)
    run_config_panel._on_benchmark_status_changed(False)

    assert run_config_panel._start_btn.isEnabled()


# ---------------------------------------------------------------------------
# Group D — ResultWidget: save checkboxes locked during run
# ---------------------------------------------------------------------------


def test_on_benchmark_is_running_changed_disables_summary_save_checkbox_when_running(
    result_widget: ResultWidget,
) -> None:
    result_widget._on_benchmark_is_running_changed(True)

    assert not result_widget._summary_also_save_checkbox.isEnabled()


def test_on_benchmark_is_running_changed_disables_details_save_checkbox_when_running(
    result_widget: ResultWidget,
) -> None:
    result_widget._on_benchmark_is_running_changed(True)

    assert not result_widget._details_also_save_checkbox.isEnabled()


def test_on_benchmark_is_running_changed_enables_save_checkboxes_when_stopped(
    result_widget: ResultWidget,
) -> None:
    result_widget._on_benchmark_is_running_changed(True)
    result_widget._on_benchmark_is_running_changed(False)

    assert result_widget._summary_also_save_checkbox.isEnabled()
    assert result_widget._details_also_save_checkbox.isEnabled()


# ---------------------------------------------------------------------------
# Group E — MainWindow: Settings dialog blocked during active benchmark
# ---------------------------------------------------------------------------


def test_open_settings_shows_message_and_does_not_open_dialog_when_running(
    main_window: MainWindow,
    mocker: MockerFixture,
) -> None:
    mock_ctx = cast(MagicMock, main_window._ctx)
    mock_ctx.get_benchmark_flow_api.return_value.is_running.return_value = True
    mock_msgbox = mocker.patch("ollama_llm_bench.ui.main_window.QMessageBox.information")
    mock_dialog = mocker.patch("ollama_llm_bench.ui.main_window.SettingsDialog")

    main_window._open_settings()

    mock_msgbox.assert_called_once()
    mock_dialog.assert_not_called()


def test_open_settings_opens_dialog_when_idle(
    main_window: MainWindow,
    mocker: MockerFixture,
) -> None:
    mock_ctx = cast(MagicMock, main_window._ctx)
    mock_ctx.get_benchmark_flow_api.return_value.is_running.return_value = False
    mocker.patch("ollama_llm_bench.ui.main_window.QMessageBox.information")
    mock_dialog_cls = mocker.patch("ollama_llm_bench.ui.main_window.SettingsDialog")
    mock_dialog_cls.return_value.exec.return_value = None

    main_window._open_settings()

    mock_dialog_cls.assert_called_once()
    mock_dialog_cls.return_value.exec.assert_called_once()


# ---------------------------------------------------------------------------
# Group F — Tooltip presence on actionable buttons
# ---------------------------------------------------------------------------


def test_start_button_has_descriptive_tooltip(run_config_panel: RunConfigPanel) -> None:
    tooltip = run_config_panel._start_btn.toolTip()
    assert len(tooltip) > 0


def test_resume_button_has_descriptive_tooltip(run_config_panel: RunConfigPanel) -> None:
    tooltip = run_config_panel._resume_btn.toolTip()
    assert len(tooltip) > 0
