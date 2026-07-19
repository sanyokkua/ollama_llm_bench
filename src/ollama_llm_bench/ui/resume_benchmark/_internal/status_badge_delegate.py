"""``StatusBadgeDelegate`` -- paints the Status column as a coloured badge instead
of plain text (STORY-056 gap fix, §4.3).

Reuses ``ui/shared``'s ``resolve_badge_color_roles`` colour-role mapping and
``ui/theme``'s ``resolve_color`` -- no ``setStyleSheet``, no colour literal.
``resolve_status_badge_colors`` is a small, directly unit-testable pure
function extracted from the paint path, mirroring how
``ui/shared/tests/test_badge_label.py`` tests ``BadgeLabelWidget``'s colour
resolution without a full paint-event round trip.
"""

from typing import override

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ollama_llm_bench.ui.resume_benchmark._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.shared import resolve_badge_color_roles
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = ["StatusBadgeDelegate", "resolve_status_badge_colors"]

_BADGE_STATUS_BY_TONE: dict[str, BadgeStatus] = {
    "pass": BadgeStatus.PASS,
    "warning": BadgeStatus.WARNING,
    "fail": BadgeStatus.FAIL,
    "neutral": BadgeStatus.NEUTRAL,
}
_CELL_MARGIN = 4
_CORNER_RADIUS = 3.0


def resolve_status_badge_colors(
    *, status_badge_status: str, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> tuple[str, str]:
    """Resolve ``(base_hex, fill_hex)`` for a ``RunRow.status_badge_status`` value.

    Args:
        status_badge_status: One of ``"pass"``/``"warning"``/``"fail"``/``"neutral"``
            (``RunRow.status_badge_status``, §4.3).
        theme_manager: Supplies the currently active theme's token container.
        platform_kind: The platform whose font/colour token variant applies.

    Returns:
        The resolved base (text/border) and fill (background) hex colours.
    """
    badge_status = _BADGE_STATUS_BY_TONE[status_badge_status]
    base_role, fill_role = resolve_badge_color_roles(badge_status)
    tokens = resolve_theme_tokens(theme_manager=theme_manager, platform_kind=platform_kind)
    return resolve_color(tokens, base_role), resolve_color(tokens, fill_role)


class StatusBadgeDelegate(QStyledItemDelegate):
    """Paints the Status column as a coloured pill (§4.3) instead of plain text."""

    def __init__(self, *, theme_manager: ThemeManager | None, platform_kind: PlatformKind) -> None:
        super().__init__()
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        theme_manager = self._theme_manager
        status_value = index.data(Qt.ItemDataRole.UserRole)
        label = index.data(Qt.ItemDataRole.DisplayRole)
        if theme_manager is None or not isinstance(status_value, str) or not isinstance(label, str):
            super().paint(painter, option, index)
            return
        base_hex, fill_hex = resolve_status_badge_colors(
            status_badge_status=status_value,
            theme_manager=theme_manager,
            platform_kind=self._platform_kind,
        )
        cell_rect: QRect = option.rect  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
        rect = cell_rect.adjusted(_CELL_MARGIN, _CELL_MARGIN, -_CELL_MARGIN, -_CELL_MARGIN)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(fill_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(rect), _CORNER_RADIUS, _CORNER_RADIUS)
        painter.setPen(QColor(base_hex))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()
