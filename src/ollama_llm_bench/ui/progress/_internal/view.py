"""``ProgressView`` -- the passive Progress widget view: header row + the Run
Progress/Model two-column row (``04_Progress_Widget/description.md`` §2, §3, §4, §5,
§6.1; STORY-058). No Current-Task or Log regions -- those are STORY-059/STORY-060.

Passive View: renders a ``ViewModel`` slice per ``apply_*`` method and emits
widget-local Qt signals on user interaction; imports no adapter Gateway, no reactive
store, and no backend service symbol.
"""

from typing import Final

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.domain import ResultStatus
from ollama_llm_bench.ui.progress._internal.header import ProgressHeaderWidget
from ollama_llm_bench.ui.progress._internal.stage_badge import StageBadgeWidget
from ollama_llm_bench.ui.progress._internal.theme_lookup import (
    resolve_spacing_tokens,
    resolve_theme_tokens,
)
from ollama_llm_bench.ui.progress.models import (
    CountersViewModel,
    CurrentTaskViewModel,
    HeaderAffordances,
    ProgressViewModel,
    StabilityViewModel,
)
from ollama_llm_bench.ui.shared import BadgeStatus, make_badge_label
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = ["ProgressView"]

# description.md §4's per-ResultStatus counter rows shown as plain per-phase counts
# (the "Failed" row is a derived aggregate, read from `badge_counts` instead -- §4).
_COUNTER_ROWS: Final[tuple[tuple[str, ResultStatus], ...]] = (
    ("Pending", ResultStatus.PENDING),
    ("Keyword-wait", ResultStatus.AWAITING_KEYWORD_CHECK),
    ("Cosine-wait", ResultStatus.AWAITING_COSINE_CHECK),
    ("Judge-wait", ResultStatus.AWAITING_JUDGE_CHECK),
    ("Completed", ResultStatus.COMPLETED),
)
# description.md §5's segment tone table.
_SEGMENT_TONE: Final[dict[str, str]] = {
    "bench": "primary",
    "judge_wait": "warn",
    "failed": "error",
    "pending": "mute",
    "complete": "success",
}
_SEGMENT_FILL_ROLE: Final[dict[str, str]] = {
    "primary": "primary.disabled",
    "warn": "warning.fill",
    "error": "error.fill",
    "mute": "muted.fill",
    "success": "success.fill",
}
_STABILITY_BADGE_STATUS: Final[dict[str, BadgeStatus]] = {
    "ok": BadgeStatus.PASS,
    "closed": BadgeStatus.PASS,
    "warn": BadgeStatus.WARNING,
    "excluded": BadgeStatus.FAIL,
    "open": BadgeStatus.FAIL,
}

# Current-task grid row indices, in _build_current_task_panel's addRow order --
# named so apply_current_task never hardcodes a bare row number (AC-1..AC-6).
_CURRENT_TASK_RETRY_ROW: Final[int] = 4
_CURRENT_TASK_INFERENCE_ROW: Final[int] = 5
_CURRENT_TASK_JUDGE_ROW: Final[int] = 6


