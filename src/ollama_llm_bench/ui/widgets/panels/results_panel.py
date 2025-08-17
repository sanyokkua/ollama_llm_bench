import logging

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.result.result_tab_widget import ResultTabWidget

logger = logging.getLogger(__name__)


class ResultsPanel(QWidget):
    """
    Container widget for benchmark results display.
    Hosts the result tabs (logs and results) with proper layout configuration.
    """

    def __init__(self, ctx: AppContext) -> None:
        """
        Initialize the results panel.

        Args:
            ctx: Application context providing access to controller APIs.
        """
        super().__init__()
        logger.debug("Initializing ResultsPanel")

        self._tab_widget: ResultTabWidget = ResultTabWidget(ctx)

        # Configure layout with proper spacing
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Clean edge-to-edge layout
        layout.addWidget(self._tab_widget, 1)  # Allow expansion
        self.setLayout(layout)

        logger.info("ResultsPanel initialized successfully")
