"""JudgeAnalysisWidget — displays the post-run LLM-generated prose summary."""

import logging

from PySide6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

_PLACEHOLDER_TEXT: str = (
    "No judge analysis available for this run.\n\n"
    "Judge analysis is generated automatically after a Full Grading run completes."
)
_PENDING_TEXT: str = "Generating judge analysis, please wait\u2026"
_HEADER_TEXT: str = "Judge Analysis"


class JudgeAnalysisWidget(QWidget):
    """Displays the LLM judge prose summary generated at the end of a full-grading run."""

    def __init__(self) -> None:
        """Initialise widget with a header label and a read-only text browser."""
        super().__init__()
        self._header: QLabel = QLabel(_HEADER_TEXT)
        self._header.setProperty("role", "heading")
        self._text_browser: QTextBrowser = QTextBrowser()
        self._text_browser.setOpenExternalLinks(False)
        self._text_browser.setPlaceholderText(_PLACEHOLDER_TEXT)
        self._text_browser.setReadOnly(True)
        self._setup_layout()
        self.clear()
        logger.debug("JudgeAnalysisWidget initialised")

    def show_pending(self) -> None:
        """Show a 'generating' placeholder while the judge model is running."""
        self._text_browser.setPlainText(_PENDING_TEXT)

    def show_summary(self, text: str) -> None:
        """Display the prose summary produced by the judge model.

        Args:
            text: Plain-text prose summary from the judge.
        """
        self._header.setText(_HEADER_TEXT)
        self._text_browser.setPlainText(text)

    def show_perf_analysis(self, text: str) -> None:
        """Display the run-level performance analysis produced by the judge model.

        Args:
            text: Plain-text performance analysis from the judge.
        """
        self._header.setText("Run-level performance analysis")
        self._text_browser.setPlainText(text)

    def clear(self) -> None:
        """Reset to the empty placeholder state."""
        self._header.setText(_HEADER_TEXT)
        self._text_browser.setPlainText(_PLACEHOLDER_TEXT)

    def _setup_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._header)
        layout.addWidget(self._text_browser)
