"""Tasks pane -- per-file task list, per-task badges, add/duplicate/remove/reorder,
multi-select (STORY-068; ``description.md`` §3.4).

Reorder is offered via the Move Up / Move Down footer controls only this story --
mouse drag-to-reorder is deferred (see the story's Notes). Remove uses a plain
``QMessageBox`` confirmation (a standard Qt built-in, not a bespoke confirmation
dialog module) since the removal is destructive and irreversible in-session.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.ui.task_editor.models import TaskRowViewModel, ValidationState

__all__: list[str] = ["TasksPaneWidget"]

logger = structlog.get_logger(__name__)

_BADGE_BY_STATE: dict[ValidationState, str] = {
    ValidationState.CLEAN: "[clean]",
    ValidationState.INFO: "[clean]",
    ValidationState.WARNING: "[warning]",
    ValidationState.ERROR: "[error]",
}


class TasksPaneWidget(QWidget):
    """Passive per-file task list; forwards every user action via signals."""

    row_selected = Signal(int)
    add_task_clicked = Signal()
    duplicate_task_clicked = Signal(int)
    remove_tasks_clicked = Signal(object)
    move_up_clicked = Signal(int)
    move_down_clicked = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("task_editor.tasks_pane")
        self._rows: tuple[TaskRowViewModel, ...] = ()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setObjectName("task_editor.tasks_pane.list")
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.currentRowChanged.connect(self._on_current_row_changed)
        layout.addWidget(self._list)

        footer = QHBoxLayout()
        self._add_button = QPushButton("Add Task")
        self._add_button.setObjectName("task_editor.tasks_pane.add")
        self._add_button.clicked.connect(self.add_task_clicked.emit)
        footer.addWidget(self._add_button)

        self._duplicate_button = QPushButton("Duplicate")
        self._duplicate_button.setObjectName("task_editor.tasks_pane.duplicate")
        self._duplicate_button.clicked.connect(self._on_duplicate_clicked)
        footer.addWidget(self._duplicate_button)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setObjectName("task_editor.tasks_pane.remove")
        self._remove_button.clicked.connect(self._on_remove_clicked)
        footer.addWidget(self._remove_button)

        self._move_up_button = QPushButton("Move Up")
        self._move_up_button.setObjectName("task_editor.tasks_pane.move_up")
        self._move_up_button.clicked.connect(self._on_move_up_clicked)
        footer.addWidget(self._move_up_button)

        self._move_down_button = QPushButton("Move Down")
        self._move_down_button.setObjectName("task_editor.tasks_pane.move_down")
        self._move_down_button.clicked.connect(self._on_move_down_clicked)
        footer.addWidget(self._move_down_button)
        layout.addLayout(footer)

    def apply(self, rows: tuple[TaskRowViewModel, ...]) -> None:
        """Push the active file's current task-row list (§3.4)."""
        self._rows = rows
        self._list.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            self._list.clear()
            selected_index: int | None = None
            for index, row in enumerate(rows):
                item = QListWidgetItem(f"{_BADGE_BY_STATE[row.validation_state]} {row.task_id}")
                self._list.addItem(item)
                if row.is_selected:
                    item.setSelected(True)
                    selected_index = index
            if selected_index is not None:
                self._list.setCurrentRow(selected_index)
        finally:
            self._list.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API

    def _on_current_row_changed(self, row: int) -> None:
        if row < 0:
            return
        self.row_selected.emit(row)

    def _selected_indices(self) -> tuple[int, ...]:
        return tuple(sorted(index.row() for index in self._list.selectedIndexes()))

    def _on_duplicate_clicked(self) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        self.duplicate_task_clicked.emit(indices[0])

    def _on_remove_clicked(self) -> None:
        indices = self._selected_indices()
        if not indices:
            return
        logger.debug("task_editor_remove_tasks_requested", count=len(indices))
        confirmed = QMessageBox.question(
            self,
            "Remove task(s)?",
            f"Remove {len(indices)} task(s)? This cannot be undone.",
        )
        if confirmed == QMessageBox.StandardButton.Yes:
            self.remove_tasks_clicked.emit(indices)

    def _on_move_up_clicked(self) -> None:
        indices = self._selected_indices()
        if len(indices) == 1:
            self.move_up_clicked.emit(indices[0])

    def _on_move_down_clicked(self) -> None:
        indices = self._selected_indices()
        if len(indices) == 1:
            self.move_down_clicked.emit(indices[0])
