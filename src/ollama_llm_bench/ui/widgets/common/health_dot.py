"""HealthDot — 12x12 QLabel status indicator driven by QSS health property."""

from __future__ import annotations

import logging
from typing import Final

from PySide6.QtWidgets import QLabel, QWidget

from ollama_llm_bench.ui.style.style_utils import repolish

logger = logging.getLogger(__name__)

_HEALTH_LIVE: Final[str] = "live"
_HEALTH_DOWN: Final[str] = "down"
_HEALTH_UNKNOWN: Final[str] = "unknown"


class HealthDot(QLabel):
    """Circular 12x12 status indicator driven by the QSS ``health`` property."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._current: str = _HEALTH_UNKNOWN
        self.setProperty("health", _HEALTH_UNKNOWN)

    def set_live(self) -> None:
        """Set dot to live (green) state."""
        self._apply(_HEALTH_LIVE)

    def set_down(self) -> None:
        """Set dot to down (red) state."""
        self._apply(_HEALTH_DOWN)

    def set_unknown(self) -> None:
        """Set dot to unknown (grey) state."""
        self._apply(_HEALTH_UNKNOWN)

    def _apply(self, value: str) -> None:
        if self._current == value:
            return
        self._current = value
        self.setProperty("health", value)
        repolish(self)
