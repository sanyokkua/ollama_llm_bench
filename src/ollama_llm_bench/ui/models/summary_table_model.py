"""Qt table model for aggregated (average) benchmark summary data."""

from typing import Any, override

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt

from ollama_llm_bench.backend.core.models import AvgSummaryTableItem

_INVALID_INDEX: QModelIndex = QModelIndex()

_HEADERS: list[str] = [
    "MODEL",
    "AVG. TIME (s)",
    "AVG. TOKENS/s",
    "AVG. SCORE",
    "PASS%",
    "AVG. TTFT (ms)",
]


class SummaryTableModel(QAbstractTableModel):
    """Table model providing aggregated per-model benchmark metrics.

    Displays one row per model with averaged timing, throughput, score,
    pass rate, and TTFT columns. Supports numeric ``UserRole`` data for
    correct proxy-model sorting.
    """

    NUMERIC_COLUMNS: frozenset[int] = frozenset({1, 2, 3, 4, 5})

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise with an empty item list."""
        super().__init__(parent)
        self._items: list[AvgSummaryTableItem] = []

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX) -> int:
        """Return the number of model rows.

        Args:
            parent: Must be invalid for a flat table; returns 0 otherwise.

        Returns:
            Number of ``AvgSummaryTableItem`` rows held.
        """
        if parent.isValid():
            return 0
        return len(self._items)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _INVALID_INDEX) -> int:
        """Return the fixed column count (6).

        Args:
            parent: Must be invalid for a flat table; returns 0 otherwise.

        Returns:
            6 for a valid (non-parent) request.
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

    def _display_value(self, item: AvgSummaryTableItem, col: int) -> str | None:
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
                return f"{item.avg_time_ms / 1000:.2f}"
            case 2:
                return f"{item.avg_tokens_per_second:.2f}"
            case 3:
                return f"{item.avg_score:.2f}"
            case 4:
                return f"{item.pass_rate * 100:.1f}%"
            case 5:
                if item.avg_ttft_ms is not None:
                    return f"{item.avg_ttft_ms:.0f}"
                return "—"
            case _:
                return None

    def _user_role_value(self, item: AvgSummaryTableItem, col: int) -> Any:
        """Return the raw numeric value used by sort proxy models.

        Args:
            item: Source data row.
            col: Column index.

        Returns:
            Numeric value (or ``str`` for model name), or ``None`` for unknown column.
        """
        match col:
            case 0:
                return item.model_name
            case 1:
                return item.avg_time_ms / 1000
            case 2:
                return item.avg_tokens_per_second
            case 3:
                return item.avg_score
            case 4:
                return item.pass_rate * 100
            case 5:
                return item.avg_ttft_ms
            case _:
                return None

    def update_data(self, items: list[AvgSummaryTableItem]) -> None:
        """Replace all rows with a new dataset and notify attached views.

        Args:
            items: New list of aggregated model metrics to display.
        """
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()
