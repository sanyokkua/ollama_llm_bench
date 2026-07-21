"""``RowActionsDelegate`` -- paints the Enabled toggle plus hover-revealed Test
connection and more-actions (⋯) icon buttons over the Enabled column
(``description.md`` §3.2, §3.3).

Mirrors ``ui/resume_benchmark/_internal/row_actions_delegate.py``'s hover-reveal +
``editorEvent`` hit-testing pattern, adapted to also render the always-visible
Enabled checkbox glyph -- the Providers table has no spare column for a dedicated
Actions column (``adapters.qt_table_models``'s ``make_providers_table_model``
exposes the fixed 6 data-bearing columns only; STORY-066 must consume, never fork,
that factory), so the per-row actions overlay the rightmost (Enabled) column
exactly as resume_benchmark's delegate overlays its Tasks column.
"""

from typing import Protocol, cast, override

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ollama_llm_bench.adapters.qt_table_models.models import ProviderTableRow
from ollama_llm_bench.ui.settings_dialog._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = ["COL_ENABLED", "RowActionsDelegate", "icon_rects_for_cell"]

# See health_auth_delegate.py's column-order note; Enabled is the last data column.
COL_ENABLED = 5
_ICON_SIZE = 16
_ICON_MARGIN = 4
_CHECKBOX_SIZE = 14
_TEST_GLYPH = "⚡"  # ⚡ -- Test connection (reachability-only probe, §3.3)
_MORE_GLYPH = "⋯"  # ⋯ -- opens Edit / Reset this provider / Delete
_CHECKED_GLYPH = "☑"
_UNCHECKED_GLYPH = "☐"


class _RowsExposingModel(Protocol):
    """Structural view of the table model's public ``rows`` property."""

    @property
    def rows(self) -> tuple[ProviderTableRow, ...]: ...


def icon_rects_for_cell(cell_rect: QRect) -> tuple[QRect, QRect, QRect]:
    """Return the ``(checkbox_rect, test_rect, more_rect)`` hit-boxes within `cell_rect`.

    A pure function of the cell's own rect, so both ``paint`` and
    ``editorEvent`` compute identical geometry with no cached per-row state.
    """
    checkbox_rect = QRect(
        cell_rect.left() + _ICON_MARGIN,
        cell_rect.center().y() - _CHECKBOX_SIZE // 2,
        _CHECKBOX_SIZE,
        _CHECKBOX_SIZE,
    )
    more_rect = QRect(
        cell_rect.right() - _ICON_MARGIN - _ICON_SIZE,
        cell_rect.center().y() - _ICON_SIZE // 2,
        _ICON_SIZE,
        _ICON_SIZE,
    )
    test_rect = QRect(
        more_rect.left() - _ICON_MARGIN - _ICON_SIZE,
        cell_rect.center().y() - _ICON_SIZE // 2,
        _ICON_SIZE,
        _ICON_SIZE,
    )
    return checkbox_rect, test_rect, more_rect


class RowActionsDelegate(QStyledItemDelegate):
    """Paints the Enabled checkbox plus hover-revealed Test/more-actions glyphs."""

    enabled_toggled = Signal(int)
    test_clicked = Signal(int)
    more_clicked = Signal(int)

    def __init__(self, *, theme_manager: ThemeManager | None, platform_kind: PlatformKind) -> None:
        super().__init__()
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._hovered_row: int | None = None

    def set_hovered_row(self, row: int | None) -> None:
        """Update which view row currently shows its hover-revealed action icons."""
        self._hovered_row = row

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        theme_manager = self._theme_manager
        if theme_manager is None or index.column() != COL_ENABLED:
            super().paint(painter, option, index)
            return
        row = cast("_RowsExposingModel", index.model()).rows[index.row()]
        cell_rect: QRect = option.rect  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
        tokens = resolve_theme_tokens(
            theme_manager=theme_manager, platform_kind=self._platform_kind
        )
        icon_color = resolve_color(tokens, "text.primary")
        checkbox_rect, test_rect, more_rect = icon_rects_for_cell(cell_rect)
        painter.save()
        painter.setPen(QColor(icon_color))
        checkbox_glyph = _CHECKED_GLYPH if row.enabled else _UNCHECKED_GLYPH
        painter.drawText(checkbox_rect, Qt.AlignmentFlag.AlignCenter, checkbox_glyph)
        if index.row() == self._hovered_row:
            painter.drawText(test_rect, Qt.AlignmentFlag.AlignCenter, _TEST_GLYPH)
            painter.drawText(more_rect, Qt.AlignmentFlag.AlignCenter, _MORE_GLYPH)
        painter.restore()

    @override
    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease or not isinstance(event, QMouseEvent):
            return False
        cell_rect: QRect = option.rect  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
        checkbox_rect, test_rect, more_rect = icon_rects_for_cell(cell_rect)
        position = event.position().toPoint()
        if checkbox_rect.contains(position):
            self.enabled_toggled.emit(index.row())
            return True
        if test_rect.contains(position) and index.row() == self._hovered_row:
            self.test_clicked.emit(index.row())
            return True
        if more_rect.contains(position) and index.row() == self._hovered_row:
            self.more_clicked.emit(index.row())
            return True
        return False
