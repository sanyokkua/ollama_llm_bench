from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QTabWidget

from ollama_llm_bench.ui.widgets.panels.control.new_run_widget import (
    NewRunWidget,
    NewRunWidgetModel,
    NewRunWidgetStartEvent,
)
from ollama_llm_bench.ui.widgets.panels.control.previous_run_widget import PreviousRunWidget, PreviousRunWidgetModel


class ControlTabWidget(QTabWidget):
    btn_new_run_stop_clicked = pyqtSignal()
    btn_new_run_start_clicked = pyqtSignal(NewRunWidgetStartEvent)
    btn_new_run_refresh_clicked = pyqtSignal()
    btn_prev_run_refresh_clicked = pyqtSignal()
    btn_prev_run_stop_clicked = pyqtSignal()
    btn_prev_run_start_clicked = pyqtSignal(int)

    def __init__(self, new_run_model: NewRunWidgetModel, prev_run_model: PreviousRunWidgetModel) -> None:
        super().__init__()
        self._new_benchmark_tab = NewRunWidget(new_run_model)
        self._previous_benchmark_tab = PreviousRunWidget(prev_run_model)

        self.addTab(self._new_benchmark_tab, "Run New Benchmark")
        self.addTab(self._previous_benchmark_tab, "Run Previous Benchmark")

        self._new_benchmark_tab.btn_stop_clicked.connect(self.btn_new_run_stop_clicked)
        self._new_benchmark_tab.btn_start_clicked.connect(self.btn_new_run_start_clicked)
        self._new_benchmark_tab.btn_refresh_clicked.connect(self.btn_new_run_refresh_clicked)
        self._previous_benchmark_tab.btn_refresh_clicked.connect(self.btn_prev_run_refresh_clicked)
        self._previous_benchmark_tab.btn_stop_clicked.connect(self.btn_prev_run_stop_clicked)
        self._previous_benchmark_tab.btn_start_clicked.connect(self.btn_prev_run_start_clicked)

    def refresh_widgets_data_for_new_run(self, model: NewRunWidgetModel) -> None:
        self._new_benchmark_tab.refresh_widgets_data(model)

    def refresh_widgets_data_for_prev_run(self, model: PreviousRunWidgetModel) -> None:
        self._previous_benchmark_tab.refresh_widgets_data(model)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._new_benchmark_tab.set_benchmark_is_running(is_running)
        self._previous_benchmark_tab.set_benchmark_is_running(is_running)
