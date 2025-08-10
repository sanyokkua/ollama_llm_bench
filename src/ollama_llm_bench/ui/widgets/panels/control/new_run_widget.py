from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QWidget


@dataclass(frozen=True)
class NewRunWidgetModel:
    judge_models: list[str]
    models: list[str]


@dataclass(frozen=True)
class NewRunWidgetStartEvent:
    judge_model: str
    models: tuple[str, ...]


class NewRunWidget(QWidget):
    btn_stop_clicked = pyqtSignal()
    btn_start_clicked = pyqtSignal(NewRunWidgetStartEvent)
    btn_refresh_clicked = pyqtSignal()

    def __init__(self, model: NewRunWidgetModel) -> None:
        """Create the 'Run New Benchmark' tab."""
        super().__init__()
        self._judge_dropdown_new = QComboBox()
        self._models_list = QListWidget()
        self._refresh_button_new = QPushButton("Refresh Models")
        self._start_button_new = QPushButton("Start Benchmark")
        self._stop_button_new = QPushButton("Stop Benchmark")

        judge_group = QGroupBox("Judge Model")
        judge_layout = QVBoxLayout()
        judge_layout.addWidget(self._judge_dropdown_new)
        judge_group.setLayout(judge_layout)

        models_group = QGroupBox("Models to Benchmark")
        models_layout = QVBoxLayout()
        models_layout.addWidget(self._models_list)
        models_group.setLayout(models_layout)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self._refresh_button_new)
        button_layout.addWidget(self._start_button_new)
        button_layout.addWidget(self._stop_button_new)

        layout = QVBoxLayout()
        layout.addWidget(judge_group)
        layout.addWidget(models_group)
        layout.addLayout(button_layout)
        self.setLayout(layout)

        self._models_list.setSelectionMode(self._models_list.SelectionMode.MultiSelection)

        self._refresh_button_new.clicked.connect(self._on_refresh_clicked)
        self._start_button_new.clicked.connect(self._on_start_clicked)
        self._stop_button_new.clicked.connect(self._on_stop_clicked)

        self.refresh_widgets_data(model)
        self.set_benchmark_is_running(False)

    def _on_refresh_clicked(self) -> None:
        self.btn_refresh_clicked.emit()
        print("Refresh Models button clicked")

    def _on_start_clicked(self) -> None:
        items = self._models_list.selectedItems()
        models = [item.text() for item in items]
        models_tuple = tuple(models)
        event = NewRunWidgetStartEvent(
            judge_model=self._judge_dropdown_new.currentText(),
            models=models_tuple,
        )
        self.btn_start_clicked.emit(event)
        print("Start Benchmark button clicked")

    def _on_stop_clicked(self) -> None:
        self.btn_stop_clicked.emit()
        print("Stop Benchmark button clicked")

    def refresh_widgets_data(self, model: NewRunWidgetModel) -> None:
        if model is None:
            print("Model is None")
            return
        self._judge_dropdown_new.clear()
        self._judge_dropdown_new.addItems(model.judge_models)
        self._models_list.clear()
        self._models_list.addItems(model.models)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._start_button_new.setEnabled(not is_running)
        self._judge_dropdown_new.setEnabled(not is_running)
        self._models_list.setEnabled(not is_running)
        self._stop_button_new.setEnabled(is_running)
