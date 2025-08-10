from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget)


@dataclass(frozen=True)
class PreviousRunWidgetModel:
    runs: list[tuple[int, str]]


class PreviousRunWidget(QWidget):
    btn_refresh_clicked = pyqtSignal()
    btn_stop_clicked = pyqtSignal()
    btn_start_clicked = pyqtSignal(int)
    dropdown_run_changed = pyqtSignal(int)

    def __init__(self, model: PreviousRunWidgetModel) -> None:
        """Initialize the control panel."""
        super().__init__()

        self._refresh_button_new = QPushButton("Refresh Runs")
        self._start_button_prev = QPushButton("Continue Benchmark")
        self._stop_button_prev = QPushButton("Stop Benchmark")
        self._unfinished_dropdown_prev = QComboBox()

        unfinished_group = QGroupBox("Unfinished Benchmarks")
        unfinished_layout = QVBoxLayout()
        unfinished_layout.addWidget(self._unfinished_dropdown_prev)
        unfinished_group.setLayout(unfinished_layout)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self._start_button_prev)
        button_layout.addWidget(self._stop_button_prev)

        layout = QVBoxLayout()
        layout.addWidget(unfinished_group)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self._refresh_button_new.clicked.connect(self._on_refresh_clicked)
        self._start_button_prev.clicked.connect(self._on_start_clicked)
        self._stop_button_prev.clicked.connect(self._on_stop_clicked)

        self.refresh_widgets_data(model)
        self.set_benchmark_is_running(False)

    def _on_refresh_clicked(self) -> None:
        self.btn_refresh_clicked.emit()
        print("Refresh Runs button clicked")

    def _on_start_clicked(self) -> None:
        index = self._unfinished_dropdown_prev.currentIndex()
        data = self._unfinished_dropdown_prev.itemData(index)
        self.btn_start_clicked.emit(data)
        print("Start Benchmark button clicked")

    def _on_stop_clicked(self) -> None:
        self.btn_stop_clicked.emit()
        print("Stop Benchmark button clicked")

    def _on_item_changed(self):
        current_index = self._unfinished_dropdown_prev.currentIndex()
        if current_index >= 0:
            run_id = self._unfinished_dropdown_prev.itemData(current_index)
            self.dropdown_run_changed.emit(run_id)

    def refresh_widgets_data(self, model: PreviousRunWidgetModel) -> None:
        if model is None:
            print("Model is None")
            return
        self._unfinished_dropdown_prev.clear()
        for item in model.runs:
            self._unfinished_dropdown_prev.addItem(item[1], item[0])

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._unfinished_dropdown_prev.setEnabled(not is_running)
        self._refresh_button_new.setEnabled(not is_running)
        self._start_button_prev.setEnabled(not is_running)
        self._stop_button_prev.setEnabled(is_running)
