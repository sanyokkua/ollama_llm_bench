import logging

from PyQt6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget)

from ollama_llm_bench.core.controllers import PreviousRunWidgetControllerApi

logger = logging.getLogger(__name__)


class PreviousRunWidget(QWidget):
    def __init__(self, controller: PreviousRunWidgetControllerApi) -> None:
        super().__init__()
        self._controller = controller

        self._refresh_button_new = QPushButton("Refresh Runs")
        self._start_button_prev = QPushButton("Continue Benchmark")
        self._stop_button_prev = QPushButton("Stop Benchmark")
        self._unfinished_dropdown_prev = QComboBox()

        unfinished_group = QGroupBox("Unfinished Benchmarks")
        unfinished_layout = QVBoxLayout()
        unfinished_layout.addWidget(self._unfinished_dropdown_prev)
        unfinished_group.setLayout(unfinished_layout)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self._refresh_button_new)
        button_layout.addWidget(self._start_button_prev)
        button_layout.addWidget(self._stop_button_prev)

        layout = QVBoxLayout()
        layout.addWidget(unfinished_group)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self._start_button_prev.clicked.connect(self._controller.handle_start_click)
        self._refresh_button_new.clicked.connect(self._controller.handle_refresh_click)
        self._stop_button_prev.clicked.connect(self._controller.handle_stop_click)
        self._unfinished_dropdown_prev.currentIndexChanged.connect(self._on_item_changed)
        self._controller.subscribe_to_runs_change(self._on_runs_changed)
        self._controller.subscribe_to_benchmark_status_change(self._on_benchmark_is_running_changed)

    def _on_item_changed(self):
        logger.debug("Dropdown item changed")
        current_index = self._unfinished_dropdown_prev.currentIndex()
        if current_index >= 0:
            run_id = self._unfinished_dropdown_prev.itemData(current_index)
            self._controller.handle_item_change(run_id)
            logger.debug(f"Run ID changed to {run_id}")

    def _on_runs_changed(self, runs: list[tuple[int, str]]):
        self._unfinished_dropdown_prev.clear()
        for run_id, name in runs:
            self._unfinished_dropdown_prev.addItem(name, run_id)

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        self._unfinished_dropdown_prev.setEnabled(not is_running)
        self._refresh_button_new.setEnabled(not is_running)
        self._start_button_prev.setEnabled(not is_running)
        self._stop_button_prev.setEnabled(is_running)
