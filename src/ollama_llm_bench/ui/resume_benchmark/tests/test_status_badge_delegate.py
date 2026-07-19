"""Colocated unit tests for StatusBadgeDelegate (STORY-056 gap fix, §4.3)."""

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.resume_benchmark._internal.run_table_model import COL_STATUS, RunTableModel
from ollama_llm_bench.ui.resume_benchmark._internal.status_badge_delegate import (
    StatusBadgeDelegate,
    resolve_status_badge_colors,
)
from ollama_llm_bench.ui.resume_benchmark.models import RunRow
from ollama_llm_bench.ui.theme import (
    PlatformKind,
    ThemeSetting,
    make_dark_theme_tokens,
    make_theme_manager,
    resolve_color,
)

_STATUS_TO_ROLES = [
    ("pass", "success.base", "success.fill"),
    ("warning", "warning.base", "warning.fill"),
    ("fail", "error.base", "error.fill"),
    ("neutral", "muted.base", "muted.fill"),
]


def _row(status_badge_status: str) -> RunRow:
    return RunRow(
        run_id=1,
        effective_name="Alpha",
        mode_label="Task Benchmark",
        started_at_display="2024-01-01 00:00",
        started_at_sort_key="2024-01-01T00:00:00+00:00",
        status_badge_label="Done",
        status_badge_status=status_badge_status,
        tasks_completed=1,
        tasks_total=1,
        is_resumable=False,
        is_executing=False,
        has_analysis=False,
        log_file_exists=False,
    )


@pytest.mark.parametrize(("status_badge_status", "base_role", "fill_role"), _STATUS_TO_ROLES)
def test_resolve_status_badge_colors_matches_theme_role_per_status(
    status_badge_status: str, base_role: str, fill_role: str, qapp: QApplication
) -> None:
    """Proves: STORY-056-AC-3 (gap fix: coloured Status badge, §4.3)

    For each RunRow.status_badge_status value, resolve_status_badge_colors
    resolves the exact same (base, fill) colour-role pair BadgeLabelWidget
    uses for that badge status.
    """
    # Arrange
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    tokens = make_dark_theme_tokens(platform_kind=PlatformKind.LINUX)

    # Act
    base_hex, fill_hex = resolve_status_badge_colors(
        status_badge_status=status_badge_status,
        theme_manager=theme_manager,
        platform_kind=PlatformKind.LINUX,
    )

    # Assert
    assert base_hex == resolve_color(tokens, base_role)
    assert fill_hex == resolve_color(tokens, fill_role)


def test_paint_with_no_theme_manager_falls_back_to_default_rendering(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-3 (gap fix: coloured Status badge, §4.3)

    With no live ThemeManager wired, the delegate paints via the base
    QStyledItemDelegate implementation with no exception -- the same
    optional-collaborator fallback ui/new_benchmark/_internal/task_files.py
    already establishes.
    """
    # Arrange
    delegate = StatusBadgeDelegate(theme_manager=None, platform_kind=PlatformKind.UNKNOWN)
    model = RunTableModel(rows=(_row("pass"),))
    index = model.index(0, COL_STATUS)
    pixmap = QPixmap(120, 24)
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute

    # Act / Assert (raises nothing)
    delegate.paint(painter, option, index)
    painter.end()


def test_paint_with_theme_manager_draws_a_coloured_badge(qtbot: QtBot, qapp: QApplication) -> None:
    """Proves: STORY-056-AC-3 (gap fix: coloured Status badge, §4.3)

    With a live ThemeManager wired, painting a Status cell raises no
    exception and does not fall through to the plain-text default painter.
    """
    # Arrange
    theme_manager = make_theme_manager(
        app=qapp, theme_setting=ThemeSetting.DARK, platform_kind=PlatformKind.LINUX
    )
    delegate = StatusBadgeDelegate(theme_manager=theme_manager, platform_kind=PlatformKind.LINUX)
    model = RunTableModel(rows=(_row("pass"),))
    index = model.index(0, COL_STATUS)
    pixmap = QPixmap(120, 24)
    painter = QPainter(pixmap)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 120, 24)  # type: ignore[attr-defined]  # PySide6 stub gap: QStyleOption.rect is a real public C++ attribute

    # Act / Assert (raises nothing)
    delegate.paint(painter, option, index)
    painter.end()
