"""``ResumeBenchmarkView`` -- the passive Resume run table widget (STORY-056).

A passive ``QWidget``: renders the search box, the run table, and the
caption; every user action is forwarded to its controller. Imports no
Gateway, no reactive store, and no ``ollama_llm_bench.backend.*`` symbol
(the passive-View rule, enforced by an architecture test).
"""

from PySide6.QtCore import QItemSelection, QPoint, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.resume_benchmark._internal.controller import ResumeBenchmarkController

__all__: list[str] = ["ResumeBenchmarkView"]

_SEARCH_DEBOUNCE_MS = 150
_CAPTION_TEXT = "Right-click a row or use ⋯ for actions."


class ResumeBenchmarkView(QWidget):
    """Passive Resume run table: search box, table view, caption."""

    def __init__(self, *, controller: ResumeBenchmarkController) -> None:
        super().__init__()
        self.setObjectName("resume_benchmark.view")
        self._controller = controller
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._on_debounced_search)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("resume_benchmark.search")
        self._search_edit.setPlaceholderText("Search by name or mode…")
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self._search_edit)

        self._table_view = QTableView()
        self._table_view.setObjectName("resume_benchmark.table")
        self._table_view.setModel(self._controller.table_model)
        self._table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_view.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table_view.setContextMenuPolicy(
            self._table_view.contextMenuPolicy().CustomContextMenu
        )
        self._table_view.customContextMenuRequested.connect(self._on_context_menu_requested)
        self._table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table_view)

        caption = QLabel(_CAPTION_TEXT)
        caption.setObjectName("resume_benchmark.caption")
        caption.setProperty("role", "muted-caption")
        layout.addWidget(caption)

    def _on_search_text_changed(self, _text: str) -> None:
        self._debounce_timer.start()

    def _on_debounced_search(self) -> None:
        self._controller.on_search_term_changed(self._search_edit.text())

    def _on_header_clicked(self, column: int) -> None:
        self._controller.on_sort_header_clicked(column)

    def _on_context_menu_requested(self, position: QPoint) -> None:
        index = self._table_view.indexAt(position)
        if not index.isValid():
            return
        global_pos = self._table_view.viewport().mapToGlobal(position)
        self._controller.on_context_menu_requested(index.row(), global_pos)

    def _on_selection_changed(self, _selected: QItemSelection, _deselected: QItemSelection) -> None:
        selected_rows = self._table_view.selectionModel().selectedRows()
        if not selected_rows:
            self._controller.on_row_selected(None)
            return
        row = self._controller.table_model.visible_row(selected_rows[0].row())
        self._controller.on_row_selected(row.run_id)
