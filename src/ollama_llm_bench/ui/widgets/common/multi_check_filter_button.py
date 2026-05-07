"""MultiCheckFilterButton — a QToolButton with a searchable checkbox dropdown menu."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

logger = logging.getLogger(__name__)


class MultiCheckFilterButton(QToolButton):
    """A QToolButton that opens a searchable checkbox menu for multi-value filtering.

    Attributes:
        selection_changed: Emitted with the new frozenset[str] when the menu closes.
    """

    selection_changed: Signal = Signal(object)

    def __init__(
        self,
        *,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the button with an empty option set.

        Args:
            label: Display prefix shown in the button text summary.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._label: str = label
        self._all_values: list[str] = []
        self._counts: dict[str, int] = {}
        self._selected: set[str] = set()
        self._checkboxes: dict[str, QCheckBox] = {}
        self._search_hidden: set[str] = set()
        self._menu: QMenu = QMenu(self)
        self._search_field: QLineEdit = QLineEdit()
        self._list_container: QWidget = QWidget()
        self._list_layout: QVBoxLayout = QVBoxLayout(self._list_container)
        self._build_menu_skeleton()
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._update_button_text()
        self.setMenu(self._menu)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_options(self, options: list[str], counts: dict[str, int]) -> None:
        """Replace the option list, preserving the prior selection intersection.

        Args:
            options: The new ordered list of values to display.
            counts: A mapping of value → occurrence count shown next to each checkbox.
        """
        self._all_values = list(options)
        self._counts = dict(counts)
        new_set = frozenset(options)
        intersection = self._selected & new_set
        self._selected = set(intersection) if intersection else set(options)
        self._rebuild_checkboxes()
        self._update_button_text()

    def selected(self) -> frozenset[str]:
        """Return the currently selected values.

        Returns:
            Immutable frozenset of selected value strings.
        """
        return frozenset(self._selected)

    # ------------------------------------------------------------------
    # Private: menu construction
    # ------------------------------------------------------------------

    def _build_menu_skeleton(self) -> None:
        """Build the QMenu containing the search bar, checkbox list, and action buttons."""
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        self._search_field.setPlaceholderText("Search…")
        self._search_field.textChanged.connect(self._on_search_changed)
        outer.addWidget(self._search_field)

        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        outer.addWidget(self._list_container)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("All")
        btn_none = QPushButton("None")
        btn_invert = QPushButton("Invert")
        btn_all.clicked.connect(self._select_all)
        btn_none.clicked.connect(self._clear_all)
        btn_invert.clicked.connect(self._invert)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addWidget(btn_invert)
        outer.addLayout(btn_row)

        action = QWidgetAction(self._menu)
        action.setDefaultWidget(container)
        self._menu.addAction(action)
        self._menu.aboutToHide.connect(self._on_menu_closed)

    def _rebuild_checkboxes(self) -> None:
        """Remove existing checkbox widgets and create fresh ones from _all_values."""
        for cb in self._checkboxes.values():
            self._list_layout.removeWidget(cb)
            cb.deleteLater()
        self._checkboxes.clear()
        self._search_hidden.clear()
        self._search_field.clear()

        for value in self._all_values:
            count = self._counts.get(value, 0)
            cb = QCheckBox(f"{value} ({count})")
            cb.setChecked(value in self._selected)
            cb.stateChanged.connect(lambda state, v=value: self._on_item_toggled(v, bool(state)))
            self._checkboxes[value] = cb
            self._list_layout.addWidget(cb)

    # ------------------------------------------------------------------
    # Private: slot handlers
    # ------------------------------------------------------------------

    def _on_item_toggled(self, value: str, checked: bool) -> None:
        """Update selection set when a checkbox is toggled.

        Args:
            value: The option value whose checkbox changed.
            checked: True if the checkbox is now checked.
        """
        if checked:
            self._selected.add(value)
        else:
            self._selected.discard(value)
        self._update_button_text()

    def _on_search_changed(self, text: str) -> None:
        """Show/hide checkboxes based on the search text (visibility only).

        Args:
            text: Current text in the search field.
        """
        lower = text.lower()
        self._search_hidden.clear()
        for value, cb in self._checkboxes.items():
            visible = lower in value.lower()
            cb.setVisible(visible)
            if not visible:
                self._search_hidden.add(value)

    def _select_all(self) -> None:
        """Check all search-visible checkboxes and update selection state."""
        for value, cb in self._checkboxes.items():
            if value not in self._search_hidden:
                cb.setChecked(True)
                self._selected.add(value)
        self._update_button_text()

    def _clear_all(self) -> None:
        """Uncheck all checkboxes and clear selection state."""
        for cb in self._checkboxes.values():
            cb.setChecked(False)
        self._selected.clear()
        self._update_button_text()

    def _invert(self) -> None:
        """Flip the checked state of every search-visible checkbox."""
        for value, cb in self._checkboxes.items():
            if value not in self._search_hidden:
                new_state = not cb.isChecked()
                cb.setChecked(new_state)
                if new_state:
                    self._selected.add(value)
                else:
                    self._selected.discard(value)
        self._update_button_text()

    def _on_menu_closed(self) -> None:
        """Emit selection_changed with the committed frozenset when the menu closes."""
        self.selection_changed.emit(frozenset(self._selected))

    # ------------------------------------------------------------------
    # Private: button text
    # ------------------------------------------------------------------

    def _update_button_text(self) -> None:
        """Refresh the button label to reflect the current selection summary."""
        total = len(self._all_values)
        n_selected = len(self._selected)
        if n_selected == 0:
            text = f"{self._label}: None — empty"
        elif n_selected == total:
            text = f"{self._label}: All ({total})"
        else:
            text = f"{self._label}: {n_selected} of {total}"
        self.setText(text)
