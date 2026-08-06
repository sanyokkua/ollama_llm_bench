"""The one definition of a modal dialog's Close button (08_ACCESSIBILITY_FLOOR §7.2).

The registry pins one objectName, accessible name, and tooltip for the dialog-close
control across every screen it appears on. Defining the button here rather than in each
dialog is what makes "repeated controls share one objectName pattern" true by
construction instead of by seven copies staying in agreement.
"""

from typing import Final

from PySide6.QtWidgets import QPushButton

__all__: list[str] = ["DIALOG_CLOSE_OBJECT_NAME", "build_dialog_close_button"]

DIALOG_CLOSE_OBJECT_NAME: Final = "dialog_close_button"
DIALOG_CLOSE_ACCESSIBLE_NAME: Final = "Close dialog"
DIALOG_CLOSE_TOOLTIP: Final = "Close"
DIALOG_CLOSE_TEXT: Final = "Close"


def build_dialog_close_button(*, role: str) -> QPushButton:
    """Build a dialog Close button carrying the registry's pinned identity.

    Args:
        role: The theme style role. Use ``"primary-button"`` when Close is the
            footer's only or right-most action, and ``"outlined-muted-button"``
            when it sits to the left of a distinct primary confirm.

    Returns:
        The button, unconnected -- the mounting dialog wires its own ``clicked``.
    """
    button = QPushButton(DIALOG_CLOSE_TEXT)
    button.setObjectName(DIALOG_CLOSE_OBJECT_NAME)
    button.setAccessibleName(DIALOG_CLOSE_ACCESSIBLE_NAME)
    button.setToolTip(DIALOG_CLOSE_TOOLTIP)
    button.setProperty("role", role)
    return button
