"""RetrySelectionDialog — per-task selector for cloning a partial run."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.backend.core.models import BenchmarkResult, BenchmarkResultStatus

_logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES: frozenset[BenchmarkResultStatus] = frozenset(
    {
        BenchmarkResultStatus.NOT_COMPLETED,
        BenchmarkResultStatus.WAITING_FOR_JUDGE,
        BenchmarkResultStatus.FAILED,
    }
)


class RetrySelectionDialog(QDialog):
    """Dialog for selecting which failed or incomplete results to include in a retry clone.

    All retryable results (NOT_COMPLETED, WAITING_FOR_JUDGE, FAILED) are shown as
    checked checkboxes; cleanly completed results are omitted.  On acceptance,
    ``selected_result_ids`` is populated with the IDs of all checked results.
    """

    def __init__(
        self,
        *,
        run_id: int,
        results: list[BenchmarkResult],
        parent: QWidget | None = None,
    ) -> None:
        """Construct the dialog.

        Args:
            run_id: ID of the run whose results are being retried.
            results: All results belonging to the run.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.selected_result_ids: list[int] = []
        self._checkboxes: list[tuple[QCheckBox, int]] = []

        self.setWindowTitle(f"Select Tasks to Retry — Run #{run_id}")
        self.setMinimumWidth(480)

        self._build_ui(results)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, results: list[BenchmarkResult]) -> None:
        retryable = [r for r in results if r.status in _RETRYABLE_STATUSES]

        scroll_contents = QWidget()
        inner_layout = QVBoxLayout(scroll_contents)
        inner_layout.setContentsMargins(8, 8, 8, 8)
        inner_layout.setSpacing(4)

        if not retryable:
            inner_layout.addWidget(QLabel("No failed or incomplete results to retry."))
        else:
            for result in retryable:
                label = f"{result.provider_id} / {result.model_name} / {result.task_id}"
                cb = QCheckBox(label)
                cb.setChecked(True)
                self._checkboxes.append((cb, result.result_id))
                inner_layout.addWidget(cb)

        inner_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(scroll_contents)
        scroll.setWidgetResizable(True)

        btn_box = QDialogButtonBox()
        retry_btn = btn_box.addButton("Retry Selected", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        if retry_btn is not None:
            retry_btn.setProperty("role", "primary")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.addWidget(scroll, stretch=1)
        root.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Accept override
    # ------------------------------------------------------------------

    def accept(self) -> None:
        """Populate selected_result_ids from checked boxes, then close."""
        self.selected_result_ids = [rid for cb, rid in self._checkboxes if cb.isChecked()]
        super().accept()
