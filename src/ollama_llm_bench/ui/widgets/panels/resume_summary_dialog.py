"""ResumeSummaryDialog — pre-resume confirmation dialog for unfinished benchmark runs."""

from __future__ import annotations

import json
import logging
from collections import Counter

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

from ollama_llm_bench.backend.core.constants import RUN_MODE_LABELS
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
)
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController

_logger = logging.getLogger(__name__)

_DIALOG_MIN_WIDTH = 640
_FROZEN_CONFIG_NOTE = (
    "These values are frozen from the original run and cannot be changed. "
    "Drift warnings appear when a provider is no longer enabled."
)


class _CollapsibleSection(QWidget):
    """A collapsible section with a toggle button header and a body frame."""

    def __init__(self, title: str, body: QWidget, parent: QWidget | None = None) -> None:
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
        title_text = self._toggle.text()[3:]
        prefix = "▼  " if checked else "▶  "
        self._toggle.setText(prefix + title_text)


class ResumeSummaryDialog(QDialog):
    """Pre-resume confirmation dialog showing original config and current progress.

    Performs three synchronous reads on construction (all small, single-row queries):
    the BenchmarkRun record, its BenchmarkResult rows, and the set of currently
    enabled providers. Displays a drift warning banner when any provider referenced
    by the original run is no longer enabled.
    """

    def __init__(
        self,
        *,
        run_id: int,
        controller: RunConfigController,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the dialog by loading the run data and building the UI.

        Args:
            run_id: ID of the NOT_COMPLETED run to resume.
            controller: Run configuration controller used for data access.
            parent: Optional parent widget for proper dialog stacking.
        """
        super().__init__(parent)
        self._run_id = run_id
        self._controller = controller

        self.setWindowTitle("Resume Benchmark")
        self.setMinimumWidth(_DIALOG_MIN_WIDTH)

        run = controller.get_run(run_id)
        results = controller.get_results_for_run(run_id)
        enabled_providers = controller.get_enabled_provider_ids()

        drift_warnings = self._detect_drift(run, enabled_providers)

        self._build_ui(run, results, drift_warnings)

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def _detect_drift(self, run: BenchmarkRun, enabled_providers: set[str]) -> list[str]:
        """Return list of drift warning strings."""
        warnings: list[str] = []
        if run.judge_provider_id and run.judge_provider_id not in enabled_providers:
            warnings.append(f"Judge provider '{run.judge_provider_id}' is no longer enabled.")
        try:
            models: list[dict[str, str]] = json.loads(run.models_json)
        except (json.JSONDecodeError, ValueError):
            models = []
        drifted = {
            m["provider_id"] for m in models if m.get("provider_id") and m["provider_id"] not in enabled_providers
        }
        for pid in sorted(drifted):
            warnings.append(f"Test provider '{pid}' is no longer enabled.")
        return warnings

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(
        self,
        run: BenchmarkRun,
        results: list[BenchmarkResult],
        drift_warnings: list[str],
    ) -> None:
        heading = QLabel("Resume benchmark")
        heading.setProperty("role", "heading")

        note = QLabel(_FROZEN_CONFIG_NOTE)
        note.setProperty("role", "secondary")
        note.setWordWrap(True)

        scroll_contents = QWidget()
        scroll_layout = QVBoxLayout(scroll_contents)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(4)

        if drift_warnings:
            scroll_layout.addWidget(self._build_drift_banner(drift_warnings))

        scroll_layout.addWidget(_CollapsibleSection("Original Configuration", self._build_config_body(run)))
        scroll_layout.addWidget(_CollapsibleSection("Current Progress", self._build_progress_body(run, results)))
        scroll_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_contents)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        btn_box = QDialogButtonBox()
        resume_btn = btn_box.addButton("Resume Run", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        if resume_btn is not None:
            resume_btn.setProperty("role", "primary")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.addWidget(heading)
        root.addWidget(note)
        root.addWidget(scroll, stretch=1)
        root.addWidget(btn_box)

    def _build_drift_banner(self, warnings: list[str]) -> QFrame:
        banner = QFrame()
        banner.setFrameShape(QFrame.Shape.StyledPanel)
        banner.setProperty("role", "warning")
        layout = QVBoxLayout(banner)
        layout.setContentsMargins(8, 6, 8, 6)
        for text in warnings:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        return banner

    def _build_config_body(self, run: BenchmarkRun) -> QWidget:
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        form = QFormLayout(body)
        form.setContentsMargins(8, 4, 8, 4)

        mode_label = RUN_MODE_LABELS.get(run.run_mode, str(run.run_mode))
        form.addRow("Mode:", QLabel(mode_label))
        form.addRow("Judge provider:", QLabel(run.judge_provider_id or "(none)"))
        form.addRow("Judge model:", QLabel(run.judge_model or "(none)"))

        try:
            raw_models: list[dict[str, str]] = json.loads(run.models_json)
            model_entries = [f"{m.get('provider_id', '')} / {m.get('model_name', '')}" for m in raw_models]
        except (json.JSONDecodeError, ValueError):
            model_entries = []

        models_text = "\n".join(model_entries) if model_entries else "(none)"
        models_lbl = QLabel(models_text)
        models_lbl.setWordWrap(True)
        form.addRow("Test models:", models_lbl)

        task_paths = run.task_file_paths
        tasks_text = "\n".join(str(p) for p in task_paths) if task_paths else "(none)"
        tasks_lbl = QLabel(tasks_text)
        tasks_lbl.setWordWrap(True)
        form.addRow("Task files:", tasks_lbl)

        return body

    def _build_progress_body(self, run: BenchmarkRun, results: list[BenchmarkResult]) -> QWidget:
        body = QFrame()
        body.setFrameShape(QFrame.Shape.StyledPanel)
        form = QFormLayout(body)
        form.setContentsMargins(8, 4, 8, 4)

        counts: Counter[BenchmarkResultStatus] = Counter(r.status for r in results)

        form.addRow("Total tasks:", QLabel(str(run.total_tasks)))
        form.addRow("Completed:", QLabel(str(counts[BenchmarkResultStatus.COMPLETED])))
        form.addRow(
            "Waiting for judge:",
            QLabel(str(counts[BenchmarkResultStatus.WAITING_FOR_JUDGE])),
        )
        form.addRow(
            "Not completed:",
            QLabel(str(counts[BenchmarkResultStatus.NOT_COMPLETED])),
        )
        form.addRow("Failed:", QLabel(str(counts[BenchmarkResultStatus.FAILED])))

        return body
