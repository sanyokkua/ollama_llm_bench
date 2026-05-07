"""TaskDetailWidget — renders full task detail for a selected BenchmarkResult."""

import html
import json
import logging

import markdown as md
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from ollama_llm_bench.backend.core.models import BenchmarkResult
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _plain_to_html(text: str) -> str:
        """Escape plain text and preserve line breaks for Qt HTML rendering."""
        return html.escape(text).replace("\n", "<br>")

    @staticmethod
    def _markdown_to_html(text: str) -> str:
        """Convert markdown text to HTML for Qt HTML rendering."""
        return md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])

    def _build_html(self, result: BenchmarkResult) -> str:
        """Build the full HTML representation of a BenchmarkResult.

        Args:
            result: Source data for the HTML document.

        Returns:
            A complete HTML string with inline styles derived from design tokens.
        """
        color_scheme = QGuiApplication.styleHints().colorScheme()
        theme = "light" if color_scheme == Qt.ColorScheme.Light else "dark"
        t = get_tokens(theme)
        sections: list[str] = []

        sections.append(self._header_section(result, t))

        if result.user_prompt_sent:
            sections.append(self._prompt_section(result, t))

        sections.append(self._response_section(result, t))
        sections.append(self._performance_section(result, t))
        sections.append(self._evaluation_section(result, t))

        error_html = self._error_section(result, t)
        if error_html:
            sections.append(error_html)

        keyword_html = self._keyword_section(result, t)
        if keyword_html:
            sections.append(keyword_html)

        if result.cosine_similarity is not None:
            sections.append(self._cosine_section(result, t))

        if result.judge_score is not None:
            sections.append(self._judge_section(result, t))

        body = f'<hr style="border: 1px solid {t["border"]}; margin: 8px 0;">'.join(sections)

        return (
            f'<html><body style="background: {t["bg_primary"]}; '
            f'font-family: {t["font_sans"]}; padding: 8px;">'
            f"{body}"
            f"</body></html>"
        )

    @staticmethod
    def _header_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return the provider/model/task identity header HTML."""
        s = f"color: {t['text_muted']}; font-size: 12px; margin-bottom: 8px; line-height: 1.7;"
        return (
            f'<div style="{s}">'
            f"<b>Provider:</b> {html.escape(result.provider_id)}<br>"
            f"<b>Type:</b> {html.escape(result.task_type or '—')}<br>"
            f"<b>Model:</b> {html.escape(result.model_name)}<br>"
            f"<b>Difficulty:</b> {html.escape(result.task_difficulty or '—')}<br>"
            f"<b>Task:</b> {html.escape(result.task_id)}"
            f"</div>"
        )

    @staticmethod
    def _prompt_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return the prompt HTML block."""
        return (
            f'<div style="color: {t["primary"]}; font-weight: bold; margin-top: 8px;">PROMPT</div>'
            f'<pre style="color: {t["text_secondary"]}; '
            f"font-family: {t['font_mono']}; font-size: 12px; margin: 4px 0 8px 0; "
            f"padding: 8px; background: {t['bg_secondary']}; border-radius: 4px; "
            f'white-space: pre-wrap; word-wrap: break-word;">'
            f"{html.escape(result.user_prompt_sent)}"
            f"</pre>"
        )

    @staticmethod
    def _response_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return the response HTML block, choosing sanitized over raw when available."""
        sanitized = result.sanitized_response
        raw = result.raw_response
        response_text: str | None = sanitized if sanitized else raw

        if response_text:
            content = (
                f'<div style="color: {t["text_primary"]}; font-size: 12px; '
                f"margin: 4px 0 8px 0; padding: 8px; background: {t['bg_secondary']}; "
                f'border-radius: 4px;">'
                f"{TaskDetailWidget._markdown_to_html(response_text)}"
                f"</div>"
            )
        else:
            content = f'<i style="color: {t["text_muted"]};">(no response)</i>'

        return f'<div style="color: {t["primary"]}; font-weight: bold; margin-top: 8px;">RESPONSE</div>{content}'

    @staticmethod
    def _performance_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return the performance metrics HTML row."""
        total_time = result.total_time_ms if result.total_time_ms is not None else "N/A"
        ttft = result.ttft_ms if result.ttft_ms is not None else "N/A"
        tps = f"{result.tokens_per_second:.1f}" if result.tokens_per_second is not None else "N/A"
        prompt_tok = result.prompt_tokens if result.prompt_tokens is not None else "N/A"
        completion_tok = result.completion_tokens if result.completion_tokens is not None else "N/A"
        return (
            f'<div style="color: {t["text_muted"]}; font-size: 11px; margin: 4px 0;">'
            f"Time: {total_time} ms &nbsp;|&nbsp; "
            f"TTFT: {ttft} ms &nbsp;|&nbsp; "
            f"Tokens/s: {tps} &nbsp;|&nbsp; "
            f"Prompt tokens: {prompt_tok} &nbsp;|&nbsp; "
            f"Completion tokens: {completion_tok}"
            f"</div>"
        )

    @staticmethod
    def _evaluation_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return the evaluation verdict and resolution layer HTML block."""
        verdict = result.final_verdict
        if verdict == "pass":
            verdict_color = t["success_text"]
        elif verdict == "fail":
            verdict_color = t["failure_text"]
        else:
            verdict_color = t["text_muted"]

        verdict_display = html.escape(verdict) if verdict else "—"
        resolution = html.escape(result.resolution_layer) if result.resolution_layer else "—"

        return (
            f'<div style="color: {t["primary"]}; font-weight: bold; margin-top: 8px;">EVALUATION</div>'
            f'<div style="color: {t["text_muted"]}; font-size: 12px;">'
            f'Verdict: <b style="color: {verdict_color};">{verdict_display}</b> &nbsp;|&nbsp; '
            f"Resolution Layer: {resolution}"
            f"</div>"
        )

    @staticmethod
    def _error_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return inference error HTML if an inference error occurred, else empty string."""
        if not result.has_inference_error:
            return ""
        error_msg = html.escape(result.inference_error_message or "")
        return (
            f'<div style="color: {t["failure_text"]}; margin-top: 6px;">'
            f"&#10060; <b>Inference Error:</b> {error_msg}"
            f"</div>"
        )

    @staticmethod
    def _parse_term_list(raw: str | None) -> list[str]:
        """Parse a JSON-encoded list of strings from a model field.

        Args:
            raw: JSON string representing a list, or None.

        Returns:
            Parsed list of strings, or empty list if None or malformed.
        """
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
            return []
        except (json.JSONDecodeError, TypeError):
            logger.debug("term_list_parse_failed", extra={"raw": raw})
            return []

    def _keyword_section(self, result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return keyword evaluation HTML block, or empty string when nothing to show."""
        parts: list[str] = []

        missing = self._parse_term_list(result.missing_exact_terms)
        if missing:
            terms = html.escape(", ".join(missing))
            parts.append(
                f'<div style="color: {t["warning"]}; margin-top: 6px;">'
                f"&#9888; <b>Missing required terms:</b> {terms}"
                f"</div>"
            )

        forbidden = self._parse_term_list(result.found_forbidden_terms)
        if forbidden:
            terms = html.escape(", ".join(forbidden))
            parts.append(
                f'<div style="color: {t["failure_text"]}; margin-top: 4px;">'
                f"&#128683; <b>Forbidden terms found:</b> {terms}"
                f"</div>"
            )

        return "".join(parts)

    @staticmethod
    def _cosine_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return cosine similarity HTML block."""
        similarity = result.cosine_similarity
        if similarity is None:
            return ""
        strategy = html.escape(result.cosine_strategy or "—")
        return (
            f'<div style="color: {t["text_muted"]}; margin-top: 4px;">'
            f"&#128208; Cosine similarity: <b>{similarity:.4f}</b> "
            f"(strategy: {strategy}, "
            f"auto_pass: {result.cosine_auto_pass}, resolved: {result.cosine_resolved})"
            f"</div>"
        )

    @staticmethod
    def _judge_section(result: BenchmarkResult, t: dict[str, str]) -> str:
        """Return judge score and reasoning HTML block."""
        score = result.judge_score
        if score is None:
            return ""

        if score >= 0.7:
            judge_color = t["success_text"]
        elif score >= 0.4:
            judge_color = t["warning"]
        else:
            judge_color = t["failure_text"]

        parts: list[str] = [
            f'<div style="color: {t["text_muted"]}; margin-top: 4px;">'
            f'&#9878; Judge score: <b style="color: {judge_color};">{score:.2f}</b>'
            f"</div>"
        ]

        if result.judge_reasoning:
            parts.append(
                f'<div style="color: {t["text_secondary"]}; margin-top: 4px; padding: 6px; '
                f'background: {t["bg_secondary"]}; border-radius: 4px; font-size: 11px;">'
                f"{TaskDetailWidget._markdown_to_html(result.judge_reasoning)}"
                f"</div>"
            )

        return "".join(parts)
