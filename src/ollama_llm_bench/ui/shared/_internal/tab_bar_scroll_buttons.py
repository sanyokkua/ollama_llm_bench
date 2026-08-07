"""Resizes a ``QTabWidget``'s Qt-internal tab-overflow scroll buttons to the accessibility
floor's minimum hit area (``08_ACCESSIBILITY_FLOOR.md`` §6).

Qt's ``QTabBar`` privately constructs two ``QToolButton``s -- objectName
``"ScrollLeftButton"``/``"ScrollRightButton"`` -- the instant a ``QTabWidget`` is built, sized
well below the 24x24px floor by default (Qt Fusion style: 21x30px). The application has no
construction site of its own for them, so every ``QTabWidget`` whose tab strip can overflow
must apply this once, right after construction.
"""

from typing import TYPE_CHECKING, cast

from PySide6.QtWidgets import QTabWidget, QToolButton

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__: list[str] = ["apply_tab_bar_scroll_button_min_hit_area"]

_SCROLL_BUTTON_OBJECT_NAMES: frozenset[str] = frozenset({"ScrollLeftButton", "ScrollRightButton"})
_MIN_HIT_AREA_PX = 24


def apply_tab_bar_scroll_button_min_hit_area(tab_widget: QTabWidget) -> None:
    """Resize `tab_widget`'s tab-bar scroll buttons, if any, to the 24x24px floor."""
    buttons = cast("Iterable[QToolButton]", tab_widget.tabBar().findChildren(QToolButton))
    for button in buttons:
        if button.objectName() in _SCROLL_BUTTON_OBJECT_NAMES:
            button.setMinimumSize(_MIN_HIT_AREA_PX, _MIN_HIT_AREA_PX)
