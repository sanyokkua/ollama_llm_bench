"""RenameRunDialog — validation dialog for renaming a benchmark run."""

from __future__ import annotations

import re
from typing import Final

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

_MAX_LEN: Final[int] = 80
_CONTROL_CHAR_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x1f\x7f]")


class RenameRunDialog(QDialog):
    """Dialog for renaming a benchmark run with inline validation.

    Validates that the new name is non-empty, within 80 characters, free of
    control characters, and not a case-insensitive duplicate of an existing name.
    The OK button is disabled until the input passes all validation rules.
    """

    def __init__(
        self,
        *,
        current_name: str,
        existing_names: frozenset[str],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the rename dialog.

        Args:
            current_name: The run's current display name (pre-fills the input field).
            existing_names: Case-folded names already in use (used for duplicate check).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._existing_names = existing_names

        self.setWindowTitle("Rename Run")
        self.setMinimumWidth(400)

        self._line_edit = QLineEdit(current_name)
        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        self._btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._ok_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("New name:"))
        layout.addWidget(self._line_edit)
        layout.addWidget(self._error_label)
        layout.addWidget(self._btn_box)

        self._line_edit.textChanged.connect(self._validate)
        self._validate(current_name)

    @property
    def new_name(self) -> str:
        """Return the validated, stripped new name."""
        return self._line_edit.text().strip()

    def _validate(self, _text: str) -> None:
        """Run all validation rules and update the error label and OK button state."""
        text = self._line_edit.text().strip()
        error = self._find_error(text)
        if error:
            self._error_label.setText(error)
            self._error_label.setVisible(True)
            if self._ok_btn is not None:
                self._ok_btn.setEnabled(False)
        else:
            self._error_label.setVisible(False)
            if self._ok_btn is not None:
                self._ok_btn.setEnabled(True)

    def _find_error(self, text: str) -> str | None:
        """Return an error message string if validation fails, else None."""
        if not text:
            return "Name must not be empty."
        if len(text) > _MAX_LEN:
            return f"Name must be {_MAX_LEN} characters or fewer."
        if _CONTROL_CHAR_RE.search(text):
            return "Name must not contain control characters."
        if text.casefold() in self._existing_names:
            return "A run with this name already exists."
        return None
