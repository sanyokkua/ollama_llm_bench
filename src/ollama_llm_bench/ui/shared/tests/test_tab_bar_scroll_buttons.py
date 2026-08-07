"""Unit tests for the tab-bar scroll-button click-target fix (STORY-091)."""

from typing import cast

from PySide6.QtWidgets import QTabWidget, QToolButton
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.shared import ensure_tab_bar_scroll_buttons_meet_click_target

_MIN_HIT_AREA_PX = 24
_SCROLL_BUTTON_OBJECT_NAMES = frozenset({"ScrollLeftButton", "ScrollRightButton"})


def test_ensure_tab_bar_scroll_buttons_meet_click_target_resizes_both_buttons(
    qtbot: QtBot,
) -> None:
    """Proves: STORY-091 Definition of Done (08_ACCESSIBILITY_FLOOR.md §6)

    Qt privately constructs a QTabWidget's tab-overflow scroll buttons below the 24x24px
    click-target floor by default (Fusion style: 21x30px); calling the helper resizes both
    to meet it.
    """
    tab_widget = QTabWidget()
    qtbot.addWidget(tab_widget)

    ensure_tab_bar_scroll_buttons_meet_click_target(tab_widget)

    scroll_buttons = [
        button
        for button in cast("list[QToolButton]", tab_widget.tabBar().findChildren(QToolButton))
        if button.objectName() in _SCROLL_BUTTON_OBJECT_NAMES
    ]
    assert scroll_buttons, "QTabBar did not construct its scroll buttons"
    assert all(
        button.minimumWidth() >= _MIN_HIT_AREA_PX and button.minimumHeight() >= _MIN_HIT_AREA_PX
        for button in scroll_buttons
    )


def test_ensure_tab_bar_scroll_buttons_meet_click_target_ignores_other_tool_buttons(
    qtbot: QtBot,
) -> None:
    """Proves: STORY-091 Definition of Done (08_ACCESSIBILITY_FLOOR.md §6)

    Only the two named scroll buttons are resized -- an unrelated QToolButton child of the
    tab bar is left untouched, proving the objectName filter is real rather than a blanket
    resize of every QToolButton descendant.
    """
    tab_widget = QTabWidget()
    qtbot.addWidget(tab_widget)
    unrelated = QToolButton(tab_widget.tabBar())
    unrelated.setObjectName("not_a_scroll_button")

    ensure_tab_bar_scroll_buttons_meet_click_target(tab_widget)

    assert unrelated.minimumWidth() < _MIN_HIT_AREA_PX
    assert unrelated.minimumHeight() < _MIN_HIT_AREA_PX
