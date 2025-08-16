import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QMainWindow, QMessageBox)  # Added for proper parent handling

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.central_widget import CentralWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with proper resource management and UI safety."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx  # Store context reference for cleanup
        self._setup_ui()
        self._setup_event_handlers()

    def _setup_ui(self) -> None:
        """Configure window properties and layout."""
        self.setWindowTitle("Ollama LLM Benchmarker v1.0")
        self.resize(1200, 800)

        # Central widget setup
        central_widget = CentralWidget(self._ctx)
        self.setCentralWidget(central_widget)

        # Platform-specific enhancements
        if QApplication.platformName() == "darwin":
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowType.MacWindowToolBarButtonHint,
            )

    def _setup_event_handlers(self) -> None:
        """Configure event subscriptions and initialization."""
        self._ctx.send_initialization_events()
        self._ctx.get_event_bus().subscribe_to_global_event_msg(
            self._show_global_message,
        )

    def _show_global_message(self, text: Optional[str]) -> None:
        """Safely display global messages with proper parenting."""
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
