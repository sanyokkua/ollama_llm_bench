"""Non-modal dialog for displaying a result table in a detached window."""

import logging
from typing import override

from PySide6.QtCore import QByteArray, QSettings, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.models.numeric_sort_proxy_model import NumericSortProxyModel

logger = logging.getLogger(__name__)


class TableDetachDialog(QDialog):
    """Non-modal dialog that hosts a result table in a separate, resizable window.

    Geometry is persisted per table name via ``QSettings`` so the window
    reopens at the same size and position the user last left it.
    """

    closed: Signal = Signal()

    def __init__(
        self,
        *,
        proxy_model: NumericSortProxyModel,
        run_name: str,
        table_name: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the detached table dialog.

        Args:
            proxy_model: The proxy model whose data should be displayed.
            run_name: Human-readable benchmark run name used in the window title.
            table_name: Table identifier used in the window title and settings key.
            parent: Optional parent widget.
        """
        super().__init__(parent, Qt.WindowType.Window)

        self._table_name: str = table_name
        self.setWindowTitle(f"{run_name} — {table_name}")

        # Table view
        self._table_view: QTableView = QTableView()
        self._table_view.setModel(proxy_model)
        self._table_view.setSortingEnabled(True)
        self._table_view.horizontalHeader().setSortIndicatorShown(True)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._table_view)

        # Default size
        self.resize(1200, 700)

        # Restore persisted geometry if available
        settings = QSettings()
        key = f"ui/detached_{self._table_name.lower()}_geometry"
        raw = settings.value(key, QByteArray())
        data = raw if isinstance(raw, QByteArray) else QByteArray()
        if not data.isEmpty():
            self.restoreGeometry(data)

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Persist window geometry and emit the closed signal.

        Args:
            event: The close event from Qt.
        """
        settings = QSettings()
        key = f"ui/detached_{self._table_name.lower()}_geometry"
        settings.setValue(key, self.saveGeometry())

        self.closed.emit()
        super().closeEvent(event)
