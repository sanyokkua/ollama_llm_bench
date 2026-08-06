"""``RunTableModel`` -- the virtualised, sortable, searchable run table (STORY-056-AC-1).

Source of truth: ``docs/v3_specification/03_Resume_Benchmark_Widget/description.md``
§3.3. A bespoke ``QAbstractTableModel`` (not ``adapters.qt_table_models``'s
``_FrozenRowTableModel`` -- that base carries no sort/filter state) exposing
``set_rows``/``set_search_term``/``set_sort`` and view-row lookups the
controller uses to map a selected view row back to a ``run_id``.
"""

from typing import override

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from ollama_llm_bench.backend.domain import RunId
from ollama_llm_bench.ui.resume_benchmark._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.resume_benchmark.models import RunRow
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = [
    "COL_MODE",
    "COL_NAME",
    "COL_STARTED",
    "COL_STATUS",
    "COL_TASKS",
    "RunTableModel",
]

COL_NAME = 0
COL_MODE = 1
COL_STARTED = 2
COL_STATUS = 3
COL_TASKS = 4
_HEADERS: tuple[str, ...] = ("Run name", "Mode", "Started", "Status", "Tasks")


def _tasks_ratio(row: RunRow) -> float:
    return row.tasks_completed / row.tasks_total if row.tasks_total else 0.0


_SORT_KEY_FNS: dict[int, object] = {
    COL_NAME: lambda r: r.effective_name.lower(),
    COL_MODE: lambda r: r.mode_label.lower(),
    COL_STARTED: lambda r: r.started_at_sort_key,
    COL_STATUS: lambda r: r.status_badge_label,
    COL_TASKS: _tasks_ratio,
}


class RunTableModel(QAbstractTableModel):
    """Virtualised run table: search + sort over ``RunRow`` tuples (STORY-056-AC-1)."""

    def __init__(
        self,
        *,
        rows: tuple[RunRow, ...] = (),
        theme_manager: ThemeManager | None = None,
        platform_kind: PlatformKind = PlatformKind.UNKNOWN,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._all_rows: tuple[RunRow, ...] = rows
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._search_term = ""
        self._sort_column = COL_STARTED
        self._sort_descending = True
        self._visible_rows: tuple[RunRow, ...] = ()
        self._recompute()

    def set_rows(self, rows: tuple[RunRow, ...]) -> None:
        """Replace the backing data, re-applying the current search/sort."""
        self.beginResetModel()
        self._all_rows = rows
        self._recompute()
        self.endResetModel()

    def set_search_term(self, term: str) -> None:
        """Re-filter the visible rows by ``term`` (name-or-mode substring)."""
        self.beginResetModel()
        self._search_term = term
        self._recompute()
        self.endResetModel()

    def set_sort(self, column: int, *, descending: bool) -> None:
        """Re-sort the visible rows by ``column`` in the given direction."""
        self.beginResetModel()
        self._sort_column = column
        self._sort_descending = descending
        self._recompute()
        self.endResetModel()

    @property
    def sort_column(self) -> int:
        """The currently active sort column index."""
        return self._sort_column

    @property
    def sort_descending(self) -> bool:
        """Whether the currently active sort direction is descending."""
        return self._sort_descending

    def visible_row(self, index: int) -> RunRow:
        """Return the filtered+sorted row at view row ``index``."""
        return self._visible_rows[index]

    def find_view_row_for_run_id(self, run_id: RunId) -> int | None:
        """Return the view row index currently showing ``run_id``, or ``None``."""
        for i, row in enumerate(self._visible_rows):
            if row.run_id == run_id:
                return i
        return None

    def _recompute(self) -> None:
        term = self._search_term.lower()
        filtered = [
            r
            for r in self._all_rows
            if term in r.effective_name.lower() or term in r.mode_label.lower()
        ]
        key_fn = _SORT_KEY_FNS[self._sort_column]
        filtered.sort(key=key_fn, reverse=self._sort_descending)  # type: ignore[arg-type]  # heterogeneous per-column key callables, each individually well-typed
        self._visible_rows = tuple(filtered)

    @override
    def rowCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008  # QModelIndex() is Qt's stateless "no parent" sentinel value, not a mutable default — safe to construct fresh each call
    ) -> int:
        if parent.isValid():
            return 0
        return len(self._visible_rows)

    @override
    def columnCount(
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),  # noqa: B008  # QModelIndex() is Qt's stateless "no parent" sentinel value, not a mutable default — safe to construct fresh each call
    ) -> int:
        if parent.isValid():
            return 0
        return len(_HEADERS)

    @override
    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None
        row = self._visible_rows[index.row()]
        if role == Qt.ItemDataRole.UserRole and index.column() == COL_STATUS:
            return row.status_badge_status
        if role == Qt.ItemDataRole.AccessibleTextRole and index.column() == COL_TASKS:
            return "Rename run"
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            row.effective_name,
            row.mode_label,
            row.started_at_display,
            row.status_badge_label,
            f"{row.tasks_completed}/{row.tasks_total}",
        )
        return values[index.column()]

    @override
    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation != Qt.Orientation.Horizontal:
            return None
        is_active_sort_column = section == self._sort_column
        if role == Qt.ItemDataRole.DisplayRole:
            if is_active_sort_column:
                caret = "▼" if self._sort_descending else "▲"
                return f"{_HEADERS[section]} {caret}"
            return _HEADERS[section]
        if (
            role == Qt.ItemDataRole.ForegroundRole
            and is_active_sort_column
            and self._theme_manager is not None
        ):
            tokens = resolve_theme_tokens(
                theme_manager=self._theme_manager, platform_kind=self._platform_kind
            )
            return QColor(resolve_color(tokens, "primary.base"))
        return None
