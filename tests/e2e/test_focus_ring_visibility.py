"""E2E accessibility-floor check: every focus-retaining input renders the focus ring.

Proves the accessibility floor's §5/§10 verification row (08_ACCESSIBILITY_FLOOR.md), scoped
to focus-retaining controls only -- momentary buttons are exempt per DD-52.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QWidget,
)
import pytest
from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.theme import PlatformKind, make_dark_theme_tokens, make_light_theme_tokens

_FOCUS_RETAINING_TYPES: tuple[type[QWidget], ...] = (
    QComboBox,
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)


def _image_contains_color(image: QImage, color: QColor, *, tolerance: int = 8) -> bool:
    target = (color.red(), color.green(), color.blue())
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            channels = (pixel.red(), pixel.green(), pixel.blue())
            if all(abs(a - b) <= tolerance for a, b in zip(channels, target, strict=True)):
                return True
    return False


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_focus_retaining_input_renders_focus_ring_on_click(
    qtbot: QtBot,
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-4

    Every focus-retaining input control (text inputs, combos, spinners, lists, tables --
    not momentary buttons, DD-52) reports hasFocus() and renders the focus.ring border
    colour after a click. Checked against both themes' border_focus value since the live
    app's active theme depends on the host's OS colour-scheme detection.
    """
    dark_focus = QColor(
        make_dark_theme_tokens(platform_kind=PlatformKind.LINUX).colors.border_focus
    )
    light_focus = QColor(
        make_light_theme_tokens(platform_kind=PlatformKind.LINUX).colors.border_focus
    )

    checked = 0
    for surface in mounted_app_surfaces:

        def _activate(surface: QWidget = surface) -> bool:
            surface.raise_()
            surface.activateWindow()
            return surface.isActiveWindow()

        qtbot.waitUntil(_activate, timeout=2000)

        for control in interactive_descendants(surface):
            if (
                not isinstance(control, _FOCUS_RETAINING_TYPES)
                or not control.isVisible()
                or not control.isEnabled()
            ):
                # A disabled control (e.g. `result_widget.run_dropdown` with no runs yet
                # seeded in this fixture) structurally cannot accept a click or hold focus
                # in Qt -- it is not a "focus-retaining input control" in DD-52's operative
                # sense, the same reasoning that already exempts momentary buttons.
                continue
            qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
                control, Qt.MouseButton.LeftButton
            )
            if isinstance(control, QComboBox):
                # A click on a QComboBox opens its popup, and Qt moves actual keyboard
                # focus to the popup's internal QListView for the duration -- hasFocus()
                # on the combo itself is therefore False while the popup is showing, by
                # Qt's own design (needed for arrow-key item navigation), not a product
                # defect. Closing the popup -- the same as a user selecting an item or
                # clicking away -- returns focus to the combo, matching the settled state
                # DD-52's ring requirement actually describes.
                control.hidePopup()
            assert control.hasFocus(), (
                f"{control.objectName()} did not report hasFocus() after a click"
            )

            image = control.grab().toImage()
            assert _image_contains_color(image, dark_focus) or _image_contains_color(
                image, light_focus
            ), f"{control.objectName()} does not render the focus.ring border colour after a click"
            checked += 1

    assert checked > 0, "no focus-retaining control was found to test"
