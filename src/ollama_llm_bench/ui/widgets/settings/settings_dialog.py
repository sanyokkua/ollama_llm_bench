import logging
from typing import Final

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.ui_controllers import SettingsWidgetControllerApi
from ollama_llm_bench.ui.widgets.settings.feature_flags_tab_widget import FeatureFlagsTabWidget
from ollama_llm_bench.ui.widgets.settings.providers_tab_widget import ProvidersTabWidget

logger = logging.getLogger(__name__)

_DIALOG_TITLE: Final[str] = "Settings"
_MIN_WIDTH: Final[int] = 700
_MIN_HEIGHT: Final[int] = 500
_TAB_PROVIDERS: Final[str] = "Providers"
_TAB_GENERAL: Final[str] = "General"


class SettingsDialog(QDialog):
    """Modal settings dialog with Providers and General tabs.

    Opens modally from MainWindow. Uses a Close-only button box — no OK/Cancel.
    Prompts to save unsaved General tab changes when closing while dirty.
    """

    def __init__(
        self,
        *,
        controller: SettingsWidgetControllerApi,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_DIALOG_TITLE)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self._setup_ui(controller)

    def _setup_ui(self, controller: SettingsWidgetControllerApi) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        self._general_tab = FeatureFlagsTabWidget(controller=controller)

        self._providers_tab = ProvidersTabWidget(controller=controller)

        tab_widget = QTabWidget()
        tab_widget.addTab(self._providers_tab, _TAB_PROVIDERS)
        tab_widget.addTab(self._general_tab, _TAB_GENERAL)
        layout.addWidget(tab_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.setContentsMargins(12, 4, 12, 0)
        button_box.rejected.connect(self.close)
        close_button = button_box.button(QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setDefault(True)
        layout.addWidget(button_box)

    def closeEvent(self, event: QCloseEvent) -> None:
        providers_dirty = self._providers_tab.is_dirty
        general_dirty = self._general_tab.is_dirty
        if not providers_dirty and not general_dirty:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. What would you like to do?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            if providers_dirty:
                self._providers_tab._handle_save_changes()
            if general_dirty:
                self._general_tab.save_settings()
            event.accept()
        elif answer == QMessageBox.StandardButton.Discard:
            event.accept()
        else:
            event.ignore()
