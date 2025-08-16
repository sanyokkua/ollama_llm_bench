import logging

from PyQt6.QtWidgets import (QLabel, QProgressBar, QVBoxLayout, QWidget)

from ollama_llm_bench.core.interfaces import AppContext
from ollama_llm_bench.core.models import ReporterStatusMsg
from ollama_llm_bench.ui.widgets.panels.control.control_tab_widget import ControlTabWidget
from ollama_llm_bench.utils.time_utils import format_elapsed_time_interval

logger = logging.getLogger(__name__)


class ControlPanel(QWidget):

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._event_bus = ctx.get_event_bus()

        self._tab_widget = ControlTabWidget(ctx)
        self._tasks_status = QLabel()
        self._progress_bar = QProgressBar()
        self._status_label = QLabel()
        self._time_label = QLabel()

        progress_layout = QVBoxLayout()
        progress_layout.addWidget(self._tasks_status)
        progress_layout.addWidget(self._progress_bar)
        progress_layout.addWidget(self._status_label)
        progress_layout.addWidget(self._time_label)
        progress_layout.addStretch()
        self._progress_bar.setRange(0, 100)

        layout = QVBoxLayout()
        layout.addWidget(self._tab_widget)
        layout.addLayout(progress_layout)
        self.setLayout(layout)

        self._event_bus.subscribe_to_background_thread_progress(self._on_progress_changed)

    def _on_progress_changed(self, status: ReporterStatusMsg):
        self._update_progress(status.tasks_total, status.tasks_completed)
        self._update_tasks_status(status.tasks_total, status.tasks_completed, status.current_stage)
        self._update_status(f"Current Model: [{status.current_model or "N/A"}]. Loaded Task: {status.current_task}")
        self._update_time(status.start_time_ms, status.end_time_ms)

    def _update_progress(self, total_amount: int, completed_amount: int) -> None:
        max = 100 if total_amount == 0 else total_amount
        self._progress_bar.setMaximum(max)
        self._progress_bar.setValue(completed_amount)

    def _update_tasks_status(self, total_amount: int, completed_amount: int, stage: str) -> None:
        self._tasks_status.setText(f"Tasks for stage: [{stage or "N/A"}]. Completed [{completed_amount}] /Total [{total_amount}] ")

    def _update_status(self, status: str) -> None:
        self._status_label.setText(status)

    def _update_time(self, start: float, end: float) -> None:
        self._time_label.setText(format_elapsed_time_interval(start, end))
