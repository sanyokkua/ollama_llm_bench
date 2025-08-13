from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.result.result_tab_widget import ResultTabWidget


class ResultsPanel(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()

        self._tab_widget = ResultTabWidget(ctx)

        layout = QVBoxLayout()
        layout.addWidget(self._tab_widget)
        self.setLayout(layout)
