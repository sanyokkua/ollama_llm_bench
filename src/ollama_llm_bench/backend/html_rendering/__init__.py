"""HTML renderer — string output; Qt-free.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/20_HTML_RENDERING.md``.

Converts a ``BenchmarkResult`` (paired with its ``BenchmarkTask``) into the
ordered, themed result-detail HTML fragment shown in the Details tab, and a
``LogEntry`` into a compact log-line HTML fragment. Every value sourced from a
domain record, task file, model output, or provider message is HTML-escaped
before concatenation, so no untrusted input can inject markup. Pure, stateless
apart from the recorded ``UiTheme``; performs no I/O and applies no redaction.
"""

from ollama_llm_bench.backend.html_rendering.api import make_result_html_renderer
from ollama_llm_bench.backend.html_rendering.models import (
    LogEntry,
    LogSeverity,
    ResultDetailRenderRequest,
    UiTheme,
)
from ollama_llm_bench.backend.html_rendering.protocols import ResultHtmlRenderer

__all__: list[str] = [
    "LogEntry",
    "LogSeverity",
    "ResultDetailRenderRequest",
    "ResultHtmlRenderer",
    "UiTheme",
    "make_result_html_renderer",
]
