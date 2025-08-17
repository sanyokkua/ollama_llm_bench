import logging
from typing import Final

from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from ollama_llm_bench.core.interfaces import AppContext, EventBus
from ollama_llm_bench.core.models import ReporterStatusMsg
from ollama_llm_bench.ui.widgets.panels.control.control_tab_widget import ControlTabWidget
from ollama_llm_bench.utils.time_utils import format_elapsed_time_interval

logger = logging.getLogger(__name__)

# Constants for UI messages (avoid magic strings)
_N_A: Final[str] = "N/A"
_TASKS_PROGRESS_FORMAT: Final[str] = "Tasks for stage: [{stage}]. Completed: {completed} / Total: {total}"
_MODEL_STATUS_FORMAT: Final[str] = "Current Model: [{model}]. Loaded Task: {task}"

# Constants for progress bar behavior
_DEFAULT_PROGRESS_MAX: Final[int] = 100  # Standard percentage scale


class ControlPanel(QWidget):
    """
    UI panel displaying benchmark progress and status information during execution.
    Shows progress bar, task completion, current model/task, and elapsed time.
    """

    def __init__(self, ctx: AppContext) -> None:
        """
        Initialize the control panel.

        Args:
            ctx: Application context providing access to event bus and UI components.
        """
        super().__init__()
        # Add explicit type hints for better static analysis
        self._event_bus: EventBus = ctx.get_event_bus()
        self._tab_widget: ControlTabWidget = ControlTabWidget(ctx)
        self._tasks_status: QLabel = QLabel()
        self._progress_bar: QProgressBar = QProgressBar()
        self._status_label: QLabel = QLabel()
        self._time_label: QLabel = QLabel()

        # Configure progress bar with safe defaults
        self._progress_bar.setRange(0, _DEFAULT_PROGRESS_MAX)
        self._progress_bar.setValue(0)

        # Build UI layout
        self._setup_ui_layout()

        # Subscribe to progress events
        self._event_bus.subscribe_to_background_thread_progress(
            self._on_progress_changed,
        )
        logger.debug("ControlPanel initialized with EventBus subscription")

    def _setup_ui_layout(self) -> None:
        """
        Constructs the progress monitoring UI layout.
        Combines control tabs with progress indicators in a vertical arrangement.
        """
        progress_layout = QVBoxLayout()
        progress_layout.addWidget(self._tasks_status)
        progress_layout.addWidget(self._progress_bar)
        progress_layout.addWidget(self._status_label)
        progress_layout.addWidget(self._time_label)
        progress_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.addWidget(self._tab_widget)
        main_layout.addLayout(progress_layout)
        self.setLayout(main_layout)

    def _on_progress_changed(self, status: ReporterStatusMsg) -> None:
        """
        Handle progress updates from ongoing benchmark execution.

        Args:
            status: Current execution status containing progress metrics.
        """
        try:
            # Update components in logical order
            self._update_progress(status.tasks_total, status.tasks_completed)
            self._update_tasks_progress(status.tasks_total, status.tasks_completed, status.current_stage)
            self._update_model_status(status.current_model, status.current_task)
            self._update_time(status.start_time_ms, status.end_time_ms)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to process progress update: {e}", exc_info=True)

    def _update_progress(self, total: int, completed: int) -> None:
        """
        Update the progress bar with current task completion percentage.

        Args:
            total: Total number of tasks to complete.
            completed: Number of tasks already completed.
        """
        if total <= 0:
            # Reset to default percentage scale when no tasks
            self._progress_bar.setRange(0, _DEFAULT_PROGRESS_MAX)
            self._progress_bar.setValue(0)
            return

        # Calculate percentage (0-100) to match progress bar's natural scale
        percentage = min(100, max(0, int((completed / total) * 100)))
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(percentage)

    def _update_tasks_progress(self, total: int, completed: int, stage: str) -> None:
        """
        Update the task progress counter display.

        Args:
            total: Total number of tasks in current stage.
            completed: Number of completed tasks.
            stage: Current execution stage (e.g., benchmarking, judging).
        """
        safe_stage = stage if stage else _N_A
        self._tasks_status.setText(
            _TASKS_PROGRESS_FORMAT.format(
                stage=safe_stage,
                completed=completed,
                total=total,
            ),
        )

    def _update_model_status(self, model: str, task: str) -> None:
        """
        Update the display showing current model and task being processed.

        Args:
            model: Name of currently active model.
            task: ID of currently processing task.
        """
        safe_model = model if model else _N_A
        self._status_label.setText(
            _MODEL_STATUS_FORMAT.format(
                model=safe_model,
                task=task or _N_A,
            ),
        )

    def _update_time(self, start: float, end: float) -> None:
        """
        Update the elapsed time display.

        Args:
            start: Start timestamp in milliseconds.
            end: End timestamp in milliseconds.
        """
        if start < 0 or end < 0:
            logger.warning("Invalid time values received: start=%.2f, end=%.2f", start, end)
            self._time_label.setText("Elapsed Time: --:--")
            return

        try:
            elapsed = format_elapsed_time_interval(start, end)
            self._time_label.setText(f"Elapsed Time: {elapsed}")
        except Exception as e:
            logger.error(f"Time formatting failed: {e}", exc_info=True)
            self._time_label.setText("Elapsed Time: --:--")
