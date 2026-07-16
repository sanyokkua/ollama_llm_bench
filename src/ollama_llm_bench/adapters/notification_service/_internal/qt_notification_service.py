"""Concrete Qt-backed ``NotificationService`` (08-E §20). Renders toasts on an
injected ``QStatusBar`` and modal errors over an injected ``QWidget`` parent.
"""

from typing import Final

from PySide6.QtWidgets import QMessageBox, QStatusBar, QWidget
import structlog

_log = structlog.get_logger(__name__)

_DEFAULT_DURATION_MS: Final = 5000


class QtNotificationService:
    """Qt ``QStatusBar``/``QMessageBox``-backed ``NotificationService`` (08-E §20).

    Every method is synchronous, must be called on the Qt main thread, and
    never raises to the caller -- a Qt-layer failure (for example the
    underlying widget having been destroyed) is caught and logged instead.
    """

    def __init__(self, *, status_bar: QStatusBar, parent: QWidget) -> None:
        self._status_bar = status_bar
        self._parent = parent

    def show_info(self, text: str, duration_ms: int = _DEFAULT_DURATION_MS) -> None:
        self._show_toast(text=text, duration_ms=duration_ms)

    def show_warning(self, text: str, duration_ms: int = _DEFAULT_DURATION_MS) -> None:
        self._show_toast(text=text, duration_ms=duration_ms)

    def show_error(self, text: str, *, blocking: bool = False) -> None:
        if blocking:
            self._show_modal(text=text)
        else:
            self._show_toast(text=text, duration_ms=_DEFAULT_DURATION_MS)

    def _show_toast(self, *, text: str, duration_ms: int) -> None:
        try:
            self._status_bar.showMessage(text, duration_ms)
        except Exception:  # noqa: BLE001  # never-raises contract; Qt widget calls raise no
            # typed exception hierarchy (08-E §20; error-handling-standard.md allowlist: "an
            # adapter wrapping a native library with no typed exception hierarchy")
            _log.exception("notification_toast_failed")

    def _show_modal(self, *, text: str) -> None:
        try:
            QMessageBox.critical(self._parent, "Error", text)
        except Exception:  # noqa: BLE001  # never-raises contract; same allowlisted case as
            # _show_toast above
            _log.exception("notification_modal_failed")
