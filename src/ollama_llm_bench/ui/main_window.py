import logging
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox

from ollama_llm_bench.backend.core.interfaces import AppContext
from ollama_llm_bench.backend.core.models import AppReadinessChangedEvent
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
        self._ready_indicator: QLabel
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

        self._ready_indicator = QLabel("Checking…")
        self._ready_indicator.setContentsMargins(4, 0, 8, 0)
        self.statusBar().addPermanentWidget(self._ready_indicator)

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
            parent=self,
        )
        self._ctx.get_event_bus().subscribe_to_app_readiness_changed(self._on_readiness_changed, parent=self)

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

    def _on_readiness_changed(self, event: AppReadinessChangedEvent) -> None:
        """Update the permanent status bar indicator to reflect current app readiness.

        Args:
            event: Snapshot describing provider health, model availability, and embedding status.
        """
        if not event.has_any_models:
            text = "No models available"
            colour = "#c0392b"
            tooltip = "No enabled provider returned any models.\nOpen Settings → Providers to configure a provider."
        elif event.unhealthy_providers or not event.embedding_ok:
            parts: list[str] = []
            tip_parts: list[str] = []
            if event.unhealthy_providers:
                parts.append(f"{len(event.unhealthy_providers)} provider(s) unreachable")
                tip_parts.append("Unreachable: " + ", ".join(event.unhealthy_providers))
            if not event.embedding_ok:
                parts.append("embedding unavailable")
                tip_parts.append(event.embedding_error or "Embedding model unreachable.")
            text = "Degraded: " + ", ".join(parts)
            colour = "#e67e22"
            tooltip = "\n".join(tip_parts) + "\nOpen Settings → Providers to investigate."
        else:
            text = "Ready"
            colour = "#27ae60"
            tooltip = "All providers healthy."
        self._ready_indicator.setText(text)
        self._ready_indicator.setStyleSheet(f"color: {colour}; font-weight: bold;")
        self._ready_indicator.setToolTip(tooltip)

    def _show_global_message(self, text: str | None) -> None:
        """
        Route global event-bus messages to the status bar.

        Args:
            text: Message text to display, or None to skip.
        """
        if not text:
            return
        self._notification_service.show_info(text)
