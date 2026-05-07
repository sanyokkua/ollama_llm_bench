"""Unit tests for ResultWidget — benchmark-sensitive widget locking behaviour."""

from typing import cast

import pytest
from PySide6.QtWidgets import QApplication
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget

# ---------------------------------------------------------------------------
# QApplication fixture — module scope so Qt is initialised exactly once
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Return (or create) a QApplication instance for the module."""
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


# ---------------------------------------------------------------------------
# Mock controller + widget fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_controller(mocker: MockerFixture) -> ResultWidgetControllerApi:
    """Return a spec-correct mock for ResultWidgetControllerApi."""
    ctrl = mocker.Mock(spec=ResultWidgetControllerApi)
    ctrl.get_also_save_to_default.return_value = False
    return cast(ResultWidgetControllerApi, ctrl)


@pytest.fixture
def widget(qapp: QApplication, mock_controller: ResultWidgetControllerApi) -> ResultWidget:
    """Construct a fresh ResultWidget per test with a mock controller."""
    return ResultWidget(controller=mock_controller)


# ---------------------------------------------------------------------------
# Test 1 — table views remain interactive while benchmark is running
# ---------------------------------------------------------------------------


def test_tables_remain_enabled_when_benchmark_is_running(
    widget: ResultWidget,
) -> None:
    # Arrange — widget is freshly constructed

    # Act
    widget._on_benchmark_is_running_changed(True)

    # Assert — table views are NOT in the benchmark_sensitive_widgets list
    assert widget._summary_view.isEnabled() is True
    assert widget._detailed_view.isEnabled() is True


# ---------------------------------------------------------------------------
# Test 2 — save-checkboxes are disabled while benchmark is running
# ---------------------------------------------------------------------------


def test_save_checkboxes_disabled_when_benchmark_is_running(
    widget: ResultWidget,
) -> None:
    # Arrange — widget is freshly constructed

    # Act
    widget._on_benchmark_is_running_changed(True)

    # Assert
    assert widget._summary_also_save_checkbox.isEnabled() is False
    assert widget._details_also_save_checkbox.isEnabled() is False


# ---------------------------------------------------------------------------
# Test 3 — all controls re-enabled when benchmark stops
# ---------------------------------------------------------------------------


def test_all_controls_re_enabled_when_benchmark_stops(
    widget: ResultWidget,
) -> None:
    # Arrange
    widget._on_benchmark_is_running_changed(True)

    # Act
    widget._on_benchmark_is_running_changed(False)

    # Assert
    assert widget._summary_also_save_checkbox.isEnabled() is True
    assert widget._summary_csv_button.isEnabled() is True
