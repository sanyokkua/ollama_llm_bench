import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.central_widget import CentralWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, ctx: AppContext) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Ollama LLM Benchmarker v1.0")
        self.resize(1200, 800)

        # Create a central widget and layout
        central_widget = CentralWidget(ctx)
        self.setCentralWidget(central_widget)

        # Set window flags for a better look and feel on macOS
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MacWindowToolBarButtonHint)
        ctx.send_initialization_events()
        ctx.get_event_bus().subscribe_to_global_event_msg(MainWindow.show_global_msg)

    @staticmethod
    def show_global_msg(text: Optional[str]):
        if text is not None:
            reply = QMessageBox()
            reply.setText(text)
            reply.setStandardButtons(QMessageBox.StandardButton.Ok)
            reply.exec()
