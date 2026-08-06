"""``ResumeSummaryDialog`` -- the resume confirmation modal with drift (STORY-057-AC-1..4,7).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/resume_summary_dialog.md``
§3 (layout), §5 (drift warnings), §6 (resume gating), §7 (task picker), §9 (button
behaviour), §11 (resume effects). Presents and routes only -- never edits the run or
a result in place beyond the reset the confirm action performs through the gateway.

Both the BLOCKING and WARNING drift-warning groups render with the existing
``"warning-callout"`` theme role (differentiated by group heading text only) --
no dedicated red/error role exists yet in ``ui/theme`` for a QGroupBox/QLabel
context (only ``QPushButton[role="primary-button"]`` is styled by the stylesheet
generator today); inventing a new role is out of this story's scope.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.ui.common_dialogs._internal.actions import (
    resume_summary_fix_in_settings_not_yet_available,
)
from ollama_llm_bench.ui.common_dialogs.models import ResumeSummaryViewModel, TaskPickerRow
from ollama_llm_bench.ui.common_dialogs.protocols import ResumeSummaryGateway

__all__: list[str] = ["ResumeSummaryDialog"]

logger = structlog.get_logger(__name__)

_FIX_IN_SETTINGS_KINDS = frozenset(
    {
        "provider_now_disabled",
        "provider_now_unreachable",
        "provider_removed",
        "provider_env_var_missing",
        "model_no_longer_available",
        "judge_model_unavailable",
        "embedding_model_unavailable",
        "embedding_now_unreachable",
    }
)


class ResumeSummaryDialog(QDialog):
    """The Resume Summary confirmation dialog: drift, Tasks-to-resume picker, Resume Run."""

    def __init__(
        self,
        *,
        gateway: ResumeSummaryGateway,
        event_bus: EventBus,
        view_model: ResumeSummaryViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.resume_summary")
        self.setWindowTitle("Resume Summary")
        self._gateway = gateway
        self._event_bus = event_bus
        self._run_id = view_model.run_id
        self.task_item_by_result_id: dict[int, QListWidgetItem] = {}
        self.override_checkbox: QCheckBox | None = None
        self._build_ui(view_model)
        logger.debug(
            "resume_summary_dialog_constructed",
            run_id=view_model.run_id,
            blocking_warning_count=len(view_model.blocking_warnings),
        )

    def _build_ui(self, view_model: ResumeSummaryViewModel) -> None:
        outer = QVBoxLayout(self)
        legend = QLabel(view_model.intro_legend)
        legend.setProperty("role", "muted-caption")
        outer.addWidget(legend)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(_text_group("Original config", view_model.original_config_rows))
        content_layout.addWidget(_text_group("Current progress", view_model.current_progress_rows))
        if view_model.blocking_warnings or view_model.warning_warnings:
            content_layout.addWidget(self._build_drift_group(view_model))
        content_layout.addWidget(_text_group("Settings", (view_model.settings_note,)))
        content_layout.addWidget(self._build_task_picker(view_model.task_rows))
        scroll.setWidget(content)
        outer.addWidget(scroll)
        outer.addLayout(self._build_footer(has_blocking=bool(view_model.blocking_warnings)))

    def _build_drift_group(self, view_model: ResumeSummaryViewModel) -> QGroupBox:
        group = QGroupBox("Drift warnings")
        group.setProperty("role", "warning-callout")
        layout = QVBoxLayout(group)
        for warning in view_model.blocking_warnings:
            layout.addWidget(
                _build_warning_row(warning, on_fix_in_settings=self._on_fix_in_settings_clicked)
            )
        for warning in view_model.warning_warnings:
            layout.addWidget(_build_warning_row(warning, on_fix_in_settings=None))
        if view_model.blocking_warnings:
            total_affected = sum(w.pending_results_affected for w in view_model.blocking_warnings)
            self.override_checkbox = QCheckBox(
                f"Resume anyway — affected tasks will fail ({total_affected} affected)"
            )
            self.override_checkbox.setObjectName("common_dialogs.resume_summary.override_checkbox")
            self.override_checkbox.setAccessibleName("Resume anyway")
            self.override_checkbox.toggled.connect(self._on_override_toggled)
            layout.addWidget(self.override_checkbox)
        return group

    def _build_task_picker(self, task_rows: tuple[TaskPickerRow, ...]) -> QGroupBox:
        group = QGroupBox("Tasks to resume — not-yet-completed tasks are pre-checked")
        layout = QVBoxLayout(group)
        header = QHBoxLayout()
        select_all = QPushButton("Select all")
        select_all.setObjectName("common_dialogs.resume_summary.select_all_button")
        select_all.setAccessibleName("Select all")
        select_all.setProperty("role", "outlined-muted-button")
        select_all.clicked.connect(lambda: self._toggle_all_enabled(checked=True))
        clear_all = QPushButton("Clear all")
        clear_all.setObjectName("common_dialogs.resume_summary.clear_all_button")
        clear_all.setAccessibleName("Clear all")
        clear_all.setProperty("role", "outlined-muted-button")
        clear_all.clicked.connect(lambda: self._toggle_all_enabled(checked=False))
        header.addWidget(select_all)
        header.addWidget(clear_all)
        header.addStretch()
        layout.addLayout(header)
        self.task_list = QListWidget()
        self.task_list.setObjectName("common_dialogs.resume_summary.task_list")
        self.task_list.setAccessibleName("Tasks to resume")
        for row in task_rows:
            item = QListWidgetItem(f"{row.task_id}  ·  {row.status_chip_label}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if row.is_checked else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, row.result_id)
            if not row.is_enabled:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Blocked by an unresolved drift warning until confirmed")
            self.task_item_by_result_id[row.result_id] = item
            self.task_list.addItem(item)
        layout.addWidget(self.task_list)
        return group

    def _build_footer(self, *, has_blocking: bool) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("common_dialogs.resume_summary.cancel_button")
        cancel_button.setAccessibleName("Cancel")
        cancel_button.setProperty("role", "outlined-muted-button")
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        self.resume_button = QPushButton("Resume Run")
        self.resume_button.setObjectName("common_dialogs.resume_summary.resume_button")
        self.resume_button.setAccessibleName("Resume Run")
        self.resume_button.setProperty("role", "primary-button")
        self.resume_button.setDefault(True)
        self.resume_button.setEnabled(not has_blocking)
        if has_blocking:
            self.resume_button.setToolTip("Tick “Resume anyway” to enable")
        self.resume_button.clicked.connect(self._on_resume_clicked)
        footer.addWidget(self.resume_button)
        return footer

    def _toggle_all_enabled(self, *, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for item in self.task_item_by_result_id.values():
            if item.flags() & Qt.ItemFlag.ItemIsEnabled:
                item.setCheckState(state)

    def _on_override_toggled(self, checked: bool) -> None:  # noqa: FBT001  # Qt signal signature
        logger.debug("resume_summary_dialog_override_toggled", checked=checked)
        self.resume_button.setEnabled(checked)
        self.resume_button.setToolTip("" if checked else "Tick “Resume anyway” to enable")
        for item in self.task_item_by_result_id.values():
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled)
            item.setToolTip("")
            if checked:
                item.setCheckState(Qt.CheckState.Checked)

    def _on_fix_in_settings_clicked(self) -> None:
        logger.debug("resume_summary_dialog_fix_in_settings_clicked")
        resume_summary_fix_in_settings_not_yet_available(event_bus=self._event_bus)
        self.reject()

    def _on_resume_clicked(self) -> None:
        checked_result_ids = tuple(
            result_id
            for result_id, item in self.task_item_by_result_id.items()
            if item.checkState() == Qt.CheckState.Checked
        )
        logger.debug(
            "resume_summary_dialog_resume_clicked",
            run_id=self._run_id,
            checked_count=len(checked_result_ids),
        )
        if checked_result_ids:
            self._gateway.reset_results(checked_result_ids)
        self._gateway.resume_run(self._run_id)
        self.accept()


def _build_warning_row(
    warning: DriftWarning, *, on_fix_in_settings: Callable[[], None] | None
) -> QWidget:
    row = QWidget()
    row_layout = QVBoxLayout(row)
    headline = QLabel(warning.headline)
    row_layout.addWidget(headline)
    if warning.detail:
        detail = QLabel(warning.detail)
        detail.setWordWrap(True)
        row_layout.addWidget(detail)
    if on_fix_in_settings is not None and warning.kind.value in _FIX_IN_SETTINGS_KINDS:
        fix_button = QPushButton("Fix in Settings")
        fix_button.setObjectName("common_dialogs.resume_summary.fix_in_settings_button")
        fix_button.setAccessibleName("Fix in Settings")
        fix_button.setProperty("role", "outlined-muted-button")
        fix_button.clicked.connect(on_fix_in_settings)
        row_layout.addWidget(fix_button)
    return row


def _text_group(title: str, rows: tuple[str, ...]) -> QGroupBox:
    group = QGroupBox(title)
    layout = QVBoxLayout(group)
    for row in rows:
        label = QLabel(row)
        label.setWordWrap(True)
        layout.addWidget(label)
    return group
