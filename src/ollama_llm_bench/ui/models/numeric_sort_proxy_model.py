"""Proxy model that sorts numeric columns by value and supports column-level filtering."""

from typing import Any, override

from PySide6.QtCore import QModelIndex, QObject, QPersistentModelIndex, QSortFilterProxyModel, Qt


class NumericSortProxyModel(QSortFilterProxyModel):
    """Sort/filter proxy that compares numeric columns by their ``UserRole`` float value.

    String columns fall back to the default ``QSortFilterProxyModel`` comparison.
    ``None`` values always sort to the bottom when sorting ascending.

    Column filters may be set as either:

    - ``set[Any]`` — exact membership check against the ``UserRole`` value.
    - ``tuple[float, float]`` — inclusive range check ``(lo, hi)`` on the float cast
      of the ``UserRole`` value.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise with no active column filters."""
        super().__init__(parent)
        self._column_filters: dict[int, set[Any] | tuple[float, float]] = {}

    @override
    def lessThan(self, left: QModelIndex | QPersistentModelIndex, right: QModelIndex | QPersistentModelIndex) -> bool:
        """Compare two cells for sorting using their ``UserRole`` value.

        ``None`` values are treated as greater than any real value so they
        sink to the bottom of ascending sorts.

        Args:
            left: Source index for the left operand.
            right: Source index for the right operand.

        Returns:
            ``True`` if ``left`` should appear before ``right``.
        """
        a = left.data(Qt.ItemDataRole.UserRole)
        b = right.data(Qt.ItemDataRole.UserRole)

        if a is None and b is None:
            return super().lessThan(left, right)
        if a is None:
            return False
        if b is None:
            return True

        try:
            return float(a) < float(b)
        except (TypeError, ValueError):
            return super().lessThan(left, right)

    @override
    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex) -> bool:
        """Determine whether a source row passes all active column filters.

        Args:
            source_row: Row index in the source model.
            source_parent: Parent index (unused for flat models).

        Returns:
            ``True`` if the row satisfies every active filter.
        """
        source = self.sourceModel()
        if source is None:
            return True

        for col, filter_val in self._column_filters.items():
            index = source.index(source_row, col, source_parent)
            raw = index.data(Qt.ItemDataRole.UserRole)

            if isinstance(filter_val, set):
                if raw not in filter_val:
                    return False
            elif isinstance(filter_val, tuple):
                lo, hi = filter_val
                try:
                    v = float(raw)
                    if not (lo <= v <= hi):
                        return False
                except (TypeError, ValueError):
                    return False

        return True

    def set_column_filter(self, col: int, filter_val: set[Any] | tuple[float, float]) -> None:
        """Set or replace the filter for a specific column.

        Args:
            col: Column index to filter.
            filter_val: Either a ``set`` of accepted ``UserRole`` values, or a
                ``(lo, hi)`` float range tuple.
        """
        self._column_filters[col] = filter_val
        self.invalidateRowsFilter()

    def clear_column_filter(self, col: int) -> None:
        """Remove the filter for a specific column.

        Args:
            col: Column index whose filter should be cleared.
        """
        self._column_filters.pop(col, None)
        self.invalidateRowsFilter()

    def clear_all_filters(self) -> None:
        """Remove all active column filters and refresh the visible rows."""
        self._column_filters.clear()
        self.invalidateRowsFilter()

    def has_active_filter(self, col: int) -> bool:
        """Return whether a specific column currently has an active filter.

        Args:
            col: Column index to check.

        Returns:
            ``True`` if a filter is registered for the column.
        """
        return col in self._column_filters

    def active_filter_columns(self) -> set[int]:
        """Return the set of column indices that currently carry an active filter.

        Returns:
            Set of column indices with registered filters.
        """
        return set(self._column_filters.keys())
