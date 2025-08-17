import logging
from typing import Final, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox)

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.central_widget import CentralWidget

logger = logging.getLogger(__name__)

_WINDOW_TITLE: Final[str] = "Ollama LLM Benchmarker v1.0"
_WINDOW_WIDTH: Final[int] = 1200
_WINDOW_HEIGHT: Final[int] = 800


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
        self._setup_ui()
        self._setup_event_handlers()

    def _setup_ui(self) -> None:
        """
        Configure window properties and layout.
        Sets up the central widget and platform-specific window features.
        """
        self.setWindowTitle(_WINDOW_TITLE)
        self.resize(_WINDOW_WIDTH, _WINDOW_HEIGHT)

        # Central widget setup
        central_widget = CentralWidget(self._ctx)
        self.setCentralWidget(central_widget)

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

    def _show_global_message(self, text: Optional[str]) -> None:
        """
        Safely display global messages with proper parenting.

        Args:
            text: Message text to display, or None to skip.
        """
        if not text:
            return

        # Use active window as parent for proper stacking
        parent = QApplication.activeWindow() or self
        QMessageBox.information(
            parent,
            "Notification",
            text,
            QMessageBox.StandardButton.Ok,
        )
