"""MultiCheckFilterButton: a checkable multi-select filter control (08-L §6)."""

from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QPushButton

from ollama_llm_bench.ui.shared.models import FilterSelectionChanged


class MultiCheckFilterButtonWidget(QPushButton):
    """A button opening a checkable option menu; label reflects the checked count."""

    selection_changed = Signal(object)

    def __init__(self, *, label: str, options: tuple[str, ...]) -> None:
        super().__init__()
        self._label = label
        self._options = options
        self._checked: set[str] = set()
        self.setProperty("role", "outlined-muted-button")
        self.setAccessibleName(label)
        menu = QMenu(self)
        self._actions: dict[str, QAction] = {}
        for option in options:
            action = QAction(option, menu)
            action.setCheckable(True)
            action.toggled.connect(partial(self._on_option_toggled, option))
            menu.addAction(action)
            self._actions[option] = action
        self.setMenu(menu)
        self._refresh_label()

    @property
    def checked_options(self) -> tuple[str, ...]:
        return tuple(option for option in self._options if option in self._checked)

    def toggle_option(self, option: str) -> None:
        """Toggle `option`'s checked state, as if the user clicked it in the menu."""
        action = self._actions[option]
        action.setChecked(not action.isChecked())

    def _on_option_toggled(self, option: str, checked: bool) -> None:  # noqa: FBT001  # Qt signal callback
        if checked:
            self._checked.add(option)
        else:
            self._checked.discard(option)
        self._refresh_label()
        self.selection_changed.emit(FilterSelectionChanged(selected_keys=self.checked_options))

    def _refresh_label(self) -> None:
        count = len(self._checked)
        self.setText(f"{self._label} ({count})" if count > 0 else self._label)
