"""``ProvidersTabWidget`` -- the passive Providers tab: Add Provider button, the
provider table, and the embedding section (``description.md`` §3).

A passive ``QWidget``: renders the table model it is given and emits Qt signals
on user interaction; imports no Gateway, no reactive store, and no
``ollama_llm_bench.backend.*`` symbol beyond the DTO-only pieces the delegate
modules themselves already isolate (the passive-View rule).
"""

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QObject, QPoint, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.embedding_section import (
    EmbeddingSectionWidget,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.health_auth_delegate import (
    HealthAuthDelegate,
)
from ollama_llm_bench.ui.settings_dialog._internal.providers_tab.row_actions_delegate import (
    COL_ENABLED,
    RowActionsDelegate,
)
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager

__all__: list[str] = ["ProvidersTabWidget"]


class ProvidersTabWidget(QWidget):
    """Passive Providers tab: Add Provider button, provider table, embedding section."""

    add_clicked = Signal()
    test_clicked = Signal(int)
    edit_clicked = Signal(int)
    enabled_toggled = Signal(int)
    more_clicked = Signal(int, QPoint)

    def __init__(
        self,
        *,
        embedding_section: EmbeddingSectionWidget,
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
    ) -> None:
        super().__init__()
        self.setObjectName("settings_dialog.providers_tab")
        self._embedding_section = embedding_section
        self._health_auth_delegate = HealthAuthDelegate(
            theme_manager=theme_manager, platform_kind=platform_kind
        )
        self._row_actions_delegate = RowActionsDelegate(
            theme_manager=theme_manager, platform_kind=platform_kind
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        header_row.addStretch()
        self._add_button = QPushButton("Add Provider")
        self._add_button.setObjectName("settings_dialog.providers_tab.add_button")
        self._add_button.setAccessibleName("Add Provider")
        self._add_button.setProperty("role", "primary-button")
        self._add_button.clicked.connect(self.add_clicked)
        header_row.addWidget(self._add_button)
        layout.addLayout(header_row)

        self._table_view = QTableView()
        self._table_view.setObjectName("settings_dialog.providers_tab.table")
        self._table_view.setAccessibleName("Providers table")
        self._table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table_view.setItemDelegate(self._health_auth_delegate)
        self._table_view.setItemDelegateForColumn(COL_ENABLED, self._row_actions_delegate)
        self._table_view.setMouseTracking(True)
        self._table_view.entered.connect(self._on_row_entered)
        self._table_view.viewport().installEventFilter(self)
        self._row_actions_delegate.enabled_toggled.connect(self.enabled_toggled)
        self._row_actions_delegate.test_clicked.connect(self.test_clicked)
        self._row_actions_delegate.more_clicked.connect(self._on_more_clicked)
        self._table_view.doubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table_view, 1)

        layout.addWidget(self._embedding_section)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Clear the hovered row's icons when the pointer leaves the table viewport."""
        if watched is self._table_view.viewport() and event.type() == QEvent.Type.Leave:
            self._row_actions_delegate.set_hovered_row(None)
            self._table_view.viewport().update()
        return super().eventFilter(watched, event)

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if index.isValid():
            self.edit_clicked.emit(index.row())

    def set_table_model(self, model: QAbstractTableModel) -> None:
        """Install a freshly built provider table model (STORY-066-AC-1)."""
        self._table_view.setModel(model)

    @property
    def embedding_section(self) -> EmbeddingSectionWidget:
        """The mounted embedding-selection section widget."""
        return self._embedding_section

    def _on_row_entered(self, index: QModelIndex) -> None:
        self._row_actions_delegate.set_hovered_row(index.row())
        self._table_view.viewport().update()

    def _on_more_clicked(self, view_row: int) -> None:
        index_column = COL_ENABLED
        index = self._table_view.model().index(view_row, index_column)
        rect = self._table_view.visualRect(index)
        global_pos = self._table_view.viewport().mapToGlobal(rect.center())
        self.more_clicked.emit(view_row, global_pos)
