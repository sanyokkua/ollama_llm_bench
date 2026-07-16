"""Public factory for the Qt-backed ``NotificationService`` (08-E §20)."""

import icontract
from PySide6.QtCore import QCoreApplication, QThread
from PySide6.QtWidgets import QStatusBar, QWidget

from ollama_llm_bench.adapters.notification_service._internal.qt_notification_service import (
    QtNotificationService,
)
from ollama_llm_bench.adapters.notification_service.protocols import NotificationService

__all__: list[str] = ["NotificationService", "make_notification_service"]


@icontract.require(
    lambda: QCoreApplication.instance() is not None,
    "a QApplication must already exist -- called once from compose.py during start-up",
)
@icontract.require(
    lambda: QThread.currentThread() is QCoreApplication.instance().thread(),  # type: ignore[union-attr]
    "make_notification_service must be called on the Qt GUI thread -- NotificationService is "
    "synchronous and main-thread-only (08-E §20)",
)
def make_notification_service(*, status_bar: QStatusBar, parent: QWidget) -> NotificationService:
    """Construct the Qt-backed NotificationService.

    Args:
        status_bar: The status bar toasts render into.
        parent: The top-level widget error modals are centered over.

    Returns:
        A NotificationService showing toasts on ``status_bar`` and modal
        errors over ``parent``.
    """
    return QtNotificationService(status_bar=status_bar, parent=parent)
