"""E2E accessibility-floor check: every clickable control has a >=24x24px hit area.

Proves the accessibility floor's §6/§10 verification row (08_ACCESSIBILITY_FLOOR.md).
"""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget
import pytest

_MIN_HIT_AREA_PX = 24
_MIN_EXPECTED_WALKED = 225


def _undersized_controls(
    surfaces: list[QWidget], walk: Callable[[QWidget], list[QWidget]]
) -> tuple[list[str], int]:
    """Report (violations, walked count) for every control under the 24x24px hit area."""
    violations: list[str] = []
    walked = 0
    for surface in surfaces:
        for control in walk(surface):
            walked += 1
            if control.width() >= _MIN_HIT_AREA_PX and control.height() >= _MIN_HIT_AREA_PX:
                continue
            violations.append(
                f"{type(surface).__name__}({surface.objectName() or '<no objectName>'}) > "
                f"{type(control).__name__}({control.objectName() or '<no objectName>'}) "
                f"{control.width()}x{control.height()}"
            )
    return violations, walked


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_every_clickable_control_meets_24px_minimum_hit_area(
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-3

    Every interactive control across the mounted application, the Settings dialog, and the
    seven shared modal dialogs offers a hit area of at least 24x24 logical pixels at the
    application's default scale.
    """
    undersized, walked = _undersized_controls(mounted_app_surfaces, interactive_descendants)

    assert undersized == [], "controls below the 24x24px minimum hit area:\n" + "\n".join(
        undersized
    )
    assert walked >= _MIN_EXPECTED_WALKED, (
        f"only {walked} controls were walked (expected >= {_MIN_EXPECTED_WALKED}); "
        f"a regression may have shrunk the walked surface set"
    )


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_no_walked_control_is_below_the_click_target_floor_in_either_dimension(
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-119-AC-1

    On the host's native Qt platform plugin -- the one `just check` runs, where the
    application stylesheet pulls these classes onto Qt's QStyleSheetStyle and its metrics
    collapse below the floor -- no walked control is under 24 logical pixels in either
    dimension. The coverage floor is asserted first here, so it genuinely executes rather
    than sitting behind an assert that has never passed on a native run.
    """
    undersized, walked = _undersized_controls(mounted_app_surfaces, interactive_descendants)

    assert walked >= _MIN_EXPECTED_WALKED, (
        f"only {walked} controls were walked (expected >= {_MIN_EXPECTED_WALKED}); "
        f"a regression may have shrunk the walked surface set"
    )
    assert undersized == [], (
        "controls below the 24x24px click-target floor (08_ACCESSIBILITY_FLOOR.md §6):\n"
        + "\n".join(undersized)
    )
