"""E2E accessibility-floor check: every interactive element has a non-empty accessible name.

Proves the accessibility floor's §7/§10 verification row (08_ACCESSIBILITY_FLOOR.md).
"""

from collections.abc import Callable

from PySide6.QtWidgets import QWidget
import pytest

_MIN_EXPECTED_WALKED = 225


@pytest.mark.allow_qt_warnings  # offscreen plugin warns on propagateSizeHints()
def test_every_interactive_element_has_a_nonempty_accessible_name(
    mounted_app_surfaces: list[QWidget],
    interactive_descendants: Callable[[QWidget], list[QWidget]],
) -> None:
    """Proves: STORY-091-AC-2

    Every interactive element across the mounted application, the Settings dialog, and the
    seven shared modal dialogs -- especially every icon-only button -- reports a non-empty
    accessible name.
    """
    walked = [
        control for surface in mounted_app_surfaces for control in interactive_descendants(surface)
    ]
    unnamed = [
        f"{type(surface).__name__}({surface.objectName() or '<no objectName>'}) > "
        f"{type(control).__name__}({control.objectName() or '<no objectName>'})"
        for surface in mounted_app_surfaces
        for control in interactive_descendants(surface)
        if not control.accessibleName()
    ]
    assert unnamed == [], "controls with no accessible name:\n" + "\n".join(unnamed)
    assert len(walked) >= _MIN_EXPECTED_WALKED, (
        f"only {len(walked)} controls were walked (expected >= {_MIN_EXPECTED_WALKED}); "
        f"a regression may have shrunk the walked surface set"
    )