class ProgressView(QWidget):
    """The Progress widget's passive view: header + Run Progress/Model row."""

    rename_clicked = Signal()
    pause_resume_clicked = Signal()
    stop_clicked = Signal()
    retry_probe_clicked = Signal()

    def __init__(
        self,
        *,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        super().__init__()
        self.setObjectName("progress")
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._header = ProgressHeaderWidget(
            theme_manager=theme_manager, platform_kind=platform_kind
        )
        self._header.rename_clicked.connect(self.rename_clicked)
        self._header.pause_resume_clicked.connect(self.pause_resume_clicked)
        self._header.stop_clicked.connect(self.stop_clicked)
        self._counter_value_labels: dict[str, QLabel] = {}
        self._build_counters_panel()
        self._build_model_panel()
        self._build_current_task_panel()
        self._build_layout()

    @property
    def stage_badge(self) -> StageBadgeWidget:
        """The header's stage-badge pill (for direct inspection in tests)."""
        return self._header.stage_badge

    def _build_layout(self) -> None:
        spacing = resolve_spacing_tokens(platform_kind=self._platform_kind).spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(spacing.md, spacing.md, spacing.md, spacing.md)
        root.setSpacing(spacing.md)
        root.addWidget(self._header)
        row = QHBoxLayout()
        row.setSpacing(spacing.lg)
        row.addWidget(self._counters_group, 1)
        row.addWidget(self._model_group, 1)
        root.addLayout(row)
        root.addWidget(self._current_task_group)
        root.addStretch(1)

    def _build_counters_panel(self) -> None:
        self._counters_group = QGroupBox("Run Progress")
        self._counters_group.setObjectName("progress.counters")
        form = QFormLayout()
        self._tasks_label = QLabel("—")
        self._eta_label = QLabel("—")
        self._total_time_label = QLabel("—")
        form.addRow("Tasks", self._tasks_label)
        form.addRow("ETA", self._eta_label)
        form.addRow("Total Time", self._total_time_label)
        for row_label, _status in _COUNTER_ROWS:
            value_label = QLabel("0")
            self._counter_value_labels[row_label] = value_label
            form.addRow(row_label, value_label)
        failed_label = QLabel("0")
        self._counter_value_labels["Failed"] = failed_label
        form.addRow("Failed", failed_label)
        self._stage_bar = QWidget()
        self._stage_bar.setObjectName("progress.counters.stage_bar")
        self._stage_bar.setFixedHeight(10)
        self._stage_bar_layout = QHBoxLayout(self._stage_bar)
        self._stage_bar_layout.setContentsMargins(0, 0, 0, 0)
        self._stage_bar_layout.setSpacing(0)
        self._badge_row_label = QLabel("")
        self._badge_row_label.setObjectName("progress.counters.badge_row")
        layout = QVBoxLayout(self._counters_group)
        layout.addLayout(form)
        layout.addWidget(self._stage_bar)
        layout.addWidget(self._badge_row_label)

    def _build_model_panel(self) -> None:
        self._model_group = QGroupBox("Model")
        self._model_group.setObjectName("progress.model")
        form = QFormLayout()
        self._provider_label = QLabel("—")
        self._provider_label.setObjectName("progress.model.provider")
        self._model_label = QLabel("—")
        self._model_label.setObjectName("progress.model.model")
        form.addRow("Provider", self._provider_label)
        form.addRow("Model", self._model_label)
        self._stability_container = QWidget()
        self._stability_container.setObjectName("progress.model.stability")
        self._stability_layout = QVBoxLayout(self._stability_container)
        self._stability_layout.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self._model_group)
        layout.addLayout(form)
        layout.addWidget(self._stability_container)

    def _build_current_task_panel(self) -> None:
        self._current_task_group = QGroupBox("Current Task")
        self._current_task_group.setObjectName("progress.current_task")
        form = QFormLayout()
        form.setObjectName("progress.current_task.form")
        self._task_id_label = QLabel("—")
        self._task_id_label.setObjectName("progress.current_task.task_id")
        self._current_task_stage_label = QLabel("—")
        self._current_task_stage_label.setObjectName("progress.current_task.stage")
        self._task_time_label = QLabel("—")
        self._task_time_label.setObjectName("progress.current_task.task_time")
        self._timeouts_label = QLabel("0")
        self._timeouts_label.setObjectName("progress.current_task.timeouts")
        self._retry_container = QWidget()
        self._retry_container.setObjectName("progress.current_task.retry")
        self._retry_layout = QVBoxLayout(self._retry_container)
        self._retry_layout.setContentsMargins(0, 0, 0, 0)
        self._inference_progress_label = QLabel("")
        self._inference_progress_label.setObjectName("progress.current_task.inference_progress")
        self._judge_progress_label = QLabel("")
        self._judge_progress_label.setObjectName("progress.current_task.judge_progress")
        form.addRow("Task", self._task_id_label)
        form.addRow("Stage", self._current_task_stage_label)
        form.addRow("Task Time", self._task_time_label)
        form.addRow("Timeouts", self._timeouts_label)
        form.addRow("Retry", self._retry_container)
        form.addRow("Inference progress", self._inference_progress_label)
        form.addRow("Judge progress", self._judge_progress_label)
        self._current_task_form = form
        layout = QVBoxLayout(self._current_task_group)
        layout.addLayout(form)

    def apply_header(self, *, run_name: str, affordances: HeaderAffordances) -> None:
        """Render the run-name/pencil/Pause-Resume/Stop header slice (AC-2, AC-3)."""
        self._header.apply(run_name=run_name, affordances=affordances)

    def apply_draining_status(self, text: str | None) -> None:
        """Render the SPEC-098 Pausing/Stopping draining status line (description.md
        §3.4); `None` hides it."""
        self._header.set_draining_status(text)

    def apply_counters(self, vm: CountersViewModel) -> None:
        """Render the counters/stage-bar/badges/ETA/model-id slice (AC-1, AC-4, AC-5)."""
        self._header.stage_badge.set_stage(vm.stage)
        self._tasks_label.setText(f"{vm.tasks_done} / {vm.tasks_total}")
        self._eta_label.setText(vm.eta_label)
        self._total_time_label.setText(vm.total_time_label)
        for row_label, status in _COUNTER_ROWS:
            self._counter_value_labels[row_label].setText(str(vm.counts_by_status.get(status, 0)))
        badges = dict(vm.badge_counts)
        self._counter_value_labels["Failed"].setText(str(badges.get("failed", 0)))
        self._render_stage_bar(vm.bar_segments)
        self._badge_row_label.setText(
            "   ".join(f"{name} {count}" for name, count in vm.badge_counts)
        )
        self._provider_label.setText(vm.provider_label)
        self._model_label.setText(vm.model_label)

    def apply_stability(self, vm: StabilityViewModel) -> None:
        """Render the model-/provider-stability callouts (AC-6)."""
        while self._stability_layout.count():
            item = self._stability_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._stability_layout.addWidget(
            self._make_callout(status=vm.model_band, text=vm.model_text)
        )
        self._stability_layout.addWidget(
            self._make_callout(status=vm.provider_band, text=vm.provider_text)
        )
        if vm.judge_excluded_text is not None:
            self._stability_layout.addWidget(
                self._make_callout(status="excluded", text=vm.judge_excluded_text)
            )

    def apply_current_task(self, vm: CurrentTaskViewModel) -> None:
        """Render the Current-task grid + the two live progress sub-rows (AC-1..AC-6)."""
        self._task_id_label.setText(vm.task_id or "—")
        self._current_task_stage_label.setText(vm.stage_label)
        self._task_time_label.setText(vm.task_time_label)
        self._timeouts_label.setText(str(vm.timeouts))
        self._render_retry_line(vm)
        self._current_task_form.setRowVisible(
            _CURRENT_TASK_INFERENCE_ROW, vm.inference_progress_visible
        )
        if vm.inference_progress_label is not None:
            self._inference_progress_label.setText(vm.inference_progress_label)
        self._current_task_form.setRowVisible(_CURRENT_TASK_JUDGE_ROW, vm.judge_progress_visible)
        if vm.judge_progress_label is not None:
            self._judge_progress_label.setText(vm.judge_progress_label)

    def _render_retry_line(self, vm: CurrentTaskViewModel) -> None:
        while self._retry_layout.count():
            item = self._retry_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if vm.retry_active and vm.retry_label is not None:
            self._retry_layout.addWidget(self._make_callout(status="excluded", text=vm.retry_label))
        self._current_task_form.setRowVisible(_CURRENT_TASK_RETRY_ROW, vm.retry_active)

    def apply(self, vm: ProgressViewModel) -> None:
        """The single top-level render entry point (idempotent)."""
        self.apply_header(
            run_name=vm.run_name,
            affordances=HeaderAffordances(
                show_rename_pencil=vm.show_rename_pencil,
                pause_resume_label=vm.pause_resume_label,
                pause_resume_visible=vm.pause_resume_visible,
                pause_resume_enabled=vm.pause_resume_enabled,
                stop_visible=vm.stop_visible,
                stop_enabled=vm.stop_enabled,
            ),
        )
        self.apply_counters(vm.counters)
        self.apply_current_task(vm.current_task)
        self.apply_stability(vm.stability)

    def _make_callout(self, *, status: str, text: str) -> QWidget:
        if self._theme_manager is None:
            return QLabel(text)
        badge_status = _STABILITY_BADGE_STATUS.get(status, BadgeStatus.NEUTRAL)
        return make_badge_label(
            status=badge_status,
            text=text,
            theme_manager=self._theme_manager,
            platform_kind=self._platform_kind,
        )

    def _render_stage_bar(self, segments: tuple[tuple[str, int], ...]) -> None:
        while self._stage_bar_layout.count():
            item = self._stage_bar_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for name, weight in segments:
            self._stage_bar_layout.addWidget(self._make_segment(name), weight)

    def _make_segment(self, name: str) -> QWidget:
        segment = QWidget()
        segment.setAutoFillBackground(True)
        color_hex = self._segment_color_hex(name)
        if color_hex is not None:
            palette = segment.palette()
            palette.setColor(QPalette.ColorRole.Window, QColor(color_hex))
            segment.setPalette(palette)
        return segment

    def _segment_color_hex(self, segment_name: str) -> str | None:
        if self._theme_manager is None:
            return None
        tone = _SEGMENT_TONE.get(segment_name, "mute")
        role = _SEGMENT_FILL_ROLE[tone]
        tokens = resolve_theme_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        return resolve_color(tokens, role)
