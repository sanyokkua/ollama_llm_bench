from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMainWindow

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.central_widget import CentralWidget


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
        ctx.get_benchmark_controller_api().send_initial_state()
