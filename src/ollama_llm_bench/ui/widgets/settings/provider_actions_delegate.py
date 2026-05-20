"""ProviderActionsDelegate — renders Test / Edit / Delete buttons in the actions column."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QModelIndex, QObject, QPersistentModelIndex, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStyledItemDelegate, QStyleOptionViewItem, QWidget


class _Signals(QObject):
    """Signal carrier for ProviderActionsDelegate.

    QStyledItemDelegate does not inherit QObject through the metaclass path that
    exposes Signal, so signals live on a separate QObject instance.
    """

    test_requested: Signal = Signal(int)  # row index
    edit_requested: Signal = Signal(int)
    delete_requested: Signal = Signal(int)
    reset_requested: Signal = Signal(int)


class ProviderActionsDelegate(QStyledItemDelegate):
    """Renders Test / Edit / Delete buttons via persistent editors in the actions column.

    Callers must open a persistent editor for each row via QTableView.openPersistentEditor()
    and refresh them after row insertions or deletions to keep row-index closures accurate.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.signals = _Signals()

    @override
    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        """Return a button-row widget for the given table row."""
        return self._make_button_row(index.row(), parent)

    @override
    def updateEditorGeometry(
        self,
        editor: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Fit the button-row widget into the cell rectangle."""
        editor.setGeometry(option.rect)

    def _make_button_row(self, row: int, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        test_btn = QPushButton("Test", container)
        edit_btn = QPushButton("Edit", container)
        delete_btn = QPushButton("Delete", container)

        test_btn.setProperty("size", "small")
        edit_btn.setProperty("size", "small")
        delete_btn.setProperty("size", "small")
        delete_btn.setProperty("role", "danger")

        reset_btn = QPushButton("Reset", container)
        reset_btn.setProperty("size", "small")

        test_btn.clicked.connect(lambda: self.signals.test_requested.emit(row))
        edit_btn.clicked.connect(lambda: self.signals.edit_requested.emit(row))
        delete_btn.clicked.connect(lambda: self.signals.delete_requested.emit(row))
        reset_btn.clicked.connect(lambda: self.signals.reset_requested.emit(row))

        layout.addWidget(test_btn)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        layout.addWidget(reset_btn)
        layout.addStretch()
        return container
