"""``ErrorDialog`` -- the single generic blocking-error modal (STORY-070-AC-3..5, AC-7).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/error_dialog.md``
§4 (layout), §5 (three error patterns), §6-§7 (verbatim content, no redaction),
§8-§9 (default state, button behaviour), §12 (edge cases -- EC-ERR-6). Pure
presentation of a caller-supplied payload -- performs no redaction and derives
nothing (§7). Copy Details emits a ``GlobalMessageEvent`` confirmation/failure
toast (§9, EC-ERR-6).
"""

from typing import override

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import structlog

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import SIGNAL_GLOBAL_MESSAGE, EventBus, GlobalMessageEvent
from ollama_llm_bench.ui.common_dialogs._internal.theme_lookup import monospace_font
from ollama_llm_bench.ui.common_dialogs.models import ErrorDialogPattern, ErrorDialogPayload

__all__: list[str] = ["ErrorDialog"]

logger = structlog.get_logger(__name__)

_DETAILS_COPIED_MESSAGE = "Details copied."
_COULD_NOT_COPY_TO_CLIPBOARD_MESSAGE = "Could not copy to the clipboard."


class ErrorDialog(QDialog):
    """The single generic blocking Error dialog: recoverable / action-available / fatal."""

    def __init__(
        self,
        *,
        payload: ErrorDialogPayload,
        clipboard: Clipboard,
        event_bus: EventBus,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("common_dialogs.error")
        self.setWindowTitle(payload.title)
        self._payload = payload
        self._clipboard = clipboard
        self._event_bus = event_bus
        self._build_ui(payload)
        if payload.pattern is ErrorDialogPattern.FATAL:
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, on=False)
        logger.debug(
            "error_dialog_constructed",
            pattern=payload.pattern.value,
            has_detail=payload.detail is not None,
        )

    def _build_ui(self, payload: ErrorDialogPayload) -> None:
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        header = QHBoxLayout()
        glyph_label = QLabel("✕")
        glyph_label.setObjectName("common_dialogs.error.glyph")
        glyph_label.setProperty("role", "error-icon")
        header.addWidget(glyph_label)
        title_label = QLabel(payload.title)
        title_label.setObjectName("common_dialogs.error.title")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

        message_label = QLabel(payload.message)
        message_label.setObjectName("common_dialogs.error.message")
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        self._detail_edit: QTextEdit | None = None
        if payload.detail is not None:
            self._detail_edit = QTextEdit(payload.detail)
            self._detail_edit.setObjectName("common_dialogs.error.detail")
            self._detail_edit.setReadOnly(True)
            self._detail_edit.setProperty("role", "muted-caption")
            self._detail_edit.setFont(monospace_font())
            layout.addWidget(self._detail_edit)

        layout.addLayout(self._build_footer(payload))

    def _build_footer(self, payload: ErrorDialogPayload) -> QHBoxLayout:
        footer = QHBoxLayout()
        if payload.detail is not None:
            self.copy_details_button = QPushButton("Copy Details")
            self.copy_details_button.setObjectName("common_dialogs.error.copy_details_button")
            self.copy_details_button.setProperty("role", "outlined-muted-button")
            self.copy_details_button.clicked.connect(self._on_copy_details_clicked)
            footer.addWidget(self.copy_details_button)
        footer.addStretch()

        if payload.pattern is ErrorDialogPattern.ACTION_AVAILABLE and payload.action is not None:
            self.action_button = QPushButton(payload.action.label)
            self.action_button.setObjectName("common_dialogs.error.action_button")
            self.action_button.setProperty("role", "outlined-muted-button")
            self.action_button.clicked.connect(self._on_action_clicked)
            footer.addWidget(self.action_button)

        if payload.pattern is ErrorDialogPattern.FATAL:
            self.quit_button = QPushButton("Quit")
            self.quit_button.setObjectName("common_dialogs.error.quit_button")
            self.quit_button.setProperty("role", "destructive-button")
            self.quit_button.setDefault(True)
            self.quit_button.clicked.connect(self._on_quit_clicked)
            footer.addWidget(self.quit_button)
        else:
            self.close_button = QPushButton("Close")
            self.close_button.setObjectName("common_dialogs.error.close_button")
            self.close_button.setProperty("role", "primary-button")
            self.close_button.setDefault(True)
            self.close_button.clicked.connect(self.accept)
            footer.addWidget(self.close_button)
        return footer

    @override
    def reject(self) -> None:
        """Ignore Escape for the fatal pattern (§8: "Escape does nothing"); otherwise
        the default ``QDialog.reject()`` behaviour applies."""
        if self._payload.pattern is ErrorDialogPattern.FATAL:
            logger.debug("error_dialog_escape_ignored_fatal_pattern")
            return
        super().reject()

    def _on_copy_details_clicked(self) -> None:
        logger.debug("error_dialog_copy_details_clicked")
        detail = self._payload.detail
        if detail is None:
            return
        try:
            self._clipboard.copy_text(detail)
        except OsAdapterError as exc:
            logger.warning("error_dialog_copy_details_failed", error=str(exc))
            self._emit_toast(_COULD_NOT_COPY_TO_CLIPBOARD_MESSAGE, severity="error")
            return
        self._emit_toast(_DETAILS_COPIED_MESSAGE, severity="info")

    def _emit_toast(self, text: str, *, severity: str) -> None:
        self._event_bus.emit(
            SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text=text, severity=severity)
        )

    def _on_action_clicked(self) -> None:
        logger.debug("error_dialog_action_clicked")
        action = self._payload.action
        if action is not None:
            action.callback()

    def _on_quit_clicked(self) -> None:
        logger.debug("error_dialog_quit_clicked")
        quit_callback = self._payload.quit_callback
        if quit_callback is not None:
            quit_callback()
