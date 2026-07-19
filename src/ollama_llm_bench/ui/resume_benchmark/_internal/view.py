"""``ResumeBenchmarkView`` -- the passive Resume run table widget (STORY-056).

A passive ``QWidget``: renders the search box, the run table, and the
caption; every user action is forwarded to its controller. Imports no
Gateway, no reactive store, and no ``ollama_llm_bench.backend.*`` symbol
(the passive-View rule, enforced by an architecture test).
"""

from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QTimer,
)
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
from ollama_llm_bench.ui.resume_benchmark._internal.row_actions_delegate import (
    RowActionsDelegate,
)
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import COL_STATUS, COL_TASKS
from ollama_llm_bench.ui.resume_benchmark._internal.status_badge_delegate import (
    StatusBadgeDelegate,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["ResumeBenchmarkView"]

_SEARCH_DEBOUNCE_MS = 150
_CAPTION_TEXT = "Right-click a row, use the pencil to rename, or ⋯ for more actions."


class ResumeBenchmarkView(QWidget):
    """Passive Resume run table: search box, table view, caption."""

    def __init__(
        self,
        *,
        controller: ResumeBenchmarkController,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        super().__init__()
        self.setObjectName("resume_benchmark.view")
        self._controller = controller
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._on_debounced_search)
        self._row_actions_delegate = RowActionsDelegate(
            theme_manager=theme_manager, platform_kind=platform_kind
        )
        self._status_badge_delegate = StatusBadgeDelegate(
            theme_manager=theme_manager, platform_kind=platform_kind
        )
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
        self._table_view.setItemDelegateForColumn(COL_STATUS, self._status_badge_delegate)
        self._table_view.setItemDelegateForColumn(COL_TASKS, self._row_actions_delegate)
        self._table_view.setMouseTracking(True)
        self._table_view.entered.connect(self._on_row_entered)
        self._table_view.viewport().installEventFilter(self)
        self._row_actions_delegate.pencil_clicked.connect(self._on_pencil_clicked)
        self._row_actions_delegate.more_clicked.connect(self._on_more_clicked)
        self._controller.table_model.modelReset.connect(self._on_model_reset)
        layout.addWidget(self._table_view)

        caption = QLabel(_CAPTION_TEXT)
        caption.setObjectName("resume_benchmark.caption")
        caption.setProperty("role", "muted-caption")
        layout.addWidget(caption)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Clear the hovered row's icons when the pointer leaves the table viewport."""
        if watched is self._table_view.viewport() and event.type() == QEvent.Type.Leave:
            self._row_actions_delegate.set_hovered_row(None)
            self._table_view.viewport().update()
        return super().eventFilter(watched, event)

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

    def _on_row_entered(self, index: QModelIndex) -> None:
        self._row_actions_delegate.set_hovered_row(index.row())
        self._table_view.viewport().update()

    def _on_pencil_clicked(self, view_row: int) -> None:
        self._controller.on_pencil_clicked(view_row)

    def _on_more_clicked(self, view_row: int) -> None:
        index = self._controller.table_model.index(view_row, COL_TASKS)
        rect = self._table_view.visualRect(index)
        global_pos = self._table_view.viewport().mapToGlobal(rect.center())
        self._controller.on_more_clicked(view_row, global_pos)

    def _on_model_reset(self) -> None:
        """Restore the QTableView's visual selection after any model reset.

        ``set_rows``/``set_search_term``/``set_sort`` all call
        ``beginResetModel``/``endResetModel``, which clears Qt's own
        selection model. If the controller's currently-tracked selected run
        is still visible, re-select its row here, blocked from re-emitting
        ``selectionChanged`` (the selection is being restored, not changed
        by the user) -- the controller's own filtered-out-selection path
        (``_clear_selection_if_filtered_out``) handles the case where the
        row is gone.
        """
        run_id = self._controller.current_selected_run_id()
        if run_id is None:
            return
        view_row = self._controller.table_model.find_view_row_for_run_id(run_id)
        if view_row is None:
            return
        index = self._controller.table_model.index(view_row, 0)
        selection_model = self._table_view.selectionModel()
        selection_model.blockSignals(True)  # noqa: FBT003  # Qt's own blockSignals(bool) API
        try:
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            self._table_view.setCurrentIndex(index)
        finally:
            selection_model.blockSignals(False)  # noqa: FBT003  # Qt's own blockSignals(bool) API
