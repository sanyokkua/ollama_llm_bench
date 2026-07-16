"""Qt-based notification surface -- QStatusBar toasts and QMessageBox modals
(08-E §20). The sole sanctioned path for a controller to raise a user-visible
message.
"""

from ollama_llm_bench.adapters.notification_service.api import (
    NotificationService,
    make_notification_service,
)

__all__: list[str] = ["NotificationService", "make_notification_service"]
