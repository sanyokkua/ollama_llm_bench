from PyQt6.QtWidgets import QTabWidget

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.ui.widgets.panels.control.new_run_widget import (
    NewRunWidget,
)
from ollama_llm_bench.ui.widgets.panels.control.previous_run_widget import PreviousRunWidget


class ControlTabWidget(QTabWidget):

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._new_benchmark_tab = NewRunWidget(ctx.get_new_run_widget_controller_api())
        self._previous_benchmark_tab = PreviousRunWidget(ctx.get_previous_run_widget_controller_api())

        self.addTab(self._new_benchmark_tab, "Run New Benchmark")
        self.addTab(self._previous_benchmark_tab, "Run Previous Benchmark")
