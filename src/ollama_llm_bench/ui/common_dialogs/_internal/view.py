"""``RunSummaryDialog`` -- the pre-start confirmation modal (STORY-055-AC-6, AC-8).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§3 (layout), §10 (button behaviour), §12 (Start Effects). Renders a frozen
``RunSummaryViewModel``; presents and re-checks only, never edits configuration
(§1). Holds ``RunSummaryGateway`` directly -- its own per-widget Gateway Protocol
(D-R-06), not a backend Store/Service -- because this dialog is simple enough
that a separate controller class would add no value beyond what the factory
(``api.py``) and this one passive-rendering-plus-two-buttons class already give.
"""

from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.backend.domain import RunStartRequest
from ollama_llm_bench.ui.common_dialogs.models import RunSummaryViewModel
from ollama_llm_bench.ui.common_dialogs.protocols import RunSummaryGateway

__all__: list[str] = ["RunSummaryDialog"]

logger = structlog.get_logger(__name__)


class RunSummaryDialog(QDialog):
    """The Run Summary confirmation dialog: renders ``view_model``, Back / Start."""

    def __init__(
        self,
        *,
        gateway: RunSummaryGateway,
        request: RunStartRequest,
        view_model: RunSummaryViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.run_summary")
        self.setWindowTitle("Run Summary")
        self._gateway = gateway
        self._request = request
        self._build_ui(view_model)
        logger.debug("run_summary_dialog_constructed", run_mode=view_model.run_mode.value)

    def _build_ui(self, view_model: RunSummaryViewModel) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        for group in self._build_sections(view_model):
            content_layout.addWidget(group)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        outer.addLayout(self._build_footer())

    def _build_sections(self, view_model: RunSummaryViewModel) -> list[QGroupBox]:
        sections = [
            _text_group("Mode and run name", (view_model.run_name_preview,)),
            _text_group("Test models", view_model.test_model_rows),
            _text_group("Judge", (view_model.judge_summary,)),
        ]
        if view_model.embedding_summary is not None:
            sections.append(_text_group("Embedding", (view_model.embedding_summary,)))
        if view_model.task_file_summary is not None:
            sections.append(_text_group("Task files", (view_model.task_file_summary,)))
        if view_model.synthetic_matrix_rows is not None:
            sections.append(
                _text_group("Synthetic prompt matrix", view_model.synthetic_matrix_rows)
            )
        sections.append(_text_group("Work to be done", (view_model.work_to_be_done,)))
        sections.append(_text_group("Inference", view_model.inference_snapshot_rows))
        sections.append(_text_group("Pipeline events", view_model.pipeline_events_rows))
        if view_model.evaluation_phase_rows is not None:
            sections.append(_text_group("Evaluation phases", view_model.evaluation_phase_rows))
        if view_model.warnings:
            warnings_group = _text_group("Warnings", view_model.warnings)
            warnings_group.setProperty("role", "warning-callout")
            sections.append(warnings_group)
        return sections

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addStretch()
        self._back_button = QPushButton("Back")
        self._back_button.setObjectName("common_dialogs.run_summary.back_button")
        self._back_button.setAccessibleName("Back")
        self._back_button.setProperty("role", "outlined-muted-button")
        self._back_button.clicked.connect(self.reject)
        footer.addWidget(self._back_button)
        self._start_button = QPushButton("Start Benchmark")
        self._start_button.setObjectName("common_dialogs.run_summary.start_button")
        self._start_button.setAccessibleName("Start Benchmark")
        self._start_button.setProperty("role", "primary-button")
        self._start_button.setDefault(True)
        self._start_button.clicked.connect(self._on_start_clicked)
        footer.addWidget(self._start_button)
        return footer

    def _on_start_clicked(self) -> None:
        logger.debug("run_summary_dialog_start_clicked")
        self._gateway.start_run(self._request)
        self.accept()


def _text_group(title: str, rows: tuple[str, ...]) -> QGroupBox:
    group = QGroupBox(title)
    layout = QVBoxLayout(group)
    for row in rows:
        label = QLabel(row)
        label.setWordWrap(True)
        layout.addWidget(label)
    return group
