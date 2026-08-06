"""Unit tests for the shared dialog Close button (STORY-097)."""

from typing import TYPE_CHECKING

from pytestqt.qtbot import QtBot

from ollama_llm_bench.ui.shared import make_dialog_close_button

if TYPE_CHECKING:
    from PySide6.QtWidgets import QPushButton


def test_dialog_close_button_carries_the_pinned_identity(qtbot: QtBot) -> None:
    """The shared Close button reports the registry's pinned objectName, accessible
    name, and tooltip, so every dialog mounting it conforms by construction."""
    # Arrange / Act
    button = make_dialog_close_button()
    qtbot.addWidget(button)

    # Assert
    assert (button.objectName(), button.accessibleName(), button.toolTip()) == (
        "dialog_close_button",
        "Close dialog",
        "Close",
    )


def test_dialog_close_button_uses_the_requested_style_role(qtbot: QtBot) -> None:
    """A Close button sitting left of a distinct confirm takes the outlined-muted role;
    a Close button that is the footer's only action stays the filled primary."""
    # Arrange / Act
    beside_confirm = make_dialog_close_button(role="outlined-muted-button")
    qtbot.addWidget(beside_confirm)

    # Assert
    assert beside_confirm.property("role") == "outlined-muted-button"


def test_dialog_close_button_reads_close(qtbot: QtBot) -> None:
    """The button's visible text is `Close` -- the accessible name is the longer
    `Close dialog`, and the two are independent by design."""
    # Arrange / Act
    button: QPushButton = make_dialog_close_button()
    qtbot.addWidget(button)

    # Assert
    assert button.text() == "Close"
