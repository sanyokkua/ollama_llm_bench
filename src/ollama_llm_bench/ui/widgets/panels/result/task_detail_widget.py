"""TaskDetailWidget — renders full task detail for a selected BenchmarkResult."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.models import BenchmarkResult
from ollama_llm_bench.backend.services.result_html_renderer import build_result_html
from ollama_llm_bench.ui.style.chart_colors import PLACEHOLDER_TEXT_COLOR
from ollama_llm_bench.ui.style.tokens import get_tokens

logger = logging.getLogger(__name__)

_PLACEHOLDER_HTML: str = (
    f'<p style="color: {PLACEHOLDER_TEXT_COLOR}; font-style: italic;">Select a row to view task details.</p>'
)


class TaskDetailWidget(QWidget):
    """Displays the full detail of a single BenchmarkResult as styled HTML."""

    def __init__(self) -> None:
        """Initialise the widget with a read-only QTextBrowser and zero-margin layout."""
        super().__init__()
        self._text_browser: QTextBrowser = QTextBrowser()
        self._text_browser.setOpenExternalLinks(False)
        self._text_browser.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text_browser)
        self.clear()
        logger.debug("TaskDetailWidget initialised")

    def show_result(self, result: BenchmarkResult) -> None:
        """Render the full task detail as HTML in the text browser.

        Args:
            result: The BenchmarkResult to display.
        """
        self._text_browser.setHtml(self._build_html(result))

    def clear(self) -> None:
        """Show a placeholder message when no task is selected."""
        self._text_browser.setHtml(_PLACEHOLDER_HTML)

    def _build_html(self, result: BenchmarkResult) -> str:
        color_scheme = QGuiApplication.styleHints().colorScheme()
        theme = "light" if color_scheme == Qt.ColorScheme.Light else "dark"
        t = get_tokens(theme)
        return build_result_html(result, t)
