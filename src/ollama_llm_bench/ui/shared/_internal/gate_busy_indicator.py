"""The one definition of the gate-busy indicator strip (08_ACCESSIBILITY_FLOOR §7.2).

Shown while the application-wide single-inference gate is held by some other activity,
to explain why a control is temporarily disabled. The registry pins the identity
attributes; the visible sentence stays the caller's, because each surface's wording is
pinned separately by that surface's own specification.

Deliberately not animated. The registry table calls this a "spinner", but every mockup
draws a static strip, and ADR-0018 retired support for the operating system's
reduced-motion preference -- a looping animation would have no way to be switched off.
"""

from typing import Final

from PySide6.QtWidgets import QLabel

__all__: list[str] = ["GATE_BUSY_OBJECT_NAME", "build_gate_busy_indicator"]

GATE_BUSY_OBJECT_NAME: Final = "gate_busy_indicator"
GATE_BUSY_ACCESSIBLE_NAME: Final = "Inference in flight — controls temporarily disabled"
GATE_BUSY_TOOLTIP: Final = "An inference is in flight; please wait."


def build_gate_busy_indicator(*, message: str) -> QLabel:
    """Build a hidden gate-busy strip showing `message`.

    Args:
        message: The sentence the mounting surface's own specification pins.

    Returns:
        The strip, hidden -- the mounting surface reveals it when the gate is held.
    """
    strip = QLabel(message)
    strip.setObjectName(GATE_BUSY_OBJECT_NAME)
    strip.setAccessibleName(GATE_BUSY_ACCESSIBLE_NAME)
    strip.setToolTip(GATE_BUSY_TOOLTIP)
    strip.setProperty("role", "info-callout")
    strip.setWordWrap(True)
    strip.setVisible(False)
    return strip
