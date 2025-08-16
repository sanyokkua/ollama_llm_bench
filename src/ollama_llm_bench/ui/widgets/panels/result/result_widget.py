import logging
from typing import List

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

from ollama_llm_bench.core.controllers import ResultWidgetControllerApi
from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem

logger = logging.getLogger(__name__)

TABLE_SUMMARY_HEADER = ["MODEL", "AVG. TIME (s)", "AVG. TOKENS/s", "AVG. SCORE (%)"]
TABLE_DETAILED_HEADER = ["MODEL", "TASK", "STATUS", "TIME (ms)", "Tokens", "TOKENS/s", "SCORE", "REASON"]


class ResultWidget(QWidget):
    def __init__(self, controller: ResultWidgetControllerApi):
        super().__init__()
        self._controller = controller

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
        self._detailed_table = QTableWidget(0, 8)

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
        self._summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._detailed_table.setHorizontalHeaderLabels(TABLE_DETAILED_HEADER)
        self._detailed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._summary_table.setSortingEnabled(True)
        self._detailed_table.setSortingEnabled(True)

        self._run_dropdown.currentIndexChanged.connect(self._on_item_changed)
        self._delete_button.clicked.connect(self._controller.handle_delete_click)
        self._summary_csv_button.clicked.connect(self._controller.handle_summary_export_csv_click)
        self._summary_md_button.clicked.connect(self._controller.handle_summary_export_md_click)
        self._detailed_csv_button.clicked.connect(self._controller.handle_detailed_export_csv_click)
        self._detailed_md_button.clicked.connect(self._controller.handle_detailed_export_md_click)

        self._controller.subscribe_to_runs_change(self._on_runs_changed)
        self._controller.subscribe_to_run_id_changed(self._on_run_id_changed)
        self._controller.subscribe_to_summary_data_change(self._on_summary_data_changed)
        self._controller.subscribe_to_detailed_data_change(self._on_detailed_data_changed)
        self._controller.subscribe_to_benchmark_status_change(self._on_benchmark_is_running_changed)

    def _on_item_changed(self):
        logger.debug("Dropdown item changed")
        current_index = self._run_dropdown.currentIndex()
        if current_index >= 0:
            run_id = self._run_dropdown.itemData(current_index)
            self._controller.handle_run_selection_change(run_id)
            logger.debug(f"Run ID changed to {run_id}")

    def _on_runs_changed(self, run_ids: list[tuple[int, str]]):
        logger.debug(f"Run IDs changed to {run_ids}")
        self._run_dropdown.clear()
        for run_id, name in run_ids:
            self._run_dropdown.addItem(name, run_id)

    def _on_run_id_changed(self, run_id: int):
        logger.debug(f"Run ID changed to {run_id}")

        # Find the index that has the matching run_id as user data
        index = -1
        for i in range(self._run_dropdown.count()):
            if self._run_dropdown.itemData(i) == run_id:
                index = i
                break

        if index >= 0:
            self._run_dropdown.setCurrentIndex(index)
        else:
            logger.warning(f"Run ID {run_id} not found in dropdown")

    def _on_summary_data_changed(self, data: List[AvgSummaryTableItem]):
        logger.debug("Summary data changed")
        self._summary_table.setSortingEnabled(False)
        self._summary_table.setRowCount(len(data))

        for row, item in enumerate(data):
            self._summary_table.setItem(row, 0, QTableWidgetItem(item.model_name))
            self._summary_table.setItem(row, 1, QTableWidgetItem(f"{item.avg_time_ms / 1000:.2f}"))
            self._summary_table.setItem(row, 2, QTableWidgetItem(f"{item.avg_tokens_per_second:.2f}"))
            self._summary_table.setItem(row, 3, QTableWidgetItem(f"{item.avg_score:.2f}"))
        self._summary_table.setSortingEnabled(True)

    def _on_detailed_data_changed(self, data: List[SummaryTableItem]):
        logger.debug("Detailed data changed")
        self._detailed_table.setSortingEnabled(False)
        self._detailed_table.setRowCount(len(data))

        for row, item in enumerate(data):
            name: str = item.model_name
            task_id: str = item.task_id
            task_status = item.task_status
            time: str = str(item.time_ms)
            tokens: str = str(item.tokens)
            tps: str = f"{item.tokens_per_second:.2f}"
            score: str = f"{item.score:.2f}"
            reason: str = item.score_reason
            self._detailed_table.setItem(row, 0, QTableWidgetItem(name))
            self._detailed_table.setItem(row, 1, QTableWidgetItem(task_id))
            self._detailed_table.setItem(row, 2, QTableWidgetItem(task_status))
            self._detailed_table.setItem(row, 3, QTableWidgetItem(time))
            self._detailed_table.setItem(row, 4, QTableWidgetItem(tokens))
            self._detailed_table.setItem(row, 5, QTableWidgetItem(tps))
            self._detailed_table.setItem(row, 6, QTableWidgetItem(score))
            self._detailed_table.setItem(row, 7, QTableWidgetItem(reason))
        self._detailed_table.setSortingEnabled(True)

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        logger.debug("Benchmark item changed")
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
