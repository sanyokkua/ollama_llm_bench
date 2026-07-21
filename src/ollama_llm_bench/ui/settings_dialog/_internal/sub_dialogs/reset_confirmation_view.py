"""The Reset-confirmation sub-dialog
(``06_Settings_Dialog/sub_dialogs/reset_confirmation.md``).

Note: the theme module's role catalog (``ui/theme/_internal/stylesheet_builder.py``)
does not yet define a distinct "destructive" button role (out of this story's
``ui/settings_dialog/`` scope to add) -- the Reset button uses the established
``primary-button`` role (the emphasized/default action) rather than an
unstyled custom role, pending a follow-up theme-module story.
"""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ollama_llm_bench.ui.settings_dialog._internal.sub_dialogs.reset_confirmation_select import (
    RESET_CONFIRMATION_BODY_TEXT,
)

__all__: list[str] = ["ResetConfirmationDialog", "make_reset_confirmation_dialog"]


class ResetConfirmationDialog(QDialog):
    """Warning modal in front of the destructive Reset to Defaults action."""

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settings_dialog.reset_confirmation")
        self.setWindowTitle("Reset all settings to factory defaults?")
        self.confirmed = False
        self._build_ui()

    def _build_ui(self) -> None:
        body_label = QLabel(RESET_CONFIRMATION_BODY_TEXT)
        body_label.setWordWrap(True)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("settings_dialog.reset_confirmation.cancel")
        self.cancel_button.setProperty("role", "outlined-muted-button")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        self.reset_button = QPushButton("Reset")
        self.reset_button.setObjectName("settings_dialog.reset_confirmation.reset")
        self.reset_button.setProperty("role", "primary-button")
        self.reset_button.clicked.connect(self._on_reset_clicked)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.reset_button)

        layout = QVBoxLayout(self)
        layout.addWidget(body_label)
        layout.addLayout(footer_layout)

    def _on_cancel_clicked(self) -> None:
        self.confirmed = False
        self.reject()

    def _on_reset_clicked(self) -> None:
        self.confirmed = True
        self.accept()


def make_reset_confirmation_dialog(*, parent: QWidget | None = None) -> ResetConfirmationDialog:
    """Construct the Reset-confirmation sub-dialog.

    Args:
        parent: The Settings dialog this sub-dialog opens on top of, if any.

    Returns:
        The dialog, not yet shown; the caller calls ``.exec()`` then reads
        ``.confirmed``.
    """
    return ResetConfirmationDialog(parent=parent)
