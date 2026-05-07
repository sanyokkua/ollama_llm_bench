"""Per-column value-set filter popup for result table views."""

import contextlib
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.models.numeric_sort_proxy_model import NumericSortProxyModel

logger = logging.getLogger(__name__)

_DISCRETE_THRESHOLD: int = 100  # if distinct count > this, show range filter instead


class ValueSetFilterDialog(QDialog):
    """Per-column filter dialog for result table views.

    Displays a discrete value checklist for columns with few distinct values, or
    a numeric range selector for columns with many distinct values.
    """

    def __init__(
        self,
        col_index: int,
        proxy: NumericSortProxyModel,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise and build the appropriate filter UI for the given column.

        Args:
            col_index: Index of the column to filter.
            proxy: The proxy model that owns the column filter state.
            parent: Optional parent widget for dialog centering.
        """
        super().__init__(parent)
        self._col_index: int = col_index
        self._proxy: NumericSortProxyModel = proxy

        self.setWindowTitle(f"Filter column {col_index}")

        # Collect distinct UserRole values from source model
        source = proxy.sourceModel()
        values: dict[Any, int] = {}
        for row in range(source.rowCount()):
            idx = source.index(row, col_index)
            raw = idx.data(Qt.ItemDataRole.UserRole)
            values[raw] = values.get(raw, 0) + 1

        self._all_values: dict[Any, int] = values
        self._is_range: bool = len(values) > _DISCRETE_THRESHOLD

        if self._is_range:
            self._build_range_ui()
        else:
            self._build_discrete_ui()

    # ------------------------------------------------------------------
    # Private — UI builders
    # ------------------------------------------------------------------

    def _build_discrete_ui(self) -> None:
        """Construct the checklist-based filter UI for low-cardinality columns."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Search box
        self._search_box: QLineEdit = QLineEdit()
        self._search_box.setPlaceholderText("Search values…")
        layout.addWidget(self._search_box)

        # List widget
        self._list_widget: QListWidget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        # Determine currently active filter (if any)
        active_filter = self._proxy._column_filters.get(self._col_index)
        active_set: set[Any] | None = active_filter if isinstance(active_filter, set) else None

        for value, count in sorted(self._all_values.items(), key=lambda kv: str(kv[0])):
            item = QListWidgetItem(f"{value} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if active_set is None or value in active_set:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self._list_widget.addItem(item)

        layout.addWidget(self._list_widget)

        # Button row: Select All / Clear / Invert
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_select_all = QPushButton("Select All")
        btn_clear = QPushButton("Clear")
        btn_invert = QPushButton("Invert")
        btn_row.addWidget(btn_select_all)
        btn_row.addWidget(btn_clear)
        btn_row.addWidget(btn_invert)
        layout.addLayout(btn_row)

        # Ok / Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setDefault(True)
        layout.addWidget(button_box)

        # Connections
        self._search_box.textChanged.connect(self._on_search_changed)
        btn_select_all.clicked.connect(self._on_select_all)
        btn_clear.clicked.connect(self._on_clear_all)
        btn_invert.clicked.connect(self._on_invert)
        button_box.accepted.connect(self._on_discrete_accepted)
        button_box.rejected.connect(self.reject)

    def _build_range_ui(self) -> None:
        """Construct the numeric range filter UI for high-cardinality columns."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Detect min/max from float-castable values
        float_values: list[float] = []
        for value in self._all_values:
            with contextlib.suppress(TypeError, ValueError):
                float_values.append(float(value))

        overall_min: float = min(float_values) if float_values else 0.0
        overall_max: float = max(float_values) if float_values else 1.0

        # Determine current range from active filter
        active_filter = self._proxy._column_filters.get(self._col_index)
        current_min: float = overall_min
        current_max: float = overall_max
        if isinstance(active_filter, tuple):
            lo, hi = active_filter
            current_min = lo
            current_max = hi

        form = QFormLayout()
        form.setSpacing(6)

        self._min_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._min_spin.setDecimals(4)
        self._min_spin.setRange(overall_min, overall_max)
        self._min_spin.setValue(current_min)

        self._max_spin: QDoubleSpinBox = QDoubleSpinBox()
        self._max_spin.setDecimals(4)
        self._max_spin.setRange(overall_min, overall_max)
        self._max_spin.setValue(current_max)

        form.addRow(QLabel("Minimum:"), self._min_spin)
        form.addRow(QLabel("Maximum:"), self._max_spin)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setDefault(True)
        layout.addWidget(button_box)

        button_box.accepted.connect(self._on_range_accepted)
        button_box.rejected.connect(self.reject)

    # ------------------------------------------------------------------
    # Private — slot handlers
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        """Hide list items whose display text does not contain the search string.

        Args:
            text: Current text from the search box.
        """
        search = text.lower()
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            if item is None:
                continue
            item_value = item.data(Qt.ItemDataRole.UserRole)
            item.setHidden(search not in str(item_value).lower())

    def _on_select_all(self) -> None:
        """Check all visible items in the list."""
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            if item is not None and not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked)

    def _on_clear_all(self) -> None:
        """Uncheck all visible items in the list."""
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            if item is not None and not item.isHidden():
                item.setCheckState(Qt.CheckState.Unchecked)

    def _on_invert(self) -> None:
        """Toggle the check state of all visible items."""
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            if item is None or item.isHidden():
                continue
            if item.checkState() == Qt.CheckState.Checked:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)

    def _on_discrete_accepted(self) -> None:
        """Apply discrete filter or clear it if all values are selected."""
        checked: set[Any] = set()
        for row in range(self._list_widget.count()):
            item = self._list_widget.item(row)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked.add(item.data(Qt.ItemDataRole.UserRole))

        all_values_set: set[Any] = set(self._all_values.keys())
        if checked == all_values_set:
            self._proxy.clear_column_filter(self._col_index)
        else:
            self._proxy.set_column_filter(self._col_index, checked)

        self.accept()

    def _on_range_accepted(self) -> None:
        """Apply range filter from the spin box values."""
        self._proxy.set_column_filter(
            self._col_index,
            (self._min_spin.value(), self._max_spin.value()),
        )
        self.accept()
