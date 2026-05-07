"""Installable QObject event filter for YAML file drag-and-drop."""

import logging
from pathlib import Path
from typing import cast, override

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

_YAML_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml"})


class DragDropHandler(QObject):
    """Installable QObject event filter that emits yaml_file_dropped for .yaml/.yml drops.

    Install on any widget via install_on(). The handler sets acceptDrops(True)
    on the target widget and intercepts DragEnter and Drop events. Non-YAML
    files are ignored. All other event types pass through unchanged.
    """

    yaml_file_dropped = Signal(Path)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the handler.

        Args:
            parent: Optional parent QObject for ownership management.
        """
        super().__init__(parent)

    def install_on(self, widget: QWidget) -> None:
        """Enable drag-and-drop on widget by installing this handler as an event filter.

        Also sets acceptDrops(True) on widget — required for drop events to fire.

        Args:
            widget: The target widget that should accept YAML file drops.
        """
        widget.setAcceptDrops(True)
        widget.installEventFilter(self)

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Intercept DragEnter and Drop events.

        Args:
            watched: The widget the event was sent to.
            event: The incoming event.

        Returns:
            True if the event was consumed; False to let it propagate.
        """
        if event.type() == QEvent.Type.DragEnter:
            return self._handle_drag_enter(cast(QDragEnterEvent, event))
        if event.type() == QEvent.Type.Drop:
            return self._handle_drop(cast(QDropEvent, event))
        return super().eventFilter(watched, event)

    def _handle_drag_enter(self, event: QDragEnterEvent) -> bool:
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return False
        for url in mime.urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in _YAML_EXTENSIONS or path.is_dir():
                event.acceptProposedAction()
                return True
        event.ignore()
        return False

    def _handle_drop(self, event: QDropEvent) -> bool:
        mime = event.mimeData()
        accepted = False
        for url in mime.urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                for yaml_path in sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml")):
                    self.yaml_file_dropped.emit(yaml_path)
                    accepted = True
            elif path.suffix.lower() in _YAML_EXTENSIONS:
                self.yaml_file_dropped.emit(path)
                accepted = True
        if accepted:
            event.acceptProposedAction()
        return accepted
