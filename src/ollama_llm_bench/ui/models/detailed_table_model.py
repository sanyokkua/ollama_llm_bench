"""Qt table model for per-task detailed benchmark result data."""

from typing import Any, override

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

from ollama_llm_bench.backend.core.models import SummaryTableItem

_INVALID_INDEX: QModelIndex = QModelIndex()

_HEADERS: list[str] = [
    "MODEL",
    "TASK",
    "STATUS",
    "TIME (ms)",
    "TOKENS",
    "TOKENS/s",
    "SCORE",
    "COSINE",
    "LAYER",
    "REASON",
]


class DetailedTableModel(QAbstractTableModel):
    """Table model providing per-task benchmark results for a single run.

    Each row corresponds to one ``SummaryTableItem`` (model and task pair).
    Numeric columns expose raw float values via ``UserRole`` for proxy sorting.
    """

    NUMERIC_COLUMNS: frozenset[int] = frozenset({3, 4, 5, 6, 7})

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise with an empty item list."""
        super().__init__(parent)
        self._items: list[SummaryTableItem] = []

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX) -> int:
        """Return the number of result rows.

        Args:
            parent: Must be invalid for a flat table; returns 0 otherwise.

        Returns:
            Number of ``SummaryTableItem`` rows held.
        """
        if parent.isValid():
            return 0
        return len(self._items)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX) -> int:
        """Return the fixed column count (10).

        Args:
            parent: Must be invalid for a flat table; returns 0 otherwise.

        Returns:
            10 for a valid (non-parent) request.
        """
        if parent.isValid():
            return 0
        return len(_HEADERS)

    @override
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return column header text.

        Args:
            section: Column index.
            orientation: Only ``Horizontal`` is handled.
            role: Only ``DisplayRole`` returns a value.

        Returns:
            Column label string, or ``None`` for unhandled cases.
        """
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(_HEADERS)
        ):
            return _HEADERS[section]
        return None

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return cell data for the given role.

        Args:
            index: Cell location. Returns ``None`` when invalid.
            role: ``DisplayRole`` → formatted string; ``UserRole`` → raw numeric
                value for proxy sorting; ``TextAlignmentRole`` → alignment flags.

        Returns:
            Appropriate value for the role, or ``None`` when unhandled.
        """
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._items):
            return None

        item = self._items[row]

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_value(item, col)

        if role == Qt.ItemDataRole.UserRole:
            return self._user_role_value(item, col)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in self.NUMERIC_COLUMNS:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        return None

    def _display_value(self, item: SummaryTableItem, col: int) -> str | None:
        """Return the formatted display string for a cell.

        Args:
            item: Source data row.
            col: Column index.

        Returns:
            Formatted string or ``None`` for an unknown column.
        """
        match col:
            case 0:
                return item.model_name
            case 1:
                return item.task_id
            case 2:
                return item.task_status
            case 3:
                return f"{item.time_ms:.0f}"
            case 4:
                return str(item.tokens)
            case 5:
                return f"{item.tokens_per_second:.2f}"
            case 6:
                return f"{item.score:.2f}"
            case 7:
                if item.cosine_similarity is not None:
                    return f"{item.cosine_similarity:.2f}"
                return "—"
            case 8:
                return item.resolution_layer
            case 9:
                return item.score_reason
            case _:
                return None

    def _user_role_value(self, item: SummaryTableItem, col: int) -> Any:
        """Return the raw numeric value used by sort proxy models.

        Args:
            item: Source data row.
            col: Column index.

        Returns:
            Numeric or string value appropriate for sorting, or ``None``.
        """
        match col:
            case 0:
                return item.model_name
            case 1:
                return item.task_id
            case 2:
                return item.task_status
            case 3:
                return float(item.time_ms)
            case 4:
                return float(item.tokens)
            case 5:
                return item.tokens_per_second
            case 6:
                return item.score
            case 7:
                return item.cosine_similarity
            case 8:
                return item.resolution_layer
            case 9:
                return item.score_reason
            case _:
                return None

    def update_data(self, items: list[SummaryTableItem]) -> None:
        """Replace all rows with a new dataset and notify attached views.

        Args:
            items: New list of per-task result items to display.
        """
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()
