"""Unit tests for FeatureFlagsTabWidget and SettingsDialog (General tab)."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
)
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.core.models import EmbeddingConfig, ProvidersConfig
from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.widgets.settings.feature_flags_tab_widget import FeatureFlagsTabWidget
from ollama_llm_bench.ui.widgets.settings.settings_dialog import SettingsDialog

_EMPTY_PROVIDERS_CONFIG = ProvidersConfig(
    providers=(),
    embedding=EmbeddingConfig(provider_id="ollama_local", model="bge-m3"),
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    instance = QApplication.instance()
    if isinstance(instance, QApplication):
        return instance
    return QApplication([])


def _make_controller(mocker: MockerFixture) -> MagicMock:
    mock = cast(MagicMock, mocker.Mock(spec=SettingsWidgetControllerApi))
    mock.get_setting.return_value = None
    mock.get_setting_bool.return_value = False
    mock.get_setting_int.return_value = 0
    mock.get_setting_float.return_value = 0.0
    mock.get_providers_config.return_value = _EMPTY_PROVIDERS_CONFIG
    return mock


@pytest.fixture()
def controller(mocker: MockerFixture) -> MagicMock:
    return _make_controller(mocker)


@pytest.fixture()
def tab_widget(qapp: QApplication, controller: MagicMock) -> FeatureFlagsTabWidget:
    return FeatureFlagsTabWidget(controller=cast(SettingsWidgetControllerApi, controller))


# ---------------------------------------------------------------------------
# TestTabLabel
# ---------------------------------------------------------------------------


class TestTabLabel:
    def test_tab_label_in_settings_dialog_is_general(self, qapp: QApplication, mocker: MockerFixture) -> None:
        ctrl = _make_controller(mocker)
        dlg = SettingsDialog(controller=cast(SettingsWidgetControllerApi, ctrl))
        tab_widget = dlg.findChild(QTabWidget)
        assert tab_widget is not None
        tab_texts = [tab_widget.tabText(i) for i in range(tab_widget.count())]
        assert "General" in tab_texts


# ---------------------------------------------------------------------------
# TestSpinboxArrows
# ---------------------------------------------------------------------------


class TestSpinboxArrows:
    def test_all_spinboxes_have_up_down_arrows(self, tab_widget: FeatureFlagsTabWidget) -> None:
        for spinbox in tab_widget.findChildren(QSpinBox):
            assert spinbox.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.UpDownArrows, (
                f"QSpinBox {spinbox.objectName()!r} has wrong button symbols"
            )

    def test_all_double_spinboxes_have_up_down_arrows(self, tab_widget: FeatureFlagsTabWidget) -> None:
        for spinbox in tab_widget.findChildren(QDoubleSpinBox):
            assert spinbox.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.UpDownArrows, (
                f"QDoubleSpinBox {spinbox.objectName()!r} has wrong button symbols"
            )


# ---------------------------------------------------------------------------
# TestComboBoxTypes
# ---------------------------------------------------------------------------


class TestComboBoxTypes:
    def test_reasoning_effort_has_default_item(self, tab_widget: FeatureFlagsTabWidget) -> None:
        combo = tab_widget._reasoning_combo
        assert combo.findData("default") >= 0

    def test_reasoning_effort_has_all_items(self, tab_widget: FeatureFlagsTabWidget) -> None:
        combo = tab_widget._reasoning_combo
        data_values = [combo.itemData(i) for i in range(combo.count())]
        assert "default" in data_values
        assert "low" in data_values
        assert "medium" in data_values
        assert "high" in data_values

    def test_log_verbosity_items_are_minimal_normal_verbose(self, tab_widget: FeatureFlagsTabWidget) -> None:
        combo = tab_widget._log_verbosity_combo
        data_values = [combo.itemData(i) for i in range(combo.count())]
        assert "minimal" in data_values
        assert "normal" in data_values
        assert "verbose" in data_values

    def test_theme_default_is_system(self, tab_widget: FeatureFlagsTabWidget) -> None:
        assert tab_widget._theme_combo.currentData() == "system"

    def test_theme_has_all_items(self, tab_widget: FeatureFlagsTabWidget) -> None:
        combo = tab_widget._theme_combo
        data_values = [combo.itemData(i) for i in range(combo.count())]
        assert "system" in data_values
        assert "dark" in data_values
        assert "light" in data_values

    def test_score_format_has_example_previews(self, tab_widget: FeatureFlagsTabWidget) -> None:
        combo = tab_widget._score_format_combo
        texts = [combo.itemText(i) for i in range(combo.count())]
        joined = " ".join(texts)
        assert "0.85" in joined
        assert "85%" in joined

    def test_score_format_has_all_data_values(self, tab_widget: FeatureFlagsTabWidget) -> None:
        combo = tab_widget._score_format_combo
        data_values = [combo.itemData(i) for i in range(combo.count())]
        assert "decimal" in data_values
        assert "percent" in data_values
        assert "both" in data_values

    def test_score_format_default_is_decimal(self, tab_widget: FeatureFlagsTabWidget) -> None:
        assert tab_widget._score_format_combo.currentData() == "decimal"


# ---------------------------------------------------------------------------
# TestDirtyState
# ---------------------------------------------------------------------------


class TestDirtyState:
    def test_save_button_disabled_on_load(self, tab_widget: FeatureFlagsTabWidget) -> None:
        assert not tab_widget._save_button.isEnabled()

    def test_is_dirty_false_on_load(self, tab_widget: FeatureFlagsTabWidget) -> None:
        assert not tab_widget.is_dirty

    def test_save_button_enabled_after_checkbox_toggle(self, tab_widget: FeatureFlagsTabWidget) -> None:
        original = tab_widget._streaming_checkbox.isChecked()
        tab_widget._streaming_checkbox.setChecked(not original)
        assert tab_widget._save_button.isEnabled()
        assert tab_widget.is_dirty

    def test_dirty_flag_cleared_after_save(self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock) -> None:
        tab_widget._streaming_checkbox.setChecked(not tab_widget._streaming_checkbox.isChecked())
        assert tab_widget.is_dirty
        tab_widget.save_settings()
        assert not tab_widget.is_dirty

    def test_save_button_text_changes_when_dirty(self, tab_widget: FeatureFlagsTabWidget) -> None:
        tab_widget._streaming_checkbox.setChecked(not tab_widget._streaming_checkbox.isChecked())
        assert "*" in tab_widget._save_button.text()

    def test_save_button_text_restored_after_save(
        self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock
    ) -> None:
        tab_widget._streaming_checkbox.setChecked(not tab_widget._streaming_checkbox.isChecked())
        tab_widget.save_settings()
        assert "*" not in tab_widget._save_button.text()


# ---------------------------------------------------------------------------
# TestLogFolder
# ---------------------------------------------------------------------------


class TestLogFolder:
    def test_open_log_folder_calls_desktop_services(self, tab_widget: FeatureFlagsTabWidget) -> None:
        with patch(
            "ollama_llm_bench.ui.widgets.settings.feature_flags_tab_widget.QDesktopServices.openUrl",
            return_value=True,
        ) as mock_open:
            tab_widget._open_log_folder_btn.click()
            assert mock_open.called

    def test_copy_path_writes_to_clipboard(self, tab_widget: FeatureFlagsTabWidget, qapp: QApplication) -> None:
        from ollama_llm_bench.backend.core.app_paths import get_user_data_dir

        tab_widget._copy_path_btn.click()
        assert QApplication.clipboard().text() == str(get_user_data_dir())


# ---------------------------------------------------------------------------
# TestReset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_requires_confirmation(self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock) -> None:
        with patch(
            "ollama_llm_bench.ui.widgets.settings.feature_flags_tab_widget.QMessageBox.question",
            return_value=0x00400000,  # QMessageBox.StandardButton.Cancel
        ):
            tab_widget._reset_to_defaults()
            controller.reset_settings.assert_not_called()

    def test_reset_calls_controller_when_confirmed(
        self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        with patch(
            "ollama_llm_bench.ui.widgets.settings.feature_flags_tab_widget.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            tab_widget._reset_to_defaults()
            controller.reset_settings.assert_called_once()


# ---------------------------------------------------------------------------
# TestSave
# ---------------------------------------------------------------------------


class TestSave:
    def test_save_calls_emit_settings_changed(self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock) -> None:
        tab_widget._streaming_checkbox.setChecked(not tab_widget._streaming_checkbox.isChecked())
        tab_widget.save_settings()
        controller.emit_settings_changed.assert_called_once()

    def test_save_does_nothing_when_not_dirty(self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock) -> None:
        tab_widget.save_settings()
        controller.set_setting.assert_not_called()
        controller.emit_settings_changed.assert_not_called()

    def test_save_writes_only_dirty_keys(self, tab_widget: FeatureFlagsTabWidget, controller: MagicMock) -> None:
        tab_widget._streaming_checkbox.setChecked(not tab_widget._streaming_checkbox.isChecked())
        tab_widget.save_settings()
        from ollama_llm_bench.backend.services.app_settings_service import SETTING_STREAMING_ENABLED

        saved_keys = [call.args[0] for call in controller.set_setting.call_args_list]
        assert SETTING_STREAMING_ENABLED in saved_keys
        assert len(saved_keys) == 1
