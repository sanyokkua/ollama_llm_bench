"""Shared ``QAbstractTableModel`` boilerplate for every frozen-row table model in this
module (``01_MODULE_INVENTORY.md`` §5). A concrete subclass supplies only its row type and
a ``(row, column_index) -> str`` cell accessor; this base owns row/column counts, cell and
header lookup, and the atomic whole-model reset (story AC-3).
"""

from collections.abc import Callable
from typing import override

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)


class _FrozenRowTableModel[RowT](QAbstractTableModel):
    """Render an immutable collection of frozen row objects as a Qt table.

    Holds no backend Protocol and performs no I/O — every row is supplied by
    its caller and never mutated in place; a data change is always a full
    ``set_rows`` swap (``01_MODULE_INVENTORY.md`` §5).
    """

    def __init__(
        self,
        *,
        headers: tuple[str, ...],
        cell_value: Callable[[RowT, int], str],
        rows: tuple[RowT, ...],
    ) -> None:
        super().__init__()
        self._headers = headers
        self._cell_value = cell_value
        self._rows = rows

    @property
    def rows(self) -> tuple[RowT, ...]:
        """The table's current row collection, in display order."""
        return self._rows

    @override
    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008  # Qt virtual method
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    @override
    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008  # Qt virtual method
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._cell_value(self._rows[index.row()], index.column())

    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return self._headers[section]

    def set_rows(self, *, headers: tuple[str, ...], rows: tuple[RowT, ...]) -> None:
        """Atomically swap the table's headers and rows (story AC-3).

        Args:
            headers: The new column headers, in display order.
            rows: The new row collection; replaces the current one wholesale.
        """
        self.beginResetModel()
        self._headers = headers
        self._rows = rows
        self.endResetModel()
