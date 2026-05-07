"""RunSummaryDialog — pre-start confirmation dialog for benchmark runs."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.constants import RUN_MODE_DESCRIPTIONS, RUN_MODE_LABELS
from ollama_llm_bench.backend.core.models import RunMode, RunSummary

_logger = logging.getLogger(__name__)

_NO_MODELS_WARNING: str = "Select at least one test model before starting."
_NO_TASKS_WARNING: str = "Add at least one task file before starting."
_DIALOG_MIN_WIDTH: int = 720


class _CollapsibleSection(QWidget):
    """A collapsible section with a toggle button header and a body frame."""

    def __init__(self, title: str, body: QWidget, parent: QWidget | None = None) -> None:
        """Initialise the collapsible section.

        Args:
            title: Section header text.
            body: Widget displayed when the section is expanded.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._toggle = QPushButton(f"▼  {title}")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(True)
        self._toggle.setFlat(True)
        self._toggle.setStyleSheet("text-align: left; font-weight: bold; padding: 4px 2px;")
        self._body = body

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(0)
        layout.addWidget(self._toggle)
        layout.addWidget(self._body)

        self._toggle.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self._body.setVisible(checked)
        title_text = self._toggle.text()[3:]  # strip "▼  " or "▶  "
        prefix = "▼  " if checked else "▶  "
        self._toggle.setText(prefix + title_text)


