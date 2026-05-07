"""Utility helpers for Qt style management."""

import logging

from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


def repolish(widget: QWidget) -> None:
    """Re-apply QSS after a dynamic setProperty(...) call.

    Qt's style engine caches polish state per widget; mutating a property
    without unpolish/polish leaves the widget visually stale.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
