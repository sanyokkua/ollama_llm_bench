import logging
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from ollama_llm_bench.backend.core.interfaces import AppContext
from ollama_llm_bench.ui.qt_classes.notification_service import NotificationService
from ollama_llm_bench.ui.widgets.central_widget import CentralWidget
from ollama_llm_bench.ui.widgets.settings.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

_WINDOW_TITLE: Final[str] = "Ollama LLM Bench v2.0"
_WINDOW_WIDTH: Final[int] = 1200
_WINDOW_HEIGHT: Final[int] = 800
_FILE_MENU_LABEL: Final[str] = "File"
_SETTINGS_MENU_LABEL: Final[str] = "Settings"
_CONFIRM_STOP_TITLE: Final[str] = "Benchmark Running"
_CONFIRM_STOP_MSG: Final[str] = "A benchmark is in progress. Stop it and exit?"
_SHUTDOWN_TIMEOUT_MS: Final[int] = 5000


class MainWindow(QMainWindow):
    """Main application window with proper resource management and UI safety."""

    def __init__(self, ctx: AppContext) -> None:
        """
        Initialize the main application window.

        Args:
            ctx: Application context providing access to controllers and services.
        """
        super().__init__()
        self._ctx = ctx  # Store context reference for cleanup
        self._notification_service: NotificationService
        self._setup_ui()
        self._setup_event_handlers()

    def _setup_ui(self) -> None:
        """
        Configure window properties and layout.
        Sets up the central widget and platform-specific window features.
        """
        self.setWindowTitle(_WINDOW_TITLE)
        self.resize(_WINDOW_WIDTH, _WINDOW_HEIGHT)
        self.setMinimumSize(1200, 700)

        # Central widget setup
        central_widget = CentralWidget(self._ctx)
        self.setCentralWidget(central_widget)

        self._notification_service = NotificationService(status_bar=self.statusBar())

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu(_FILE_MENU_LABEL)
        settings_action = file_menu.addAction(_SETTINGS_MENU_LABEL)
        settings_action.triggered.connect(self._open_settings)

        # Platform-specific enhancements
        if QApplication.platformName() == "darwin":
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowType.MacWindowToolBarButtonHint,
            )

    def _setup_event_handlers(self) -> None:
        """
        Configure event subscriptions and initialization.
        Subscribes to global event messages and sends initialization events.
        """
        self._ctx.send_initialization_events()
        self._ctx.get_event_bus().subscribe_to_global_event_msg(
            self._show_global_message,
        )

    def _open_settings(self) -> None:
        """Open the settings dialog modally, blocked during an active benchmark."""
        if self._ctx.get_benchmark_flow_api().is_running():
            # Lifecycle dialog — not routed through NotificationService
            QMessageBox.information(
                self,
                "Benchmark Running",
                "Settings cannot be changed while a benchmark is in progress.",
                QMessageBox.StandardButton.Ok,
            )
            return
        controller = self._ctx.get_settings_widget_controller()
        dialog = SettingsDialog(controller=controller, parent=self)
        dialog.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop any running benchmark before closing the window."""
        if self._ctx.get_benchmark_flow_api().is_running():
            # Lifecycle dialog — not routed through NotificationService
            reply = QMessageBox.question(
                self,
                _CONFIRM_STOP_TITLE,
                _CONFIRM_STOP_MSG,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        logger.info("Main window closing — initiating shutdown")
        self._ctx.get_benchmark_flow_api().shutdown(timeout_ms=_SHUTDOWN_TIMEOUT_MS)
        event.accept()

    def _show_global_message(self, text: str | None) -> None:
        """
        Route global event-bus messages to the status bar.

        Args:
            text: Message text to display, or None to skip.
        """
        if not text:
            return
        self._notification_service.show_info(text)
