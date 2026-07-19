"""BadgeLabel: a colour-role pill rendering a semantic status + text (08-L §8, 08-D §5)."""

from typing import override

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from ollama_llm_bench.ui.shared._internal.theme_resolution import resolve_active_tokens
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

_BASE_ROLE: dict[BadgeStatus, str] = {
    BadgeStatus.PASS: "success.base",
    BadgeStatus.FAIL: "error.base",
    BadgeStatus.WARNING: "warning.base",
    BadgeStatus.INFO: "info.base",
    BadgeStatus.NEUTRAL: "muted.base",
}
_FILL_ROLE: dict[BadgeStatus, str] = {
    BadgeStatus.PASS: "success.fill",
    BadgeStatus.FAIL: "error.fill",
    BadgeStatus.WARNING: "warning.fill",
    BadgeStatus.INFO: "info.fill",
    BadgeStatus.NEUTRAL: "muted.fill",
}


def resolve_badge_color_roles(status: BadgeStatus) -> tuple[str, str]:
    """Return the ``(base_role, fill_role)`` colour-role names for a badge status.

    Shared by ``BadgeLabelWidget`` and any other custom-painted surface (for
    example a table-cell delegate) that must render the same badge colour
    language without constructing a full widget instance.
    """
    return _BASE_ROLE[status], _FILL_ROLE[status]


class BadgeLabelWidget(QWidget):
    """A pill-shaped badge: a soft fill background plus base-coloured text (08-D §5)."""

    def __init__(
        self,
        *,
        status: BadgeStatus,
        text: str,
        theme_manager: ThemeManager,
        platform_kind: PlatformKind,
    ) -> None:
        super().__init__()
        self._status = status
        self._text = text
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self.setProperty("badgeStatus", status.value)
        self.setAccessibleName(f"{status.value} badge: {text}")
        theme_manager.theme_changed.connect(self._on_theme_changed)

    @property
    def status(self) -> BadgeStatus:
        return self._status

    @property
    def text_label(self) -> str:
        return self._text

    def current_base_color_hex(self) -> str:
        tokens = resolve_active_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        return resolve_color(tokens, _BASE_ROLE[self._status])

    def current_fill_color_hex(self) -> str:
        tokens = resolve_active_tokens(
            theme_manager=self._theme_manager, platform_kind=self._platform_kind
        )
        return resolve_color(tokens, _FILL_ROLE[self._status])

    @override
    def sizeHint(self) -> QSize:  # Qt override signature
        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self._text)
        return QSize(text_width + 24, max(20, metrics.height() + 8))

    def _on_theme_changed(self) -> None:
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:  # Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(self.current_fill_color_hex()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.rect()), 3.0, 3.0)
        painter.setPen(QColor(self.current_base_color_hex()))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()
