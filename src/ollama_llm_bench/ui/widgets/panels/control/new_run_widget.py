import logging

from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QListWidget, QPushButton, QVBoxLayout, QWidget

from ollama_llm_bench.core.controllers import NewRunWidgetControllerApi
from ollama_llm_bench.core.models import NewRunWidgetStartEvent

logger = logging.getLogger(__name__)


class NewRunWidget(QWidget):
    def __init__(self, controller: NewRunWidgetControllerApi) -> None:
        super().__init__()
        self._controller = controller

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

        self._start_button_new.clicked.connect(self._on_start_clicked)
        self._refresh_button_new.clicked.connect(self._controller.handle_refresh_click)
        self._stop_button_new.clicked.connect(self._controller.handle_stop_click)
        self._controller.subscribe_to_models_change(self._on_models_changed)
        self._controller.subscribe_to_benchmark_status_change(self._on_benchmark_is_running_changed)

    def _on_start_clicked(self) -> None:
        logger.debug("Start Benchmark button clicked")
        items = self._models_list.selectedItems()
        models = { item.text() for item in items }
        models_tuple = tuple(models)
        event = NewRunWidgetStartEvent(
            judge_model=self._judge_dropdown_new.currentText(),
            models=models_tuple,
        )
        self._controller.handle_start_click(event)

    def _on_models_changed(self, value: list[str]):
        logger.debug(f"Models changed: {value}")
        self._judge_dropdown_new.clear()
        self._judge_dropdown_new.addItems(value)
        self._models_list.clear()
        self._models_list.addItems(value)

    def _on_benchmark_is_running_changed(self, is_running: bool) -> None:
        logger.debug(f"Benchmark is running: {is_running}")
        self._start_button_new.setEnabled(not is_running)
        self._judge_dropdown_new.setEnabled(not is_running)
        self._refresh_button_new.setEnabled(not is_running)
        self._models_list.setEnabled(not is_running)
        self._stop_button_new.setEnabled(is_running)
