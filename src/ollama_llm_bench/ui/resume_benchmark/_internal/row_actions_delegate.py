"""``RowActionsDelegate`` -- hover-revealed pencil (Rename) and more-actions (⋯)
icon buttons painted over the Tasks column (STORY-056 gap fix, §3.3, SPEC-078).

Mirrors the hover-revealed per-row action-button *intent* of
``ui/new_benchmark/_internal/task_files.py`` (per-row ``make_badge_label``
widgets), adapted to a virtualised ``QTableView`` -- painting glyphs through a
``QStyledItemDelegate`` rather than a persistent per-row widget keeps the
table virtualised for hundreds of rows (EC-RB-12): only the single currently
hovered row's icons are ever painted, and no widget is created per row.

The delegate holds no Gateway/controller reference; it only emits
``pencil_clicked``/``more_clicked`` signals carrying the clicked view row, and
the owning ``ResumeBenchmarkView`` forwards them to the controller.
"""

from typing import override

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

from ollama_llm_bench.ui.resume_benchmark._internal.theme_lookup import resolve_theme_tokens
from ollama_llm_bench.ui.theme import PlatformKind, ThemeManager, resolve_color

__all__: list[str] = ["RowActionsDelegate", "icon_rects_for_cell"]

_ICON_SIZE = 16
_ICON_MARGIN = 4
_PENCIL_GLYPH = "✎"  # ✎ -- inline Rename
_MORE_GLYPH = "⋯"  # ⋯ -- opens the same context menu as right-click


def icon_rects_for_cell(cell_rect: QRect) -> tuple[QRect, QRect]:
    """Return the ``(pencil_rect, more_rect)`` icon hit-boxes within `cell_rect`.

    A pure function of the cell's own rect, so both ``paint`` and
    ``editorEvent`` compute identical geometry with no cached per-row state.
    """
    more_rect = QRect(
        cell_rect.right() - _ICON_MARGIN - _ICON_SIZE,
        cell_rect.center().y() - _ICON_SIZE // 2,
        _ICON_SIZE,
        _ICON_SIZE,
    )
    pencil_rect = QRect(
        more_rect.left() - _ICON_MARGIN - _ICON_SIZE,
        cell_rect.center().y() - _ICON_SIZE // 2,
        _ICON_SIZE,
        _ICON_SIZE,
    )
    return pencil_rect, more_rect


class RowActionsDelegate(QStyledItemDelegate):
    """Paints hover-revealed pencil/more-actions glyphs over the Tasks column."""

    pencil_clicked = Signal(int)
    more_clicked = Signal(int)

    def __init__(self, *, theme_manager: ThemeManager | None, platform_kind: PlatformKind) -> None:
        super().__init__()
        self._theme_manager = theme_manager
        self._platform_kind = platform_kind
        self._hovered_row: int | None = None

    def set_hovered_row(self, row: int | None) -> None:
        """Update which view row currently shows its hover icons."""
        self._hovered_row = row

    @override
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        theme_manager = self._theme_manager
        if index.row() != self._hovered_row or theme_manager is None:
            return
        cell_rect: QRect = option.rect  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
        tokens = resolve_theme_tokens(
            theme_manager=theme_manager, platform_kind=self._platform_kind
        )
        icon_color = resolve_color(tokens, "text.primary")
        pencil_rect, more_rect = icon_rects_for_cell(cell_rect)
        painter.save()
        painter.setPen(QColor(icon_color))
        painter.drawText(pencil_rect, Qt.AlignmentFlag.AlignCenter, _PENCIL_GLYPH)
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
        pencil_rect, more_rect = icon_rects_for_cell(cell_rect)
        position = event.position().toPoint()
        if pencil_rect.contains(position):
            self.pencil_clicked.emit(index.row())
            return True
        if more_rect.contains(position):
            self.more_clicked.emit(index.row())
            return True
        return False
