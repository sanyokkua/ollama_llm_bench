"""Concrete `ResultHtmlRenderer` (`20_HTML_RENDERING.md` §6.1, §6.2, §6.5)."""

import icontract

from ollama_llm_bench.backend.html_rendering._internal.log_line import (
    render_log_line as _render_log_line,
)
from ollama_llm_bench.backend.html_rendering._internal.palette import palette_for
from ollama_llm_bench.backend.html_rendering._internal.sections import (
    render_attempts_section,
    render_error_section,
    render_grading_section,
    render_header_section,
    render_performance_section,
    render_prompts_section,
    render_response_section,
    render_task_section,
)
from ollama_llm_bench.backend.html_rendering.models import (
    LogEntry,
    ResultDetailRenderRequest,
    UiTheme,
)


class _ResultHtmlRendererImpl:
    """`ResultHtmlRenderer` whose only state is the recorded `UiTheme` (§6.5, §7).

    `set_theme` and the render methods are not synchronized against each other by
    design — every caller lives on the GUI thread (§9).
    """

    def __init__(self, *, initial_theme: UiTheme) -> None:
        self._theme = initial_theme

    def set_theme(self, theme: UiTheme) -> None:
        self._theme = theme

    @icontract.require(
        lambda request: request.task.task_id == request.result.task_id,
        "request.task must be the task request.result executed — the caller "
        "(the Details tab controller) pairs them before invoking the renderer; a "
        "mismatch here means a bug in the calling code, not a user mistake (§8)",
    )
    def render_result_detail(self, request: ResultDetailRenderRequest) -> str:
        result = request.result
        task = request.task
        theme = self._theme
        sections: list[str | None] = [
            render_header_section(result=result, task=task, theme=theme),
            render_task_section(task=task),
            render_prompts_section(result=result, theme=theme),
            render_response_section(result=result, theme=theme),
            render_performance_section(result=result),
            render_grading_section(result=result, run_mode=request.run_mode),
            render_attempts_section(result=result),
            render_error_section(result=result, theme=theme),
        ]
        body = "".join(section for section in sections if section is not None)
        palette = palette_for(theme)
        return (
            f'<div style="background-color:{palette.container_bg};'
            f'color:{palette.container_fg};padding:8px;">{body}</div>'
        )

    def render_log_line(self, entry: LogEntry) -> str:
        return _render_log_line(entry=entry, theme=self._theme)
