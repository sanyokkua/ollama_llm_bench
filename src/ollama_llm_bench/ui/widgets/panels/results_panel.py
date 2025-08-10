from dataclasses import dataclass, field

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem
from ollama_llm_bench.ui.widgets.panels.result.result_tab_widget import ResultTabWidget, ResultTabWidgetModel


@dataclass(frozen=True)
class ResultsPanelModel:
    runs: list[tuple[int, str]]
    summary_data: list[AvgSummaryTableItem] = field(default_factory=lambda: [])
    detailed_data: list[SummaryTableItem] = field(default_factory=lambda: [])


class ResultsPanel(QWidget):
    btn_export_csv_summary_clicked = pyqtSignal()
    btn_export_md_summary_clicked = pyqtSignal()
    btn_export_csv_detailed_clicked = pyqtSignal()
    btn_export_md_detailed_clicked = pyqtSignal()
    btn_delete_run_clicked = pyqtSignal()
    dropdown_run_changed = pyqtSignal(int)

    def __init__(self, model: ResultsPanelModel) -> None:
        super().__init__()

        self._tab_widget = ResultTabWidget(ResultTabWidgetModel())

        layout = QVBoxLayout()
        layout.addWidget(self._tab_widget)
        self.setLayout(layout)

        self._tab_widget.btn_export_csv_summary_clicked.connect(self.btn_export_csv_summary_clicked)
        self._tab_widget.btn_export_md_summary_clicked.connect(self.btn_export_md_summary_clicked)
        self._tab_widget.btn_export_csv_detailed_clicked.connect(self.btn_export_csv_detailed_clicked)
        self._tab_widget.btn_export_md_detailed_clicked.connect(self.btn_export_md_detailed_clicked)
        self._tab_widget.btn_delete_run_clicked.connect(self.btn_delete_run_clicked)
        self._tab_widget.dropdown_run_changed.connect(self.dropdown_run_changed)

        self.update_state(model)

    def update_state(self, model: ResultsPanelModel) -> None:
        tab_model = ResultTabWidgetModel(
            runs=model.runs,
            summary_data=model.summary_data,
            detailed_data=model.detailed_data,
        )
        self._tab_widget.update_state(tab_model)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._tab_widget.set_benchmark_is_running(is_running)

    def log_append_text(self, text: str):
        self._tab_widget.log_append_text(text)
