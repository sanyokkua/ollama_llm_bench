"""Tests verifying density-pass margin and spacing values on key panels."""

from __future__ import annotations

from typing import cast

import pytest
from PySide6.QtCore import QMargins
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, BenchmarkFlowApi, EventBus
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.center_panel import CenterPanel
from ollama_llm_bench.ui.widgets.panels.run_config_panel import RunConfigPanel

# ---------------------------------------------------------------------------
# QApplication — module scope
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_config_panel_inner_spacing(qapp: QApplication, mocker: MockerFixture) -> None:
    # Arrange
    mock_ctrl = mocker.Mock(spec=RunConfigController)
    mock_svc = mocker.Mock()
    mock_svc.get_bool.return_value = True
    mock_svc.get.return_value = "0"
    mock_ctrl._app_settings_service = mock_svc
    mock_ctrl.get_provider_names.return_value = []
    mock_ctrl.get_healthy_provider_ids.return_value = []
    mock_ctrl.get_recent_runs.return_value = []
    panel = RunConfigPanel(controller=cast(RunConfigController, mock_ctrl))

    # Act
    inner_layout = panel._new_inner.layout()

    # Assert
    assert inner_layout is not None
    assert inner_layout.spacing() == 6


def test_center_panel_margins(qapp: QApplication, mocker: MockerFixture) -> None:
    # Arrange
    mock_bus = mocker.Mock(spec=EventBus)
    mock_flow = mocker.Mock(spec=BenchmarkFlowApi)
    mock_settings = mocker.Mock(spec=AppSettingsServiceApi)
    mock_settings.get_bool.return_value = True
    panel = CenterPanel(
        event_bus=mock_bus,
        benchmark_flow_api=mock_flow,
        app_settings=mock_settings,
    )

    # Act
    layout = panel.layout()

    # Assert
    assert layout is not None
    assert layout.contentsMargins() == QMargins(8, 8, 8, 8)
    assert layout.spacing() == 8
