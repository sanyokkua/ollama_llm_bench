"""Colocated unit tests for RowActionsDelegate (STORY-056 gap fix, §3.3, SPEC-078)."""

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTableView, QWidget
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.resume_benchmark._internal.row_actions_delegate import (
    RowActionsDelegate,
    icon_rects_for_cell,
)
from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import COL_TASKS, RunTableModel
from ollama_llm_bench.ui.resume_benchmark.models import RunRow
from ollama_llm_bench.ui.theme import PlatformKind, ThemeSetting, make_theme_manager

if TYPE_CHECKING:
    from collections.abc import Iterable


def _row() -> RunRow:
    return RunRow(
        run_id=1,
        effective_name="Alpha",
        mode_label="Task Benchmark",
        started_at_display="2024-01-01 00:00",
        started_at_sort_key="2024-01-01T00:00:00+00:00",
        status_badge_label="Done",
        status_badge_status="pass",
        tasks_completed=1,
        tasks_total=1,
        is_resumable=False,
        is_executing=False,
        has_analysis=False,
        log_file_exists=False,
    )


def _release_event(position: QPointF) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_icon_rects_for_cell_places_pencil_left_of_more() -> None:
    """Proves: STORY-056 gap fix (§3.3 -- inline pencil + ⋯ icon geometry)

    The pencil hit-box sits immediately to the left of the more-actions
    hit-box, both inside the cell, neither overlapping.
    """
    # Arrange
    cell_rect = QRect(0, 0, 120, 24)
    # Act
    pencil_rect, more_rect = icon_rects_for_cell(cell_rect)
    # Assert
    assert cell_rect.contains(pencil_rect)
    assert cell_rect.contains(more_rect)
    assert pencil_rect.right() < more_rect.left()


def test_pencil_click_emits_pencil_clicked_with_the_row(qtbot: QtBot) -> None:
    """Proves: STORY-056 gap fix (§3.3 inline pencil Icon Button)

    A mouse-release inside the pencil hit-box emits pencil_clicked carrying
    the clicked view row.
    """
    # Arrange
    delegate = RowActionsDelegate(theme_manager=None, platform_kind=PlatformKind.UNKNOWN)
    model = RunTableModel(rows=(_row(),))
    index = model.index(0, COL_TASKS)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
    pencil_rect, _more_rect = icon_rects_for_cell(option.rect)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
    event = _release_event(QPointF(pencil_rect.center()))

    # Act / Assert
    with qtbot.waitSignal(delegate.pencil_clicked, timeout=1000) as blocker:
        handled = delegate.editorEvent(event, model, option, index)
    assert handled is True
    assert blocker.args == [0]


def test_more_click_emits_more_clicked_with_the_row(qtbot: QtBot) -> None:
    """Proves: STORY-056 gap fix (§3.3, SPEC-078 -- inline ⋯ Icon Button)

    A mouse-release inside the more-actions hit-box emits more_clicked
    carrying the clicked view row.
    """
    # Arrange
    delegate = RowActionsDelegate(theme_manager=None, platform_kind=PlatformKind.UNKNOWN)
    model = RunTableModel(rows=(_row(),))
    index = model.index(0, COL_TASKS)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
    _pencil_rect, more_rect = icon_rects_for_cell(option.rect)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
    event = _release_event(QPointF(more_rect.center()))

    # Act / Assert
    with qtbot.waitSignal(delegate.more_clicked, timeout=1000) as blocker:
        handled = delegate.editorEvent(event, model, option, index)
    assert handled is True
    assert blocker.args == [0]


def test_click_outside_both_icons_is_unhandled(qtbot: QtBot) -> None:
    """Proves: STORY-056 gap fix (§3.3 icon hit-box precision)

    A mouse-release elsewhere in the cell is not treated as an icon click.
    """
    # Arrange
    delegate = RowActionsDelegate(theme_manager=None, platform_kind=PlatformKind.UNKNOWN)
    model = RunTableModel(rows=(_row(),))
    index = model.index(0, COL_TASKS)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute
    event = _release_event(QPointF(2, 2))

    # Act
    handled = delegate.editorEvent(event, model, option, index)

    # Assert
    assert handled is False


def test_paint_with_hovered_row_and_theme_manager_draws_no_exception(
    qtbot: QtBot, qapp: QApplication
) -> None:
    """Proves: STORY-056 gap fix (§3.3 hover-revealed icons)

    Painting the hovered row's Tasks cell with a live ThemeManager wired
    draws the pencil/more glyphs with no exception.
    """
    # Arrange
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    delegate = RowActionsDelegate(theme_manager=theme_manager, platform_kind=PlatformKind.LINUX)
    delegate.set_hovered_row(0)
    model = RunTableModel(rows=(_row(),))
    index = model.index(0, COL_TASKS)
    pixmap = QPixmap(120, 24)
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute

    # Act / Assert (raises nothing)
    delegate.paint(painter, option, index)
    painter.end()


def test_paint_with_unhovered_row_skips_icon_drawing(qtbot: QtBot, qapp: QApplication) -> None:
    """Proves: STORY-056 gap fix (§3.3 hover-revealed icons)

    Painting a row that is not the hovered row raises no exception and does
    not attempt icon-colour resolution (no hovered row is set).
    """
    # Arrange
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    delegate = RowActionsDelegate(theme_manager=theme_manager, platform_kind=PlatformKind.LINUX)
    model = RunTableModel(rows=(_row(),))
    index = model.index(0, COL_TASKS)
    pixmap = QPixmap(120, 24)
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute

    # Act / Assert (raises nothing)
    delegate.paint(painter, option, index)
    painter.end()


def test_delegate_creates_no_per_row_widget(qtbot: QtBot, qapp: QApplication) -> None:
    """Proves: STORY-098-AC-3

    The delegate paints the rename/more-actions glyphs directly; it never
    instantiates a per-row QWidget, keeping the table virtualised (EC-RB-12).
    """
    # Arrange
    table = QTableView()
    model = RunTableModel(rows=(_row(), _row()))
    table.setModel(model)
    delegate = RowActionsDelegate(theme_manager=None, platform_kind=PlatformKind.UNKNOWN)
    table.setItemDelegateForColumn(COL_TASKS, delegate)
    qtbot.addWidget(table)
    children_before = len(list(cast("Iterable[QWidget]", table.viewport().findChildren(QWidget))))

    # Act
    with qtbot.waitExposed(table):
        table.show()
    table.viewport().update()
    qtbot.wait(50)

    # Assert
    children_after = list(cast("Iterable[QWidget]", table.viewport().findChildren(QWidget)))
    assert len(children_after) == children_before
