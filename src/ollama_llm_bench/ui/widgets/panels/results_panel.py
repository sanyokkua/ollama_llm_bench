import logging

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget

logger = logging.getLogger(__name__)


class ResultsPanel(QWidget):
    """Container widget for benchmark results display."""

    def __init__(self, *, controller: ResultWidgetControllerApi) -> None:
        super().__init__()
        logger.debug("Initializing ResultsPanel")

        self._result_widget: ResultWidget = ResultWidget(controller)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._result_widget, 1)
        self.setLayout(layout)

        logger.info("ResultsPanel initialized successfully")
