from dataclasses import dataclass

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget)

from ollama_llm_bench.ui.widgets.panels.control.control_tab_widget import ControlTabWidget
from ollama_llm_bench.ui.widgets.panels.control.new_run_widget import NewRunWidgetModel, NewRunWidgetStartEvent
from ollama_llm_bench.ui.widgets.panels.control.previous_run_widget import PreviousRunWidgetModel


@dataclass(frozen=True)
class ControlPanelModel:
    judge_models: list[str]
    models: list[str]
    runs: list[tuple[int, str]]
    progress: int = 0
    status: str = 'Idle. Ready for new benchmark.'


class ControlPanel(QWidget):
    btn_new_run_stop_clicked = pyqtSignal()
    btn_new_run_start_clicked = pyqtSignal(NewRunWidgetStartEvent)
    btn_new_run_refresh_clicked = pyqtSignal()
    btn_prev_run_refresh_clicked = pyqtSignal()
    btn_prev_run_stop_clicked = pyqtSignal()
    btn_prev_run_start_clicked = pyqtSignal(int)
    dropdown_run_changed = pyqtSignal(int)

    def __init__(self, model: ControlPanelModel) -> None:
        super().__init__()

        new_run_model: NewRunWidgetModel = NewRunWidgetModel([], [])
        prev_run_model: PreviousRunWidgetModel = PreviousRunWidgetModel([])

        self._tab_widget = ControlTabWidget(new_run_model=new_run_model, prev_run_model=prev_run_model)
        self._tasks_status = QLabel()
        self._progress_bar = QProgressBar()
        self._status_label = QLabel()

        progress_layout = QVBoxLayout()
        progress_layout.addWidget(self._tasks_status)
        progress_layout.addWidget(self._progress_bar)
        progress_layout.addWidget(self._status_label)
        progress_layout.addStretch()
        self._progress_bar.setRange(0, 100)

        layout = QVBoxLayout()
        layout.addWidget(self._tab_widget)
        layout.addLayout(progress_layout)
        self.setLayout(layout)

        self._tab_widget.btn_new_run_stop_clicked.connect(self.btn_new_run_stop_clicked)
        self._tab_widget.btn_new_run_start_clicked.connect(self.btn_new_run_start_clicked)
        self._tab_widget.btn_new_run_refresh_clicked.connect(self.btn_new_run_refresh_clicked)
        self._tab_widget.btn_prev_run_refresh_clicked.connect(self.btn_prev_run_refresh_clicked)
        self._tab_widget.btn_prev_run_stop_clicked.connect(self.btn_prev_run_stop_clicked)
        self._tab_widget.btn_prev_run_start_clicked.connect(self.btn_prev_run_start_clicked)
        self._tab_widget.dropdown_run_changed.connect(lambda run_id: self.dropdown_run_changed.emit(run_id))
        self.update_state(model)

    def update_state(self, model: ControlPanelModel) -> None:
        new_run_model: NewRunWidgetModel = NewRunWidgetModel(model.models, model.models)
        prev_run_model: PreviousRunWidgetModel = PreviousRunWidgetModel(model.runs)
        self._tab_widget.refresh_widgets_data_for_new_run(new_run_model)
        self._tab_widget.refresh_widgets_data_for_prev_run(prev_run_model)

    def set_benchmark_is_running(self, is_running: bool) -> None:
        self._tab_widget.set_benchmark_is_running(is_running)

    def update_progress(self, total_amount: int, completed_amount: int) -> None:
        self._progress_bar.setMaximum(total_amount)
        self._progress_bar.setValue(completed_amount)

    def update_tasks_status(self, total_amount: int, completed_amount: int) -> None:
        self._status_label.setText(f"Tasks: {completed_amount}/{total_amount}")

    def update_status(self, status: str) -> None:
        self._status_label.setText(status)
