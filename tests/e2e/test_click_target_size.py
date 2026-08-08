"""E2E accessibility-floor check: every clickable control has a >=24x24px hit area.

Proves the accessibility floor's §6/§10 verification row (08_ACCESSIBILITY_FLOOR.md).
"""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget
import pytest

_MIN_HIT_AREA_PX = 24
_MIN_EXPECTED_WALKED = 225


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
    walked = [
        control for surface in mounted_app_surfaces for control in interactive_descendants(surface)
    ]
    undersized = [
        f"{type(surface).__name__}({surface.objectName() or '<no objectName>'}) > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'}) "
        f"{control.width()}x{control.height()}"
        for surface in mounted_app_surfaces
        for control in interactive_descendants(surface)
        if control.width() < _MIN_HIT_AREA_PX or control.height() < _MIN_HIT_AREA_PX
    ]
    assert undersized == [], "controls below the 24x24px minimum hit area:\n" + "\n".join(
        undersized
    )
    assert len(walked) >= _MIN_EXPECTED_WALKED, (
        f"only {len(walked)} controls were walked (expected >= {_MIN_EXPECTED_WALKED}); "
        f"a regression may have shrunk the walked surface set"
    )
