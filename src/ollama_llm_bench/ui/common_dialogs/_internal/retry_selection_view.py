"""``RetrySelectionDialog`` -- the checkable retry-row picker (STORY-057-AC-5,6,7).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/retry_selection_dialog.md``
§5 (filter), §6 (check semantics), §8 (bulk toggles), §9 (selection summary), §11
(button behaviour), §13 (confirm effects, DD-66).
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.ui.common_dialogs._internal.retry_selection_select import visible_rows
from ollama_llm_bench.ui.common_dialogs.models import RetryFilterOption, RetrySelectionViewModel
from ollama_llm_bench.ui.common_dialogs.protocols import RetrySelectionGateway

if TYPE_CHECKING:
    from ollama_llm_bench.backend.domain import ResultId

__all__: list[str] = ["RetrySelectionDialog"]

logger = structlog.get_logger(__name__)

_FILTER_LABELS: dict[RetryFilterOption, str] = {
    RetryFilterOption.ALL: "All",
    RetryFilterOption.ONLY_FAILED: "Only failed",
    RetryFilterOption.ONLY_INCOMPLETE: "Only incomplete",
    RetryFilterOption.ONLY_COMPLETED: "Only completed",
}
_COL_TASK = 0
_COL_STATUS = 1
_COL_REASON = 2


class RetrySelectionDialog(QDialog):
    """The Retry Selection dialog: filterable checkable result table, Retry Selected."""

    def __init__(
        self,
        *,
        gateway: RetrySelectionGateway,
        view_model: RetrySelectionViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.retry_selection")
        self.setWindowTitle("Retry Selection")
        self._gateway = gateway
        self._run_id = view_model.run_id
        self._rows = view_model.rows
        self._checked_result_ids: set[ResultId] = {
            row.result_id for row in view_model.rows if row.is_checked
        }
        self._current_filter = RetryFilterOption.ONLY_FAILED
        self._row_items: dict[ResultId, QTableWidgetItem] = {}
        self._build_ui()
        logger.debug("retry_selection_dialog_constructed", run_id=view_model.run_id)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("common_dialogs.retry_selection.filter")
        for option in RetryFilterOption:
            self.filter_combo.addItem(_FILTER_LABELS[option], option)
        self.filter_combo.setCurrentIndex(
            list(RetryFilterOption).index(RetryFilterOption.ONLY_FAILED)
        )
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.filter_combo)
        toolbar.addStretch()
        check_all = QPushButton("Check all visible")
        check_all.setProperty("role", "outlined-muted-button")
        check_all.clicked.connect(lambda: self._bulk_toggle(checked=True))
        uncheck_all = QPushButton("Uncheck all visible")
        uncheck_all.setProperty("role", "outlined-muted-button")
        uncheck_all.clicked.connect(lambda: self._bulk_toggle(checked=False))
        toolbar.addWidget(check_all)
        toolbar.addWidget(uncheck_all)
        outer.addLayout(toolbar)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("common_dialogs.retry_selection.table")
        self.table.setHorizontalHeaderLabels(["Task", "Status", "Reason"])
        self.table.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self.table)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("common_dialogs.retry_selection.summary")
        outer.addWidget(self.summary_label)

        outer.addLayout(self._build_footer())
        self._rebuild_visible_rows()

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.setProperty("role", "outlined-muted-button")
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)
        self.retry_button = QPushButton("Retry Selected")
        self.retry_button.setObjectName("common_dialogs.retry_selection.retry_button")
        self.retry_button.setProperty("role", "primary-button")
        self.retry_button.setDefault(True)
        self.retry_button.clicked.connect(self._on_retry_clicked)
        footer.addWidget(self.retry_button)
        return footer

    def _rebuild_visible_rows(self) -> None:
        shown = visible_rows(self._rows, filter_option=self._current_filter)
        self.table.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        self.table.setRowCount(len(shown))
        self._row_items.clear()
        for row_index, row in enumerate(shown):
            task_item = QTableWidgetItem(row.task_id)
            task_item.setFlags(task_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            task_item.setCheckState(
                Qt.CheckState.Checked
                if row.result_id in self._checked_result_ids
                else Qt.CheckState.Unchecked
            )
            task_item.setData(Qt.ItemDataRole.UserRole, row.result_id)
            self.table.setItem(row_index, _COL_TASK, task_item)
            self.table.setItem(row_index, _COL_STATUS, QTableWidgetItem(row.status_chip_label))
            self.table.setItem(row_index, _COL_REASON, QTableWidgetItem(row.reason_text))
            self._row_items[row.result_id] = task_item
        self.table.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        self._update_summary_and_button()

    def _on_filter_changed(self, _index: int) -> None:
        self._current_filter = self.filter_combo.currentData()
        self._rebuild_visible_rows()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != _COL_TASK:
            return
        result_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_result_ids.add(result_id)
        else:
            self._checked_result_ids.discard(result_id)
        self._update_summary_and_button()

    def _bulk_toggle(self, *, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for item in self._row_items.values():
            item.setCheckState(state)

    def _update_summary_and_button(self) -> None:
        selected = len(self._checked_result_ids)
        not_selected_retryable = sum(
            1
            for row in self._rows
            if row.result_id not in self._checked_result_ids
            and row.filter_group
            in (RetryFilterOption.ONLY_FAILED, RetryFilterOption.ONLY_INCOMPLETE)
        )
        completed_untouched = sum(
            1
            for row in self._rows
            if row.filter_group is RetryFilterOption.ONLY_COMPLETED
            and row.result_id not in self._checked_result_ids
        )
        self.summary_label.setText(
            f"{selected} selected for retry  ·  {not_selected_retryable} not selected  ·  "
            f"{completed_untouched} completed rows untouched"
        )
        self.retry_button.setEnabled(selected > 0)

    def _on_retry_clicked(self) -> None:
        result_ids = tuple(self._checked_result_ids)
        logger.debug(
            "retry_selection_dialog_retry_clicked",
            run_id=self._run_id,
            checked_count=len(result_ids),
        )
        self._gateway.reset_results_for_retry(result_ids)
        self._gateway.resume_run(self._run_id)
        self.accept()
