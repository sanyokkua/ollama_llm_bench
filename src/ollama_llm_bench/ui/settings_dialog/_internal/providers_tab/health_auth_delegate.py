"""``HealthAuthDelegate`` -- paints the Health and Auth columns of the Providers
table as a coloured status dot and a coloured auth badge instead of plain text
(STORY-066-AC-1).

Mirrors ``ui/resume_benchmark/_internal/status_badge_delegate.py``'s pattern of
extracting a directly unit-testable pure colour-resolution function from the
paint path. Reads the full ``ProviderTableRow`` off the table model's public
``rows`` property (exposed by ``adapters.qt_table_models``'s
``_FrozenRowTableModel`` base, even though the factory's declared return type is
the base ``QAbstractTableModel``) rather than a ``UserRole`` -- the adapter's
``_ProvidersTableModel`` supports ``DisplayRole`` only (STORY-066 must consume,
never fork, ``make_providers_table_model``).
"""

from typing import Protocol, cast, override

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow
from ollama_llm_bench.backend.domain import ProviderTestStatus
from ollama_llm_bench.ui.settings_dialog._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.settings_dialog._internal.view_model_select import (
    provider_test_status_to_health,
)
from ollama_llm_bench.ui.shared import resolve_badge_color_roles
from ollama_llm_bench.ui.shared.models import BadgeStatus
from ollama_llm_bench.ui.theme import (
    PlatformKind,
    ThemeManager,
    resolve_color,
    resolve_health_color,
)

__all__: list[str] = ["COL_AUTH", "COL_HEALTH", "HealthAuthDelegate", "resolve_auth_badge_colors"]

# Column order is fixed by ``adapters.qt_table_models._internal.providers_model``'s
# header tuple (Health, Name, Type, Base URL, Auth, Enabled) -- ``description.md``
# §3.2's own column order, unlikely to change without a spec revision.
COL_HEALTH = 0
COL_AUTH = 4
_DOT_DIAMETER = 10
_DOT_MARGIN = 6

_BADGE_STATUS_BY_AUTH_BADGE: dict[str, BadgeStatus] = {
    "env ✓": BadgeStatus.PASS,
    "env ✗": BadgeStatus.FAIL,
    "none": BadgeStatus.NEUTRAL,
}


class _RowsExposingModel(Protocol):
    """Structural view of the table model's public ``rows`` property."""

    @property
    def rows(self) -> tuple[ProviderTableRow, ...]: ...


def resolve_auth_badge_colors(
    *, auth_badge: str, theme_manager: ThemeManager, platform_kind: PlatformKind
) -> tuple[str, str]:
    """Resolve ``(base_hex, fill_hex)`` for a ``ProviderTableRow.auth_badge`` value."""
    badge_status = _BADGE_STATUS_BY_AUTH_BADGE[auth_badge]
    base_role, fill_role = resolve_badge_color_roles(badge_status)
    tokens = resolve_theme_tokens(theme_manager=theme_manager, platform_kind=platform_kind)
    return resolve_color(tokens, base_role), resolve_color(tokens, fill_role)


class HealthAuthDelegate(QStyledItemDelegate):
    """Paints the Health column as a status dot and the Auth column as a badge."""

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
        if theme_manager is None or index.column() not in (COL_HEALTH, COL_AUTH):
            super().paint(painter, option, index)
            return
        row = cast("_RowsExposingModel", index.model()).rows[index.row()]
        cell_rect: QRect = option.rect  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
        if index.column() == COL_HEALTH:
            self._paint_health(painter, cell_rect, row.health, theme_manager)
            return
        self._paint_auth(painter, cell_rect, row.auth_badge, theme_manager)

    def _paint_health(
        self,
        painter: QPainter,
        cell_rect: QRect,
        status: ProviderTestStatus,
        theme_manager: ThemeManager,
    ) -> None:
        state = provider_test_status_to_health(status)
        tokens = resolve_theme_tokens(
            theme_manager=theme_manager, platform_kind=self._platform_kind
        )
        color_hex = resolve_health_color(tokens, state)
        dot_rect = QRect(
            cell_rect.left() + _DOT_MARGIN,
            cell_rect.center().y() - _DOT_DIAMETER // 2,
            _DOT_DIAMETER,
            _DOT_DIAMETER,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(dot_rect))
        painter.setPen(QColor(color_hex))
        text_rect = cell_rect.adjusted(_DOT_MARGIN * 2 + _DOT_DIAMETER, 0, 0, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, state.value)
        painter.restore()

    def _paint_auth(
        self, painter: QPainter, cell_rect: QRect, auth_badge: str, theme_manager: ThemeManager
    ) -> None:
        base_hex, _fill_hex = resolve_auth_badge_colors(
            auth_badge=auth_badge, theme_manager=theme_manager, platform_kind=self._platform_kind
        )
        painter.save()
        painter.setPen(QColor(base_hex))
        painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, auth_badge)
        painter.restore()
