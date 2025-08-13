import logging

from PyQt6.QtWidgets import (QLabel, QProgressBar, QVBoxLayout, QWidget)

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.core.models import ReporterStatusMsg
from ollama_llm_bench.ui.widgets.panels.control.control_tab_widget import ControlTabWidget

logger = logging.getLogger(__name__)


class ControlPanel(QWidget):

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._event_bus = ctx.get_event_bus()

        self._tab_widget = ControlTabWidget(ctx)
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

        self._event_bus.subscribe_to_benchmark_progress_events(self._on_progress_changed)

    def _on_progress_changed(self, status: ReporterStatusMsg):
        self._update_progress(status.total_amount_of_tasks, status.completed_amount_of_tasks)
        self._update_tasks_status(status.total_amount_of_tasks, status.completed_amount_of_tasks)
        self._update_status(f"Running task: {status.current_task_id}")

    def _update_progress(self, total_amount: int, completed_amount: int) -> None:
        self._progress_bar.setMaximum(total_amount)
        self._progress_bar.setValue(completed_amount)

    def _update_tasks_status(self, total_amount: int, completed_amount: int) -> None:
        self._tasks_status.setText(f"Tasks: {completed_amount}/{total_amount}")

    def _update_status(self, status: str) -> None:
        self._status_label.setText(status)
