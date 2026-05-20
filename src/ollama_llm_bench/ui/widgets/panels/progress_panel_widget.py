"""Structured progress panel widget for V2 benchmark execution monitoring."""

import logging
import time
from datetime import datetime
from typing import Final

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.constants import RUN_MODE_LABELS, STAGE_SEQUENCE_BY_MODE
from ollama_llm_bench.backend.core.interfaces import AppSettingsServiceApi, BenchmarkFlowApi, EventBus
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkPausedEvent,
    BenchmarkResultStatus,
    BenchmarkResumedEvent,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    JudgeEvalRetryEvent,
    JudgeEvalStartedEvent,
    PipelineStage,
    ProgressUpdateEvent,
    RunMode,
    RunRenamedEvent,
    TaskRetryEvent,
    TaskSwitchEvent,
)
from ollama_llm_bench.backend.core.ui_controllers import RunConfigControllerApi
from ollama_llm_bench.backend.utils.format import format_attempt_durations, format_progress_label
from ollama_llm_bench.backend.utils.time_utils import format_compact_duration
from ollama_llm_bench.ui.style.style_utils import repolish
from ollama_llm_bench.ui.style.tokens import SHARED_TOKENS

logger = logging.getLogger(__name__)

_PROGRESS_BAR_MAX: Final[int] = 100
_ETA_FINISHED: Final[str] = "Finished"
_STOPPED_LABEL: Final[str] = "Stopped"
_DASH: Final[str] = "\u2013"
_LIVE_TIMER_INTERVAL_MS: Final[int] = 1000

_STATUS_TOOLTIPS: Final[dict[str, str]] = {
    BenchmarkResultStatus.NOT_COMPLETED: "Not Completed: tasks that have not yet been benchmarked.",
    BenchmarkResultStatus.WAITING_FOR_JUDGE: "Waiting for Judgement: tasks whose inference is done but evaluation has not yet run.",
    BenchmarkResultStatus.COMPLETED: "Completed: tasks fully processed (inference + any required evaluation).",
    BenchmarkResultStatus.FAILED: "Failed: tasks where inference or evaluation raised an unrecoverable error. Look in the log.",
}

_MODES_WITH_JUDGING: Final[frozenset[RunMode]] = frozenset({RunMode.FULL_GRADING, RunMode.PROMPT_EVAL})


