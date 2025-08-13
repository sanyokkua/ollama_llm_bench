from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.control_panel import ControlPanel
from ollama_llm_bench.ui.widgets.panels.results_panel import ResultsPanel


class CentralWidget(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._control_panel = ControlPanel(ctx)
        self._results_tab = ResultsPanel(ctx)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._control_panel)
        splitter.addWidget(self._results_tab)
        splitter.setSizes([100, 900])

        layout = QVBoxLayout()
        layout.addWidget(splitter)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
