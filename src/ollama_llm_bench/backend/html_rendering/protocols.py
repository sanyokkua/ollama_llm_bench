"""`ResultHtmlRenderer` — this module's swap point (`20_HTML_RENDERING.md` §2.1)."""

from typing import Protocol

from ollama_llm_bench.backend.html_rendering.models import (
    LogEntry,
    ResultDetailRenderRequest,
    UiTheme,
)


class ResultHtmlRenderer(Protocol):
    """Renders a `BenchmarkResult`/`BenchmarkTask` pair and a `LogEntry` into
    themed HTML fragments.

    Both render methods are fast-synchronous and, by convention, GUI-thread-only
    (§9): `set_theme` and the render operations are not synchronized against each
    other, so all three must be called from the same thread. The service does not
    redact — free-text fields are HTML-escaped and written verbatim (§6.4).
    """

    def render_result_detail(self, request: ResultDetailRenderRequest) -> str:
        """Render the ordered result-detail HTML fragment (§6.1).

        fast-synchronous, GUI-thread-only by convention.

        Raises:
            icontract.errors.ViolationError: `request.task.task_id` does not
                match `request.result.task_id` (§8) — a programmer error; the
                caller must pair the result with its own task.
        """
        ...

    def render_log_line(self, entry: LogEntry) -> str:
        """Render one compact log-line HTML fragment (§6.2).

        fast-synchronous, GUI-thread-only by convention.
        """
        ...

    def set_theme(self, theme: UiTheme) -> None:
        """Record the active `UiTheme` for every subsequent render (§6.5).

        fast-synchronous, GUI-thread-only by convention. Called once at startup
        and again whenever the user switches theme.
        """
        ...
