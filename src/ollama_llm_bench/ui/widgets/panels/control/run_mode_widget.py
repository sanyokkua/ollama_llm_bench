"""Run mode selection widget — four ordered radio buttons with mode-change signal."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QButtonGroup, QRadioButton, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.constants import (
    RUN_MODE_DESCRIPTIONS,
    RUN_MODE_LABELS,
    RUN_MODE_ORDER,
)
from ollama_llm_bench.backend.core.models import RunMode

_logger = logging.getLogger(__name__)


class RunModeWidget(QWidget):
    """Widget presenting one radio button per run mode in a fixed order.

    Emits ``mode_changed`` when the user selects a different mode.
    Spurious signals during construction are suppressed via ``QSignalBlocker``.
    """

    mode_changed = Signal(RunMode)

    def __init__(
        self,
        *,
        initial_mode: RunMode = RunMode.SPEED,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the widget with radio buttons for each run mode.

        Args:
            initial_mode: The mode to pre-select on construction.
            parent: Optional Qt parent widget.
        """
        super().__init__(parent)

        self._buttons: dict[RunMode, QRadioButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._create_buttons()
        self._build_layout()

        with QSignalBlocker(self._button_group):
            self.set_mode(initial_mode)

        self._button_group.buttonToggled.connect(self._on_button_toggled)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_buttons(self) -> None:
        for index, mode in enumerate(RUN_MODE_ORDER):
            button = QRadioButton(RUN_MODE_LABELS[mode])
            button.setToolTip(RUN_MODE_DESCRIPTIONS[mode])
            self._buttons[mode] = button
            self._button_group.addButton(button, index)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for mode in RUN_MODE_ORDER:
            layout.addWidget(self._buttons[mode])

    def _on_button_toggled(self, button: QRadioButton, checked: bool) -> None:
        if not checked:
            return
        for mode, btn in self._buttons.items():
            if btn is button:
                _logger.debug("Run mode changed: %s", mode)
                self.mode_changed.emit(mode)
                return

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_mode(self) -> RunMode:
        """Return the currently selected run mode.

        Returns:
            The ``RunMode`` whose radio button is checked, or ``RunMode.SPEED``
            if no button is checked (should not occur in normal use).
        """
        for mode, button in self._buttons.items():
            if button.isChecked():
                return mode
        return RunMode.SPEED

    def set_mode(self, mode: RunMode) -> None:
        """Set the selected mode without emitting ``mode_changed``.

        Args:
            mode: The ``RunMode`` to pre-select.
        """
        button = self._buttons.get(mode)
        if button is not None:
            button.setChecked(True)
        else:
            _logger.warning("set_mode called with unknown mode: %s", mode)
