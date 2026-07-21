"""The read-only YAML preview side panel and its Copy YAML action (STORY-069-AC-5;
``description.md`` §3.6; EC-WS-3/EC-TE-12).

A read-only ``QPlainTextEdit`` (never ``QTextBrowser``) in the pane's monospace font
role, matching ``golden_answer``'s font choice (``_internal/theme_lookup.py``).
Content is pushed by the controller, already materialized through the real
``YamlFormatter`` (``_internal/buffer.py``'s scratch-file seam) -- this widget never
serializes or parses YAML itself.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ollama_llm_bench.ui.task_editor._internal.theme_lookup import monospace_font

__all__: list[str] = ["YamlPreviewWidget"]

_SAVE_DISABLED_NOTE = "Save is disabled while this file has errors."


class YamlPreviewWidget(QWidget):
    """Passive read-only YAML preview panel; forwards Copy YAML via a signal."""

    copy_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("task_editor.yaml_preview")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("YAML preview")
        title.setObjectName("task_editor.yaml_preview.title")
        header.addWidget(title)
        header.addStretch()
        self._copy_button = QPushButton("Copy YAML")
        self._copy_button.setObjectName("task_editor.yaml_preview.copy")
        self._copy_button.clicked.connect(self.copy_clicked.emit)
        header.addWidget(self._copy_button)
        layout.addLayout(header)

        self._text = QPlainTextEdit()
        self._text.setObjectName("task_editor.yaml_preview.text")
        self._text.setReadOnly(True)
        self._text.setFont(monospace_font())
        layout.addWidget(self._text)

        self._disabled_note = QLabel(_SAVE_DISABLED_NOTE)
        self._disabled_note.setObjectName("task_editor.yaml_preview.disabled_note")
        self._disabled_note.setVisible(False)
        layout.addWidget(self._disabled_note)

    def set_preview_text(self, text: str) -> None:
        """Push newly materialized preview text (debounced by the controller)."""
        self._text.setPlainText(text)

    def set_save_disabled_note_visible(self, *, visible: bool) -> None:
        """Show/hide the "Save is disabled while this file has errors" note
        (EC-WS-3/EC-TE-12)."""
        self._disabled_note.setVisible(visible)

    def preview_text(self) -> str:
        """Return the currently displayed preview text (for the Copy YAML action)."""
        return self._text.toPlainText()
