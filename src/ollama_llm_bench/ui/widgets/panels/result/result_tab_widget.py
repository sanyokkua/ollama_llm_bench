from dataclasses import dataclass, field

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QTabWidget

from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem
from ollama_llm_bench.ui.widgets.panels.result.log_widget import LogWidget
from ollama_llm_bench.ui.widgets.panels.result.result_widget import ResultWidget, ResultWidgetModel


@dataclass(frozen=True)
class ResultTabWidgetModel:
    runs: list[tuple[int, str]] = field(default_factory=lambda: [])
    summary_data: list[AvgSummaryTableItem] = field(default_factory=lambda: [])
    detailed_data: list[SummaryTableItem] = field(default_factory=lambda: [])


class ResultTabWidget(QTabWidget):
    btn_export_csv_summary_clicked = pyqtSignal()
    btn_export_md_summary_clicked = pyqtSignal()
    btn_export_csv_detailed_clicked = pyqtSignal()
    btn_export_md_detailed_clicked = pyqtSignal()
    btn_delete_run_clicked = pyqtSignal()
    dropdown_run_changed = pyqtSignal(int)

    def __init__(self, model: ResultTabWidgetModel) -> None:
        super().__init__()
        self._log_tab = LogWidget()

        self._result_tab = ResultWidget(ResultWidgetModel())
        self.addTab(self._log_tab, "System Log")
        self.addTab(self._result_tab, "Results")

        self._result_tab.btn_export_csv_summary_clicked.connect(self.btn_export_csv_summary_clicked)
        self._result_tab.btn_export_md_summary_clicked.connect(self.btn_export_md_summary_clicked)
        self._result_tab.btn_export_csv_detailed_clicked.connect(self.btn_export_csv_detailed_clicked)
        self._result_tab.btn_export_md_detailed_clicked.connect(self.btn_export_md_detailed_clicked)
        self._result_tab.btn_delete_run_clicked.connect(self.btn_delete_run_clicked)
        self._result_tab.dropdown_run_changed.connect(self.dropdown_run_changed)

        self.update_state(model)

    def update_state(self, model: ResultTabWidgetModel) -> None:
        tab_model = ResultWidgetModel(
            runs=model.runs,
            summary_data=model.summary_data,
            detailed_data=model.detailed_data,
        )
        self._result_tab.update_state(tab_model)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        if is_running:
            self.setCurrentIndex(self.indexOf(self._log_tab))
            self.tabBar().setTabsClosable(False)
            self.tabBar().setMovable(False)
            self.tabBar().setEnabled(False)
        else:
            self.tabBar().setEnabled(True)
        self._result_tab.set_benchmark_is_running(is_running)

    def log_append_text(self, text: str):
        self._log_tab.append_text(text)