class ProgressPanelWidget(QWidget):
    """Structured progress panel displaying V2 benchmark execution metrics."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        benchmark_flow_api: BenchmarkFlowApi,
        app_settings: AppSettingsServiceApi,
        run_config_controller: RunConfigControllerApi,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the progress panel widget.

        Args:
            event_bus: Application event bus for subscribing to progress events.
            benchmark_flow_api: API for controlling benchmark execution lifecycle.
            app_settings: Application settings service for user preferences.
            run_config_controller: Controller for run management including rename operations.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._flow_api = benchmark_flow_api
        self._app_settings = app_settings
        self._run_config_controller = run_config_controller

        # Runtime state
        self._bench_start_ms: float = 0.0
        self._task_start_ms_cached: float = 0.0
        self._is_paused: bool = False
        self._current_run_mode: RunMode | None = None
        self._run_name_full: str = ""
        self._current_run_id: int | None = None

        # Phase 1 — create child widgets
        self._run_name_label: QLabel = QLabel("")
        self._rename_btn: QToolButton = QToolButton()
        self._stage_badge: QLabel = QLabel(_DASH)
        self._pause_btn: QPushButton = QPushButton("Pause")
        self._stop_btn: QPushButton = QPushButton("Stop")
        self._progress_bar: QProgressBar = QProgressBar()
        self._progress_label: QLabel = QLabel("0 / 0 (0%)")
        self._eta_label: QLabel = QLabel(_DASH)
        self._elapsed_label: QLabel = QLabel("0s")
        # Category counters
        self._count_not_completed: QLabel = QLabel(_DASH)
        self._count_waiting: QLabel = QLabel(_DASH)
        self._count_completed: QLabel = QLabel(_DASH)
        self._count_failed: QLabel = QLabel(_DASH)
        self._count_waiting_label_widget: QLabel = QLabel("Waiting:")
        # Model group
        self._provider_label: QLabel = QLabel(_DASH)
        self._model_label: QLabel = QLabel(_DASH)
        # Task group
        self._task_label: QLabel = QLabel(_DASH)
        self._task_elapsed_label: QLabel = QLabel(_DASH)
        self._timeout_label: QLabel = QLabel(_DASH)
        self._retry_label: QLabel = QLabel("")
        self._retry_reason_label: QLabel = QLabel("")
        self._retry_durations_label: QLabel = QLabel("")

        self._live_timer: QTimer = QTimer()

        # Phase 2 — configure
        self._progress_bar.setRange(0, _PROGRESS_BAR_MAX)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._live_timer.setInterval(_LIVE_TIMER_INTERVAL_MS)
        self._live_timer.timeout.connect(self._on_timer_tick)
        self._task_label.setWordWrap(True)

        self._run_name_label.setProperty("role", "heading")
        self._run_name_label.setVisible(False)
        self._run_name_label.setWordWrap(False)

        self._rename_btn.setText("✏")
        self._rename_btn.setToolTip("Rename this run")
        self._rename_btn.setProperty("role", "icon-btn")
        self._rename_btn.setVisible(False)

        self._pause_btn.setProperty("role", "secondary")
        self._pause_btn.setEnabled(False)
        self._stop_btn.setProperty("role", "danger")
        self._stop_btn.setEnabled(False)

        self._retry_label.setProperty("role", "warning-text")
        self._retry_label.setVisible(False)
        self._retry_reason_label.setProperty("role", "warning-text")
        self._retry_reason_label.setVisible(False)
        self._retry_durations_label.setVisible(False)

        mono_font = SHARED_TOKENS.get("font_mono", "monospace")
        for lbl in (self._count_not_completed, self._count_waiting, self._count_completed, self._count_failed):
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(f"font-family: {mono_font};")

        self._count_not_completed.setToolTip(_STATUS_TOOLTIPS[BenchmarkResultStatus.NOT_COMPLETED])
        self._count_waiting.setToolTip(_STATUS_TOOLTIPS[BenchmarkResultStatus.WAITING_FOR_JUDGE])
        self._count_completed.setToolTip(_STATUS_TOOLTIPS[BenchmarkResultStatus.COMPLETED])
        self._count_failed.setToolTip(_STATUS_TOOLTIPS[BenchmarkResultStatus.FAILED])

        self._stage_badge.setToolTip("No active run. Status is shown when a benchmark starts.")

        # Phase 3 — layout
        self._build_layout()

        # Phase 4 — signals
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._rename_btn.clicked.connect(self._on_rename_clicked)
        pause_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        pause_shortcut.activated.connect(self._on_pause_clicked)
        stop_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        stop_shortcut.activated.connect(self._on_stop_clicked)

        # Phase 5 — EventBus subscriptions
        event_bus.subscribe_to_benchmark_started(self._on_benchmark_started, parent=self)
        event_bus.subscribe_to_run_renamed(self._on_run_renamed, parent=self)
        event_bus.subscribe_to_benchmark_paused(self._on_benchmark_paused, parent=self)
        event_bus.subscribe_to_benchmark_resumed(self._on_benchmark_resumed, parent=self)
        event_bus.subscribe_to_task_switch(self._on_task_switch, parent=self)
        event_bus.subscribe_to_task_retry(self._on_task_retry, parent=self)
        event_bus.subscribe_to_progress_update(self._on_progress_update, parent=self)
        event_bus.subscribe_to_benchmark_finished(self._on_benchmark_finished, parent=self)
        event_bus.subscribe_to_benchmark_stopped(self._on_benchmark_stopped, parent=self)
        event_bus.subscribe_to_judge_eval_started(self._on_judge_eval_started, parent=self)
        event_bus.subscribe_to_judge_eval_retry(self._on_judge_eval_retry, parent=self)

        logger.debug("ProgressPanelWidget initialized")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        """Compose all child widgets into the panel layout."""
        # Status row: stage badge (left) + stretch + pause/stop buttons (right)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.addWidget(self._stage_badge)
        status_row.addWidget(self._progress_bar, 1)
        status_row.addWidget(self._pause_btn)
        status_row.addWidget(self._stop_btn)

        # Run Progress group
        run_group = QGroupBox("Run Progress")
        run_form = QFormLayout()
        run_form.setSpacing(6)
        run_form.setContentsMargins(8, 8, 8, 8)
        run_form.addRow("Tasks:", self._progress_label)
        run_form.addRow("ETA:", self._eta_label)
        run_form.addRow("Total Time:", self._elapsed_label)
        run_form.addRow("Not Completed:", self._count_not_completed)
        run_form.addRow(self._count_waiting_label_widget, self._count_waiting)
        run_form.addRow("Completed:", self._count_completed)
        run_form.addRow("Failed:", self._count_failed)
        run_group.setLayout(run_form)

        # Model group
        model_group = QGroupBox("Model")
        model_form = QFormLayout()
        model_form.setSpacing(6)
        model_form.setContentsMargins(8, 8, 8, 8)
        model_form.addRow("Provider:", self._provider_label)
        model_form.addRow("Model:", self._model_label)
        model_group.setLayout(model_form)

        # Current Task group
        task_group = QGroupBox("Current Task")
        task_form = QFormLayout()
        task_form.setSpacing(4)
        task_form.addRow("Task:", self._task_label)
        task_form.addRow("Task Time:", self._task_elapsed_label)
        task_form.addRow("Timeouts:", self._timeout_label)
        task_layout = QVBoxLayout()
        task_layout.setSpacing(4)
        task_layout.setContentsMargins(8, 8, 8, 8)
        task_layout.addLayout(task_form)
        task_layout.addWidget(self._retry_label)
        task_layout.addWidget(self._retry_reason_label)
        task_layout.addWidget(self._retry_durations_label)
        task_group.setLayout(task_layout)

        # Middle row: Run Progress + Model side-by-side
        middle_row = QHBoxLayout()
        middle_row.setSpacing(8)
        middle_row.addWidget(run_group, 1)
        middle_row.addWidget(model_group, 1)

        run_name_row = QHBoxLayout()
        run_name_row.setSpacing(4)
        run_name_row.addWidget(self._run_name_label, 1)
        run_name_row.addWidget(self._rename_btn)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addLayout(run_name_row)
        layout.addLayout(status_row)
        layout.addLayout(middle_row)
        layout.addWidget(task_group)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Resize: elide run name
    # ------------------------------------------------------------------

    def resizeEvent(self, event: object) -> None:
        """Handle resize to elide the run name label."""
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._update_run_name_elided()

    def _update_run_name_elided(self) -> None:
        """Elide run name label text to fit the available width."""
        if not self._run_name_full:
            return
        fm = QFontMetrics(self._run_name_label.font())
        available = self._run_name_label.width() - 4
        elided = fm.elidedText(self._run_name_full, Qt.TextElideMode.ElideRight, max(available, 20))
        self._run_name_label.setText(elided)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_pause_clicked(self) -> None:
        """Handle pause/resume button click or Space shortcut."""
        if not self._pause_btn.isEnabled():
            return
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        if self._is_paused:
            self._flow_api.resume_execution()
        else:
            self._flow_api.pause_execution()

    def _on_stop_clicked(self) -> None:
        """Handle stop button click or Escape shortcut with confirmation dialog."""
        if not self._stop_btn.isEnabled():
            return
        reply = QMessageBox.question(
            self,
            "Stop benchmark",
            "Stop the current run? Partial results will be saved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._pause_btn.setEnabled(False)
            self._stop_btn.setEnabled(False)
            self._flow_api.stop_execution()

    def _on_rename_clicked(self) -> None:
        """Open the rename dialog and persist the new name if accepted."""
        if self._current_run_id is None:
            return
        from ollama_llm_bench.ui.widgets.panels.rename_run_dialog import RenameRunDialog

        existing = self._run_config_controller.get_run_names(exclude_run_id=self._current_run_id)
        dlg = RenameRunDialog(
            current_name=self._run_name_full,
            existing_names=existing,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_config_controller.rename_run(run_id=self._current_run_id, new_name=dlg.new_name)

    def _on_run_renamed(self, event: RunRenamedEvent) -> None:
        """Update the run name label when the current run is renamed.

        Args:
            event: RunRenamedEvent containing the run_id and new_name.
        """
        if event.run_id != self._current_run_id:
            return
        self._run_name_full = event.new_name
        self._run_name_label.setToolTip(event.new_name)
        self._update_run_name_elided()

    # ------------------------------------------------------------------
    # EventBus handlers — lifecycle
    # ------------------------------------------------------------------

    def _on_benchmark_started(self, event: BenchmarkStartedEvent) -> None:
        """Record benchmark start time and configure UI for the active run.

        Args:
            event: Benchmark started event with run metadata.
        """
        self._bench_start_ms = time.monotonic() * 1000.0
        self._task_start_ms_cached = 0.0
        self._current_run_mode = event.run_mode
        self._current_run_id = event.run_id
        self._is_paused = False
        self._pause_btn.setEnabled(True)
        self._pause_btn.setText("Pause")
        self._pause_btn.setProperty("role", "secondary")
        repolish(self._pause_btn)
        self._stop_btn.setEnabled(True)
        self._rename_btn.setVisible(True)
        # Run name
        name = (
            event.run_name if event.run_name else f"Run #{event.run_id} · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        self._run_name_full = name
        self._run_name_label.setToolTip(name)
        self._run_name_label.setVisible(True)
        self._update_run_name_elided()
        # Mode-dependent visibility for Waiting counter
        show_waiting = event.run_mode in _MODES_WITH_JUDGING
        self._count_waiting_label_widget.setVisible(show_waiting)
        self._count_waiting.setVisible(show_waiting)
        # Reset counters
        for lbl in (self._count_not_completed, self._count_waiting, self._count_completed, self._count_failed):
            lbl.setText("0")
        self._live_timer.start()
        self._refresh_stage_badge_tooltip()

    def _on_benchmark_paused(self, event: BenchmarkPausedEvent) -> None:
        """Freeze live timer and update pause button state.

        Args:
            event: Benchmark paused event.
        """
        self._is_paused = True
        self._live_timer.stop()
        self._pause_btn.setText("Resume")
        self._pause_btn.setProperty("role", "warning")
        repolish(self._pause_btn)
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)

    def _on_benchmark_resumed(self, event: BenchmarkResumedEvent) -> None:
        """Restart live timer and restore pause button state.

        Args:
            event: Benchmark resumed event.
        """
        self._is_paused = False
        self._live_timer.start()
        self._pause_btn.setText("Pause")
        self._pause_btn.setProperty("role", "secondary")
        repolish(self._pause_btn)
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)

    def _on_benchmark_finished(self, event: BenchmarkFinishedEvent) -> None:
        """Handle benchmark finished event.

        Args:
            event: Benchmark finished event.
        """
        self._live_timer.stop()
        self._eta_label.setText(_ETA_FINISHED)
        self._update_stage_badge(PipelineStage.FINISHED)
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

    def _on_benchmark_stopped(self, event: BenchmarkStoppedEvent) -> None:
        """Handle benchmark stopped event.

        Args:
            event: Benchmark stopped event.
        """
        self._live_timer.stop()
        self._stage_badge.setText(_STOPPED_LABEL)
        self._stage_badge.setProperty("pipeline_stage", None)
        repolish(self._stage_badge)
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

    def _on_task_switch(self, event: TaskSwitchEvent) -> None:
        """Update task label and reset per-task timer when a new task begins inference.

        Args:
            event: Task switch event with model and task metadata.
        """
        self._task_label.setText(event.task_id)
        self._task_label.setToolTip(event.task_id)
        self._provider_label.setText(event.model.provider_id or _DASH)
        self._model_label.setText(event.model.model_name or _DASH)
        self._model_label.setToolTip(event.model.display_label)
        self._task_elapsed_label.setText("0s")
        self._task_start_ms_cached = time.monotonic() * 1000.0
        self._retry_label.setVisible(False)
        self._retry_reason_label.setVisible(False)
        self._retry_durations_label.setVisible(False)

    def _on_task_retry(self, event: TaskRetryEvent) -> None:
        """Show retry counter and reset per-attempt timer when a retry starts.

        Args:
            event: Task retry event with attempt counts and durations.
        """
        self._retry_label.setText(f"Retry {event.attempt}/{event.total_attempts}")
        self._retry_label.setVisible(True)
        reason = event.retry_reason or _DASH
        self._retry_reason_label.setText(f"Reason: {reason}")
        self._retry_reason_label.setVisible(True)
        if event.attempt_durations_ms:
            self._retry_durations_label.setText(format_attempt_durations(event.attempt_durations_ms))
            self._retry_durations_label.setVisible(True)
        self._task_elapsed_label.setText("0s")
        self._task_start_ms_cached = time.monotonic() * 1000.0

    def _on_judge_eval_started(self, event: JudgeEvalStartedEvent) -> None:
        """Reset per-task timer and update labels when a new judge evaluation begins.

        Args:
            event: Judge eval started event with judge model metadata.
        """
        self._task_label.setText(event.task_id)
        self._task_label.setToolTip(event.task_id)
        self._provider_label.setText(event.judge_provider_id or _DASH)
        self._model_label.setText(event.judge_model or _DASH)
        self._model_label.setToolTip(event.judge_model)
        self._task_elapsed_label.setText("0s")
        self._task_start_ms_cached = time.monotonic() * 1000.0
        self._retry_label.setVisible(False)
        self._retry_reason_label.setVisible(False)
        self._retry_durations_label.setVisible(False)

    def _on_judge_eval_retry(self, event: JudgeEvalRetryEvent) -> None:
        """Show retry counter and reset per-attempt timer when a judge retry starts.

        Args:
            event: Judge eval retry event with attempt counts.
        """
        self._retry_label.setText(f"Retry {event.attempt}/{event.total_attempts}")
        self._retry_label.setVisible(True)
        self._task_elapsed_label.setText("0s")
        self._task_start_ms_cached = time.monotonic() * 1000.0

    # ------------------------------------------------------------------
    # EventBus handlers — progress
    # ------------------------------------------------------------------

    def _on_progress_update(self, event: ProgressUpdateEvent) -> None:
        """Handle a progress update event from the benchmark pipeline.

        Args:
            event: Typed progress event containing stage, completion counts, and timing.
        """
        try:
            self._bench_start_ms = event.start_time_ms
            self._task_start_ms_cached = event.task_start_ms
            self._update_stage_badge(event.stage)
            self._update_progress_bar(event.tasks_completed, event.tasks_total)
            self._update_progress_label(event.tasks_completed, event.tasks_total)
            self._update_eta_label(event.estimated_remaining_ms)
            self._update_elapsed_label(event.start_time_ms, event.current_time_ms)
            self._update_task_elapsed_label(event.task_start_ms, event.current_time_ms)
            self._update_context_labels(event.current_provider, event.current_model, event.current_task)
            self._update_status_counts(event.counts_by_status)
        except (ValueError, TypeError) as exc:
            logger.exception("Failed to process progress update: %s", exc)

    # ------------------------------------------------------------------
    # Live timer tick
    # ------------------------------------------------------------------

    def _on_timer_tick(self) -> None:
        """Update elapsed and task-time labels every second between task completion events."""
        if self._bench_start_ms <= 0:
            return
        now_ms = time.monotonic() * 1000.0
        elapsed_ms = max(0.0, now_ms - self._bench_start_ms)
        self._elapsed_label.setText(format_compact_duration(elapsed_ms))
        if self._task_start_ms_cached > 0:
            task_ms = max(0.0, now_ms - self._task_start_ms_cached)
            self._task_elapsed_label.setText(format_compact_duration(task_ms))

    # ------------------------------------------------------------------
    # Label/badge helpers
    # ------------------------------------------------------------------

    def _update_stage_badge(self, stage: PipelineStage) -> None:
        """Update the stage badge using QSS pipeline_stage property.

        Args:
            stage: Current pipeline stage.
        """
        self._stage_badge.setText(stage.value)
        self._stage_badge.setProperty("pipeline_stage", stage.name)
        repolish(self._stage_badge)
        self._refresh_stage_badge_tooltip()

    def _refresh_stage_badge_tooltip(self) -> None:
        """Rebuild the stage badge tooltip showing the stage sequence for the current run mode."""
        if self._current_run_mode is None:
            self._stage_badge.setToolTip("No active run. Status is shown when a benchmark starts.")
            return
        mode_label = RUN_MODE_LABELS.get(self._current_run_mode, self._current_run_mode.value)
        sequence = STAGE_SEQUENCE_BY_MODE.get(self._current_run_mode, ())
        current_text = self._stage_badge.text()
        lines = [f"Stages for {mode_label}:"]
        for stage in sequence:
            if stage.value == current_text:
                lines.append(f"  ▶ {stage.value}")
            else:
                lines.append(f"    {stage.value}")
        lines.append("")
        lines.append("Terminal stages: Failed, Stopped")
        self._stage_badge.setToolTip("\n".join(lines))

    def _update_progress_bar(self, completed: int, total: int) -> None:
        """Update the progress bar value.

        Args:
            completed: Number of completed tasks.
            total: Total number of tasks.
        """
        if total <= 0:
            self._progress_bar.setValue(0)
            return
        self._progress_bar.setValue(min(_PROGRESS_BAR_MAX, max(0, int(completed / total * 100))))

    def _update_progress_label(self, completed: int, total: int) -> None:
        """Update the textual progress counter label.

        Args:
            completed: Number of completed tasks.
            total: Total number of tasks.
        """
        self._progress_label.setText(format_progress_label(completed, total))

    def _update_eta_label(self, estimated_remaining_ms: float | None) -> None:
        """Update the ETA label using compact human-readable duration.

        Args:
            estimated_remaining_ms: Estimated remaining time in milliseconds, or None if unknown.
        """
        if estimated_remaining_ms is None:
            self._eta_label.setText("Calculating…")
            self._eta_label.setToolTip("ETA available after the first task completes.")
            return
        if estimated_remaining_ms <= 0:
            self._eta_label.setText("< 1s")
            self._eta_label.setToolTip("")
            return
        self._eta_label.setText(f"~{format_compact_duration(estimated_remaining_ms)}")
        self._eta_label.setToolTip("")

    def _update_elapsed_label(self, start_time_ms: float, current_time_ms: float) -> None:
        """Update the elapsed time label.

        Args:
            start_time_ms: Benchmark start time in milliseconds (monotonic).
            current_time_ms: Current time in milliseconds (monotonic).
        """
        self._elapsed_label.setText(format_compact_duration(max(0.0, current_time_ms - start_time_ms)))

    def _update_task_elapsed_label(self, task_start_ms: float, current_time_ms: float) -> None:
        """Update the per-task elapsed time label.

        Args:
            task_start_ms: Task start time in milliseconds (monotonic); 0 when no task is active.
            current_time_ms: Current time in milliseconds (monotonic).
        """
        if task_start_ms <= 0:
            self._task_elapsed_label.setText(_DASH)
            return
        self._task_elapsed_label.setText(format_compact_duration(max(0.0, current_time_ms - task_start_ms)))

    def _update_context_labels(self, provider: str, model: str, task: str) -> None:
        """Update the provider, model, and task context labels.

        Args:
            provider: Current provider identifier.
            model: Current model name.
            task: Current task identifier.
        """
        self._provider_label.setText(provider or _DASH)
        self._model_label.setText(model or _DASH)
        self._model_label.setToolTip(model)
        self._task_label.setText(task or _DASH)
        self._task_label.setToolTip(task)

    def _update_status_counts(self, counts: dict[str, int] | None) -> None:
        """Update task status counter labels from counts dict.

        Args:
            counts: Mapping of BenchmarkResultStatus string values to counts, or None to skip.
        """
        if counts is None:
            return
        self._count_not_completed.setText(str(counts.get(BenchmarkResultStatus.NOT_COMPLETED, 0)))
        self._count_waiting.setText(str(counts.get(BenchmarkResultStatus.WAITING_FOR_JUDGE, 0)))
        self._count_completed.setText(str(counts.get(BenchmarkResultStatus.COMPLETED, 0)))
        self._count_failed.setText(str(counts.get(BenchmarkResultStatus.FAILED, 0)))

    def sizeHint(self) -> QSize:
        """Return a reasonable default size hint for the panel.

        Returns:
            Preferred size for the progress panel widget.
        """
        return QSize(400, 300)
