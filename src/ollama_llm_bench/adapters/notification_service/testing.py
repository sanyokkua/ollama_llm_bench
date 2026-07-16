"""In-memory fake ``NotificationService`` for downstream widget-controller tests
(``11_Services_and_Algorithms/01_SERVICE_INVENTORY.md`` §4.10). Records every call;
never raises, never touches Qt.
"""

__all__: list[str] = ["FakeNotificationService"]


class FakeNotificationService:
    """Records every ``show_*`` call in an in-memory list. Satisfies
    ``NotificationService`` structurally.
    """

    def __init__(self) -> None:
        self.info_calls: list[tuple[str, int]] = []
        self.warning_calls: list[tuple[str, int]] = []
        self.error_calls: list[tuple[str, bool]] = []

    def show_info(self, text: str, duration_ms: int = 5000) -> None:
        self.info_calls.append((text, duration_ms))

    def show_warning(self, text: str, duration_ms: int = 5000) -> None:
        self.warning_calls.append((text, duration_ms))

    def show_error(self, text: str, *, blocking: bool = False) -> None:
        self.error_calls.append((text, blocking))
