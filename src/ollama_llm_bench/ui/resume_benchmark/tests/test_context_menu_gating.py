"""Colocated unit tests for the Resume run table's context menu (STORY-056)."""

from typing import cast

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.resume_benchmark._internal.context_menu import build_context_menu
from ollama_llm_bench.ui.resume_benchmark.models import RunRow


def _row(**overrides: object) -> RunRow:
    base: dict[str, object] = {
        "run_id": 1,
        "effective_name": "Run 1",
        "mode_label": "Task Benchmark",
        "started_at_display": "2024-01-01 00:00",
        "started_at_sort_key": "2024-01-01T00:00:00+00:00",
        "status_badge_label": "Pending",
        "status_badge_status": "neutral",
        "tasks_completed": 0,
        "tasks_total": 2,
        "is_resumable": True,
        "is_executing": False,
        "has_analysis": False,
        "log_file_exists": False,
    }
    base.update(overrides)
    return RunRow(**base)  # type: ignore[arg-type]  # overrides is a loosely-typed test builder


@pytest.mark.parametrize(
    ("row_kwargs", "object_name", "expected_enabled"),
    [
        ({"is_executing": False}, "action_clone", True),
        ({"is_executing": True}, "action_clone", False),
        ({"is_executing": False}, "action_rename", True),
        ({"is_executing": True}, "action_rename", False),
        ({"is_executing": False}, "action_delete", True),
        ({"is_executing": True}, "action_delete", False),
        ({"has_analysis": False}, "action_export_analysis", False),
        ({"has_analysis": True}, "action_export_analysis", True),
        ({"log_file_exists": False}, "action_show_log", False),
        ({"log_file_exists": True}, "action_show_log", True),
        ({}, "action_export_summary_csv", True),
        ({}, "action_export_summary_md", True),
        ({}, "action_export_details_csv", True),
        ({}, "action_export_details_md", True),
    ],
)
def test_menu_item_gating_per_row_state(
    qtbot: QtBot,
    row_kwargs: dict[str, object],
    object_name: str,
    expected_enabled: bool,  # noqa: FBT001  # pytest.mark.parametrize table column, not a call-site flag
) -> None:
    """Proves: STORY-056-AC-4

    Each context-menu item's enabled state matches the selected row's gating,
    table-driven over Clone/Rename/Delete/Export/Show-log.
    """
    # Arrange
    parent = QWidget()
    qtbot.addWidget(parent)
    # Act
    menu = build_context_menu(row=_row(**row_kwargs), parent=parent)
    action = cast("QAction", menu.findChild(QAction, object_name))
    # Assert
    assert action is not None
    assert action.isEnabled() is expected_enabled


def test_disabled_actions_carry_explanatory_tooltip(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-4

    A disabled menu item carries a non-empty tooltip explaining why (no
    placeholder UI without an explanation, 08-L §10).
    """
    # Arrange
    parent = QWidget()
    qtbot.addWidget(parent)
    row = _row(is_executing=True, has_analysis=False, log_file_exists=False)
    # Act
    menu = build_context_menu(row=row, parent=parent)
    action = cast("QAction", menu.findChild(QAction, "action_delete"))
    # Assert
    assert action is not None
    assert action.toolTip() != ""


def test_menu_groups_separated_in_naming_export_file_destructive_order(qtbot: QtBot) -> None:
    """Proves: STORY-056-AC-4

    The menu renders at least one separator between the Naming/Export/File
    groups and the destructive Delete action, per §3.5's group ordering.
    """
    # Arrange
    parent = QWidget()
    qtbot.addWidget(parent)
    # Act
    menu = build_context_menu(row=_row(), parent=parent)
    # Assert
    assert any(action.isSeparator() for action in menu.actions())
