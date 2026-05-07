"""Regression guard — asserts that primary interactive controls on key widgets have non-empty tooltips."""

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, EventBus
from ollama_llm_bench.backend.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.widgets.panels.control.performance_matrix_widget import PerformanceMatrixWidget
from ollama_llm_bench.ui.widgets.panels.control.test_models_widget import TestModelsWidget
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget

# ---------------------------------------------------------------------------
# QApplication — module scope so Qt is initialised exactly once
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


@pytest.mark.unit
def test_performance_matrix_widget_primary_buttons_have_tooltips(
    qapp: QApplication,
) -> None:
    # Arrange / Act
    widget = PerformanceMatrixWidget()

    # Assert
    assert widget._repeat_spinbox.toolTip() != ""


@pytest.mark.unit
def test_result_widget_primary_buttons_have_tooltips(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    # Arrange
    mock_controller = mocker.Mock(spec=ResultWidgetControllerApi)
    mock_app_settings = mocker.Mock(spec=AppSettingsServiceApi)
    mock_app_settings.get_bool.return_value = False
    mock_app_settings.get.return_value = None
    mock_app_settings.get_int.return_value = 0
    mock_controller.get_app_settings_service.return_value = mock_app_settings
    mock_controller.get_also_save_to_default.return_value = False

    # Act
    widget = ResultWidget(controller=mock_controller)

    # Assert
    assert widget._run_dropdown.toolTip() != ""
    assert widget._delete_button.toolTip() != ""
    assert widget._summary_csv_button.toolTip() != ""
    assert widget._summary_md_button.toolTip() != ""
    assert widget._detailed_csv_button.toolTip() != ""
    assert widget._detailed_md_button.toolTip() != ""
    assert widget._summary_detach_button.toolTip() != ""
    assert widget._detailed_detach_button.toolTip() != ""
    assert widget._summary_clear_filters_button.toolTip() != ""
    assert widget._detailed_clear_filters_button.toolTip() != ""
    assert widget._summary_also_save_checkbox.toolTip() != ""
    assert widget._details_also_save_checkbox.toolTip() != ""


@pytest.mark.unit
def test_log_widget_primary_buttons_have_tooltips(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    # Arrange
    mock_event_bus = mocker.Mock(spec=EventBus)
    mock_app_settings = mocker.Mock(spec=AppSettingsServiceApi)
    mock_app_settings.get_int.return_value = 10_000
    mock_app_settings.get.return_value = None

    # Act
    widget = LogWidget(event_bus=mock_event_bus, app_settings=mock_app_settings)

    # Assert
    assert widget._clean_button.toolTip() != ""
    assert widget._jump_button.toolTip() != ""
    assert widget._verbosity_combo.toolTip() != ""
    assert widget._search_edit.toolTip() != ""


@pytest.mark.unit
def test_test_models_widget_primary_buttons_have_tooltips(
    qapp: QApplication,
    mocker: MockerFixture,
) -> None:
    # Arrange
    mock_controller = mocker.Mock(spec=RunConfigController)
    mock_controller.get_provider_names.return_value = []

    # Act
    widget = TestModelsWidget(controller=mock_controller)

    # Assert
    assert widget._available_list.toolTip() != ""
