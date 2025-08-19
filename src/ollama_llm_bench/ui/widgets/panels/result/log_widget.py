import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QScrollBar, QTextEdit, QVBoxLayout, QWidget

from ollama_llm_bench.core.ui_controllers import LogWidgetControllerApi

logger = logging.getLogger(__name__)


class LogWidget(QWidget):
    """
    Widget for displaying application logs with auto-scrolling behavior.
    Automatically scrolls to bottom when new messages arrive, unless user has scrolled up.
    """

    def __init__(self, controller: LogWidgetControllerApi) -> None:
        """
        Initialize the log widget.

        Args:
            controller: Controller API for handling log events.
        """
        super().__init__()
        self._controller = controller
        self._setup_ui()
        self._setup_signals()

    def _setup_ui(self) -> None:
        """
        Initialize and configure the log display components.
        Creates a text display area and a clean button for log management.
        """
        self._clean_button = QPushButton("Clean")
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout = QVBoxLayout()
        layout.addWidget(self._clean_button)
        layout.addWidget(self._text_edit)
        self.setLayout(layout)

    def _setup_signals(self) -> None:
        """
        Connect UI events to appropriate handlers and controller subscriptions.
        """
        self._clean_button.clicked.connect(self._clear_log_display)
        self._controller.subscribe_to_log_clear(self._clear_log_display)
        self._controller.subscribe_to_log_append(self._append_log_entry)

    def _clear_log_display(self) -> None:
        """
        Clear all content from the log display area.
        """
        logger.debug("Clearing log display")
        self._text_edit.clear()

    def _append_log_entry(self, text: str) -> None:
        """
        Append a new log entry to the display with proper formatting and scrolling behavior.

        Args:
            text: Log message to append.
        """
        # Process text efficiently with single append operation
        clean_text = text.rstrip("\n")
        self._text_edit.append(f"{clean_text}\n")

        # Only scroll to bottom if user is already viewing latest logs
        self._scroll_to_bottom_if_needed()

    def _scroll_to_bottom_if_needed(self) -> None:
        """
        Scroll the log view to the bottom if the user is currently viewing the latest entries.
        Prevents disrupting the user when they are reviewing older log content.
        """
        scrollbar: Optional[QScrollBar] = self._text_edit.verticalScrollBar()
        if not scrollbar:
            return

        # Only auto-scroll if user is within 10 lines of the bottom
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
