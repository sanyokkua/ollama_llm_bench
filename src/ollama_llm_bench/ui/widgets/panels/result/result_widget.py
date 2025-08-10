from dataclasses import dataclass, field
from typing import List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem


@dataclass(frozen=True)
class ResultWidgetModel:
    runs: list[tuple[int, str]] = field(default_factory=lambda: [])
    summary_data: List[AvgSummaryTableItem] = field(default_factory=lambda: [])
    detailed_data: List[SummaryTableItem] = field(default_factory=lambda: [])


TABLE_SUMMARY_HEADER = ["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE (%)"]
TABLE_DETAILED_HEADER = ["MODEL", "Task", "TIME (ms)", "Tokens", "TOKENS/s", "SCORE", "REASON"]


class ResultWidget(QWidget):
    btn_export_csv_summary_clicked = pyqtSignal()
    btn_export_md_summary_clicked = pyqtSignal()
    btn_export_csv_detailed_clicked = pyqtSignal()
    btn_export_md_detailed_clicked = pyqtSignal()
    btn_delete_run_clicked = pyqtSignal()
    dropdown_run_changed = pyqtSignal(int)

    def __init__(self, model: ResultWidgetModel):
        super().__init__()
        self._run_label = QLabel("Run Results:")
        self._run_dropdown = QComboBox()
        self._summary_label = QLabel("Summary: Average Performance per Model")
        self._delete_button = QPushButton("Delete")
        self._detailed_label = QLabel("Detailed Results for Run #5")
        self._summary_csv_button = QPushButton("Export as CSV")
        self._summary_md_button = QPushButton("Export as Markdown")
        self._detailed_csv_button = QPushButton("Export as CSV")
        self._detailed_md_button = QPushButton("Export as Markdown")
        self._summary_table = QTableWidget(0, 4)
        self._detailed_table = QTableWidget(0, 7)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self._run_label)
        top_layout.addWidget(self._run_dropdown)
        top_layout.addWidget(self._delete_button)
        top_layout.addStretch()

        summary_scroll = QScrollArea()
        summary_scroll.setWidgetResizable(True)
        summary_scroll.setWidget(self._summary_table)
        summary_export_layout = QHBoxLayout()
        summary_export_layout.addWidget(self._summary_csv_button)
        summary_export_layout.addWidget(self._summary_md_button)
        summary_layout = QVBoxLayout()
        summary_layout.addWidget(self._summary_label)
        summary_layout.addWidget(summary_scroll)
        summary_layout.addLayout(summary_export_layout)

        detailed_scroll = QScrollArea()
        detailed_scroll.setWidgetResizable(True)
        detailed_scroll.setWidget(self._detailed_table)
        detailed_export_layout = QHBoxLayout()
        detailed_export_layout.addWidget(self._detailed_csv_button)
        detailed_export_layout.addWidget(self._detailed_md_button)
        detailed_layout = QVBoxLayout()
        detailed_layout.addWidget(self._detailed_label)
        detailed_layout.addWidget(detailed_scroll)
        detailed_layout.addLayout(detailed_export_layout)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addSpacing(10)
        main_layout.addLayout(summary_layout)
        main_layout.addSpacing(10)
        main_layout.addLayout(detailed_layout)
        self.setLayout(main_layout)

        self._summary_table.setHorizontalHeaderLabels(TABLE_SUMMARY_HEADER)
        self._summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._detailed_table.setHorizontalHeaderLabels(TABLE_DETAILED_HEADER)
        self._detailed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self._run_dropdown.currentIndexChanged.connect(self._on_item_changed)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        self._summary_csv_button.clicked.connect(self.btn_export_csv_summary_clicked)
        self._summary_md_button.clicked.connect(self.btn_export_md_summary_clicked)
        self._detailed_csv_button.clicked.connect(self.btn_export_csv_detailed_clicked)
        self._detailed_md_button.clicked.connect(self.btn_export_md_detailed_clicked)

        self.update_state(model)

    def _on_item_changed(self):
        current_index = self._run_dropdown.currentIndex()
        if current_index >= 0:
            run_id = self._run_dropdown.itemData(current_index)
            self.dropdown_run_changed.emit(run_id)

    def _on_delete_clicked(self):
        self.btn_delete_run_clicked.emit()

    def _set_run_options(self, run_ids: list[tuple[int, str]]):
        self._run_dropdown.clear()
        for run_id, name in run_ids:
            self._run_dropdown.addItem(name, run_id)

    def _set_summary_data(self, data: List[AvgSummaryTableItem]):
        self._summary_table.setRowCount(len(data))

        for row, item in enumerate(data):
            self._summary_table.setItem(row, 0, QTableWidgetItem(item.model_name))
            self._summary_table.setItem(row, 1, QTableWidgetItem(f"{item.avg_time_ms / 1000:.2f}"))
            self._summary_table.setItem(row, 2, QTableWidgetItem(f"{item.avg_tokens_per_second:.2f}"))
            self._summary_table.setItem(row, 3, QTableWidgetItem(f"{item.avg_score:.2f}"))

    def _set_detailed_data(self, data: List[SummaryTableItem]):
        self._detailed_table.setRowCount(len(data))

        for row, item in enumerate(data):
            self._detailed_table.setItem(row, 0, QTableWidgetItem(item.model_name))
            self._detailed_table.setItem(row, 1, QTableWidgetItem(item.task_id))
            self._detailed_table.setItem(row, 2, QTableWidgetItem(str(item.time_ms)))
            self._detailed_table.setItem(row, 3, QTableWidgetItem(str(item.tokens)))
            self._detailed_table.setItem(row, 4, QTableWidgetItem(f"{item.tokens_per_second:.2f}"))
            self._detailed_table.setItem(row, 5, QTableWidgetItem(f"{item.score:.2f}"))
            self._detailed_table.setItem(row, 6, QTableWidgetItem(item.score_reason))

    def update_state(self, model: ResultWidgetModel):
        self._set_run_options(model.runs)
        self._set_summary_data(model.summary_data)
        self._set_detailed_data(model.detailed_data)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._run_label.setEnabled(not is_running)
        self._run_dropdown.setEnabled(not is_running)
        self._summary_label.setEnabled(not is_running)
        self._delete_button.setEnabled(not is_running)
        self._detailed_label.setEnabled(not is_running)
        self._summary_csv_button.setEnabled(not is_running)
        self._summary_md_button.setEnabled(not is_running)
        self._detailed_csv_button.setEnabled(not is_running)
        self._detailed_md_button.setEnabled(not is_running)
        self._summary_table.setEnabled(not is_running)
        self._detailed_table.setEnabled(not is_running)
