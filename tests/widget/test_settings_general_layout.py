"""Tests verifying that FeatureFlagsTabWidget group bodies use QFormLayout."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QFormLayout, QGroupBox, QLayout
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.widgets.settings.feature_flags_tab_widget import FeatureFlagsTabWidget

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
# Helpers
# ---------------------------------------------------------------------------


def _find_form_layout(group: QGroupBox) -> QFormLayout | None:
    """Return the first QFormLayout found in the group's outer layout, or None."""
    outer = group.layout()
    if outer is None:
        return None
    for i in range(outer.count()):
        item = outer.itemAt(i)
        if item is None:
            continue
        candidate: QLayout | None = item.layout()
        if isinstance(candidate, QFormLayout):
            return candidate
    return None


def _find_group_by_title(widget: FeatureFlagsTabWidget, title: str) -> QGroupBox | None:
    for box in widget.findChildren(QGroupBox):
        if isinstance(box, QGroupBox) and box.title() == title:
            return box
    return None


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def feature_flags_widget(qapp: QApplication, mocker: MockerFixture) -> FeatureFlagsTabWidget:
    mock_ctrl = mocker.Mock(spec=SettingsWidgetControllerApi)
    mock_ctrl.get_setting.return_value = None
    mock_ctrl.get_setting_bool.return_value = False
    mock_ctrl.get_setting_int.return_value = 0
    mock_ctrl.get_setting_float.return_value = 0.0
    return FeatureFlagsTabWidget(controller=mock_ctrl)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inference_group_uses_form_layout(feature_flags_widget: FeatureFlagsTabWidget) -> None:
    # Arrange
    group = _find_group_by_title(feature_flags_widget, "Inference")

    # Act
    form = _find_form_layout(group) if group is not None else None

    # Assert
    assert group is not None, "QGroupBox titled 'Inference' not found"
    assert isinstance(form, QFormLayout), "Inference group body must use QFormLayout"


def test_evaluation_group_uses_form_layout(feature_flags_widget: FeatureFlagsTabWidget) -> None:
    # Arrange
    group = _find_group_by_title(feature_flags_widget, "Evaluation")

    # Act
    form = _find_form_layout(group) if group is not None else None

    # Assert
    assert group is not None, "QGroupBox titled 'Evaluation' not found"
    assert isinstance(form, QFormLayout), "Evaluation group body must use QFormLayout"


def test_logging_group_uses_form_layout(feature_flags_widget: FeatureFlagsTabWidget) -> None:
    # Arrange
    group = _find_group_by_title(feature_flags_widget, "Logging")

    # Act
    form = _find_form_layout(group) if group is not None else None

    # Assert
    assert group is not None, "QGroupBox titled 'Logging' not found"
    assert isinstance(form, QFormLayout), "Logging group body must use QFormLayout"


def test_display_group_uses_form_layout(feature_flags_widget: FeatureFlagsTabWidget) -> None:
    # Arrange
    group = _find_group_by_title(feature_flags_widget, "Display")

    # Act
    form = _find_form_layout(group) if group is not None else None

    # Assert
    assert group is not None, "QGroupBox titled 'Display' not found"
    assert isinstance(form, QFormLayout), "Display group body must use QFormLayout"