class RunSummaryDialog(QDialog):
    """Pre-start confirmation dialog showing a snapshot of the benchmark configuration.

    Displays mode, judge, test models, task files, advanced options, mode-specific
    settings, and an estimated work summary. The 'Start Benchmark' button is disabled
    when required fields (models or tasks) are missing.
    """

    def __init__(self, *, summary: RunSummary, parent: QWidget | None = None) -> None:
        """Initialise the dialog with the given run summary snapshot.

        Args:
            summary: Frozen snapshot of the run configuration to confirm.
            parent: Optional parent widget for proper dialog stacking.
        """
        super().__init__(parent)
        self._summary = summary
        self._start_btn: QPushButton
        self._warning_label: QLabel
        self._no_judge_warning: QLabel | None
        self._task_files_section: _CollapsibleSection

        self.setWindowTitle("Confirm Benchmark Configuration")
        self.setMinimumWidth(_DIALOG_MIN_WIDTH)

        self._build_widgets()
        self._build_layout()
        self._validate()

    # ------------------------------------------------------------------
    # Build phases
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        self._heading = QLabel("Confirm benchmark configuration")
        self._heading.setProperty("role", "heading")

        self._warning_label = QLabel()
        self._warning_label.setProperty("role", "warning")
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)

        self._sections: list[_CollapsibleSection] = []
        self._sections.append(_CollapsibleSection("Mode", self._build_mode_body()))
        self._judge_section = _CollapsibleSection("Judge", self._build_judge_body())
        self._sections.append(self._judge_section)
        self._sections.append(_CollapsibleSection("Test Models", self._build_models_body()))
        self._task_files_section = _CollapsibleSection("Task Files", self._build_task_files_body())
        self._sections.append(self._task_files_section)
        self._sections.append(_CollapsibleSection("Advanced Options", self._build_advanced_body()))
        self._mode_specific_section = _CollapsibleSection("Mode-specific Settings", self._build_mode_specific_body())
        self._sections.append(self._mode_specific_section)
        self._sections.append(_CollapsibleSection("Estimated Work", self._build_estimated_work_body()))

        # Show judge section for full grading / prompt eval, and for speed/performance when flag is on
        _show_judge_for_run_analysis = (
            self._summary.run_mode in (RunMode.PERFORMANCE, RunMode.SPEED) and self._summary.judge_run_analysis_enabled
        )
        self._judge_section.setVisible(
            self._summary.run_mode in (RunMode.FULL_GRADING, RunMode.PROMPT_EVAL) or _show_judge_for_run_analysis
        )
        if _show_judge_for_run_analysis and not (self._summary.judge_provider_id and self._summary.judge_model_name):
            self._no_judge_warning = QLabel(
                "Run-level analysis is enabled but no judge model is selected. The analysis will be skipped."
            )
            self._no_judge_warning.setWordWrap(True)
            self._no_judge_warning.setProperty("role", "warning")
        else:
            self._no_judge_warning = None
        # Hide mode-specific section for speed/full-grading modes
        self._mode_specific_section.setVisible(self._summary.run_mode in (RunMode.PERFORMANCE, RunMode.PROMPT_EVAL))
        self._task_files_section.setVisible(self._summary.run_mode != RunMode.PERFORMANCE)

        btn_box = QDialogButtonBox()
        self._start_btn = btn_box.addButton("Start Benchmark", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("Edit", QDialogButtonBox.ButtonRole.RejectRole)
        if self._start_btn is not None:
            self._start_btn.setProperty("role", "primary")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        self._btn_box = btn_box

    def _build_layout(self) -> None:
        scroll_contents = QWidget()
        scroll_layout = QVBoxLayout(scroll_contents)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(4)
        for section in self._sections:
            scroll_layout.addWidget(section)
        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_contents)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.addWidget(self._heading)
        root.addWidget(self._warning_label)
        if self._no_judge_warning is not None:
            root.addWidget(self._no_judge_warning)
        root.addWidget(scroll, stretch=1)
        root.addWidget(self._btn_box)

    # ------------------------------------------------------------------
    # Section body builders
    # ------------------------------------------------------------------

    def _build_mode_body(self) -> QWidget:
        """Build the Mode section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 4, 8, 4)
        mode_label = QLabel(RUN_MODE_LABELS.get(self._summary.run_mode, str(self._summary.run_mode)))
        mode_label.setProperty("role", "secondary")
        desc_label = QLabel(RUN_MODE_DESCRIPTIONS.get(self._summary.run_mode, ""))
        desc_label.setWordWrap(True)
        layout.addWidget(mode_label)
        layout.addWidget(desc_label)
        return body

    def _build_judge_body(self) -> QWidget:
        """Build the Judge section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        form = QFormLayout(body)
        form.setContentsMargins(8, 4, 8, 4)
        provider = self._summary.judge_provider_id or "(none)"
        model = self._summary.judge_model_name or "(none)"
        form.addRow("Provider:", QLabel(provider))
        form.addRow("Model:", QLabel(model))
        return body

    def _build_models_body(self) -> QWidget:
        """Build the Test Models section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        if not self._summary.selected_models:
            warn = QLabel("No models selected.")
            warn.setProperty("role", "warning")
            layout.addWidget(warn)
        else:
            for key in self._summary.selected_models:
                layout.addWidget(QLabel(f"{key.provider_id}  /  {key.model_name}"))
        return body

    def _build_task_files_body(self) -> QWidget:
        """Build the Task Files section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        if not self._summary.task_file_paths:
            warn = QLabel("No task files added.")
            warn.setProperty("role", "warning")
            layout.addWidget(warn)
        else:
            for path in self._summary.task_file_paths:
                layout.addWidget(QLabel(str(path)))
        return body

    def _build_advanced_body(self) -> QWidget:
        """Build the Advanced Options section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        opts = self._summary.advanced_options
        form = QFormLayout(body)
        form.setContentsMargins(8, 4, 8, 4)

        def _source(is_override: bool) -> str:
            return "per-run override" if is_override else "default from Settings"

        stream_val = "enabled" if opts.streaming_enabled else "disabled"
        form.addRow("Streaming:", QLabel(f"{stream_val}  ({_source(opts.streaming_is_override)})"))

        warmup_val = "enabled" if opts.warmup_enabled else "disabled"
        form.addRow("Warmup:", QLabel(f"{warmup_val}  ({_source(opts.warmup_is_override)})"))

        form.addRow(
            "Reasoning effort:",
            QLabel(f"{opts.reasoning_effort}  ({_source(opts.reasoning_is_override)})"),
        )
        return body

    def _build_mode_specific_body(self) -> QWidget:
        """Build the Mode-specific Settings section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 4, 8, 4)

        if self._summary.run_mode == RunMode.PERFORMANCE:
            form = QFormLayout()
            input_sizes = ", ".join(self._summary.performance_input_sizes) or "(none)"
            output_sizes = ", ".join(self._summary.performance_output_sizes) or "(none)"
            form.addRow("Input sizes:", QLabel(input_sizes))
            form.addRow("Output sizes:", QLabel(output_sizes))
            form.addRow("Repeats:", QLabel(str(self._summary.performance_repeats)))
            layout.addLayout(form)
        elif self._summary.run_mode == RunMode.PROMPT_EVAL:
            layout.addWidget(QLabel("Prompt variant evaluation mode selected."))
        else:
            layout.addWidget(QLabel("(no mode-specific settings)"))

        return body

    def _build_estimated_work_body(self) -> QWidget:
        """Build the Estimated Work section body widget."""
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 4, 8, 4)
        n_models = len(self._summary.selected_models)
        n_files = len(self._summary.task_file_paths)
        layout.addWidget(QLabel(f"{n_models} model(s) x {n_files} task file(s)"))
        return body

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        """Disable Start and show a warning when required fields are missing."""
        has_models = len(self._summary.selected_models) > 0
        tasks_required = self._summary.run_mode != RunMode.PERFORMANCE
        has_tasks = (not tasks_required) or len(self._summary.task_file_paths) > 0

        if not has_models:
            self._warning_label.setText(_NO_MODELS_WARNING)
            self._warning_label.setVisible(True)
        elif not has_tasks:
            self._warning_label.setText(_NO_TASKS_WARNING)
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

        can_start = has_models and has_tasks
        if self._start_btn is not None:
            self._start_btn.setEnabled(can_start)
