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

# Types that acquire focus from a click on every platform this project supports. A populated
# QComboBox does not: clicking it opens its popup, the popup takes keyboard focus, and
# hidePopup() does not hand it back (measured on macOS: still False after 50 processEvents()
# turns). See STORY-119's "Open spec conflict" section -- §5's ring obligation is on a control
# that *holds* focus, so combos are verified by the setFocus() check below instead.
_CLICK_FOCUSING_TYPES: tuple[type[QWidget], ...] = (
    QLineEdit,
    QTextEdit,
    QAbstractSpinBox,
    QAbstractItemView,
)
_FOCUS_RETAINING_TYPES: tuple[type[QWidget], ...] = (QComboBox, *_CLICK_FOCUSING_TYPES)
_MIN_EXPECTED_CLICKED = 10  # measured on both platforms; combos moved to the setFocus check
_MIN_EXPECTED_FOCUSED = 17  # measured on both platforms: the 10 above plus 7 combos


def _image_contains_color(image: QImage, color: QColor, *, tolerance: int = 8) -> bool:
    target = (color.red(), color.green(), color.blue())
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            channels = (pixel.red(), pixel.green(), pixel.blue())
            if all(abs(a - b) <= tolerance for a, b in zip(channels, target, strict=True)):
                return True
    return False


def _renders_focus_ring(control: QWidget) -> bool:
    """Whether `control`'s grabbed image carries either theme's focus.ring border colour.

    Both themes are accepted because the live application's active theme depends on the
    host's OS colour-scheme detection.
    """
    dark_focus = QColor(
        make_dark_theme_tokens(platform_kind=PlatformKind.LINUX).colors.border_focus
    )
    light_focus = QColor(
        make_light_theme_tokens(platform_kind=PlatformKind.LINUX).colors.border_focus
    )
    image = control.grab().toImage()
    return _image_contains_color(image, dark_focus) or _image_contains_color(image, light_focus)


def _scan_focus_rings(
    *,
    surfaces: list[QWidget],
    walk: Callable[[QWidget], list[QWidget]],
    qtbot: QtBot,
    types: tuple[type[QWidget], ...],
    acquire_focus: Callable[[QWidget], None],
) -> tuple[list[str], list[str], int]:
    """Drive focus onto every eligible control and report (violations, skipped, checked).

    Controls that are currently disabled (e.g. the New Benchmark Advanced Options rows
    before their activation checkbox is checked, the Judge dropdowns before judge mode is
    selected, `result_widget.run_dropdown` and `summary_tab.table` before a run is selected)
    are exempt -- a disabled Qt widget structurally cannot accept a click or hold focus
    regardless of policy, the same reasoning that already exempts momentary buttons.
    """
    violations: list[str] = []
    skipped: list[str] = []
    checked = 0
    for surface in surfaces:

        def _activate(surface: QWidget = surface) -> bool:
            surface.raise_()
            surface.activateWindow()
            return surface.isActiveWindow()

        qtbot.waitUntil(_activate, timeout=2000)
        surface_label = f"{type(surface).__name__}[{surface.objectName()}]"

        for control in walk(surface):
            if not isinstance(control, types) or not control.isVisible():
                continue
            control_label = f"{surface_label} -> {type(control).__name__}[{control.objectName()}]"
            if not control.isEnabled():
                skipped.append(f"{control_label} (disabled)")
                continue
            acquire_focus(control)
            if not control.hasFocus():
                violations.append(f"{control_label} did not report hasFocus()")
                continue
            if not _renders_focus_ring(control):
                violations.append(f"{control_label} does not render the focus.ring border colour")
                continue
            checked += 1
    return violations, skipped, checked


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_focus_retaining_input_renders_focus_ring_on_click(
    qtbot: QtBot,
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-4

    Every focus-retaining input control that acquires focus from a click on every platform
    (text inputs, text areas, spinners, lists, tables -- not momentary buttons, DD-52, and
    not combo boxes, whose popup takes focus on macOS: STORY-119) reports hasFocus() and
    renders the focus.ring border colour after a click.
    """
    violations, skipped, checked = _scan_focus_rings(
        surfaces=mounted_app_surfaces,
        walk=interactive_descendants,
        qtbot=qtbot,
        types=_CLICK_FOCUSING_TYPES,
        acquire_focus=lambda control: qtbot.mouseClick(  # type: ignore[no-untyped-call]  # pytest-qt provides no type stubs
            control, Qt.MouseButton.LeftButton
        ),
    )

    assert not violations, (
        f"{len(violations)} control(s) failed the focus-ring check after a click:\n"
        + "\n".join(violations)
    )
    assert checked >= _MIN_EXPECTED_CLICKED, (
        f"only {checked} controls were verified (expected >= {_MIN_EXPECTED_CLICKED}); "
        f"a regression may have disabled or hidden an entire surface's controls -- "
        f"{len(skipped)} skipped as disabled: {skipped}"
    )


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_focus_retaining_input_renders_focus_ring_while_it_holds_focus(
    qtbot: QtBot,
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-119-AC-2

    Every focus-retaining input control -- combos included -- renders the focus.ring border
    colour while it holds focus, on the native platform and offscreen alike. Focus is driven
    with setFocus() rather than a click because §5's obligation is on a control that *holds*
    focus, and a populated combo box does not retain click focus on macOS (STORY-119).
    """
    violations, skipped, checked = _scan_focus_rings(
        surfaces=mounted_app_surfaces,
        walk=interactive_descendants,
        qtbot=qtbot,
        types=_FOCUS_RETAINING_TYPES,
        acquire_focus=lambda control: control.setFocus(),
    )

    assert not violations, (
        f"{len(violations)} control(s) failed the focus-ring check while holding focus:\n"
        + "\n".join(violations)
    )
    assert checked >= _MIN_EXPECTED_FOCUSED, (
        f"only {checked} controls were verified (expected >= {_MIN_EXPECTED_FOCUSED}); "
        f"a regression may have disabled or hidden an entire surface's controls -- "
        f"{len(skipped)} skipped as disabled: {skipped}"
    )
