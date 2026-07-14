"""One function per §6.1 result-detail section.

`20_HTML_RENDERING.md` §6.1. Each function returns `str | None`; `None` means the
section is omitted entirely — never rendered as an empty element (AC-5).
"""

from ollama_llm_bench.backend.domain import (
    AttemptOutcome,
    BenchmarkResult,
    BenchmarkTask,
    RunMode,
)
from ollama_llm_bench.backend.html_rendering._internal.escaping import escape_html
from ollama_llm_bench.backend.html_rendering._internal.palette import _Palette, palette_for
from ollama_llm_bench.backend.html_rendering._internal.verdict_badge import render_verdict_badge
from ollama_llm_bench.backend.html_rendering.models import LogSeverity, UiTheme

_DASH = "—"


def _render_ms_as_seconds(value_ms: int | None) -> str:
    """Render a millisecond duration as seconds, 3 decimals, or a dash when unset."""
    return f"{value_ms / 1000:.3f}" if value_ms is not None else _DASH


def _render_tps(value: float | None) -> str:
    """Render tokens-per-second, 2 decimals, or a dash when unset."""
    return f"{value:.2f}" if value is not None else _DASH


def _render_count(value: int | None) -> str:
    """Render an integer count, or a dash when unset."""
    return str(value) if value is not None else _DASH


def _labelled_div(*, label: str, value: str) -> str:
    """Build one `Label: value` metadata line; both HTML-escaped."""
    return f"<div>{escape_html(label)}: {escape_html(value)}</div>"


def _text_block(*, label: str, text: str, palette: _Palette) -> str:
    """Build one labelled monospace block; escaped, line feeds preserved by `pre-wrap`."""
    return (
        f'<div style="margin:6px 0;"><div style="font-weight:600;">'
        f"{escape_html(label)}</div>"
        f'<pre style="background-color:{palette.monospace_bg};color:{palette.container_fg};'
        f'padding:6px;white-space:pre-wrap;word-break:break-word;">'
        f"{escape_html(text)}</pre></div>"
    )


def render_header_section(*, result: BenchmarkResult, task: BenchmarkTask, theme: UiTheme) -> str:
    """Render the header section (§6.1 step 1): identity, task descriptors, badge."""
    palette = palette_for(theme)
    lines = [
        _labelled_div(label="Task Id", value=task.task_id),
        _labelled_div(label="Task type", value=task.task_origin.value),
        _labelled_div(label="Category", value=f"{task.category} / {task.sub_category}"),
        _labelled_div(label="Difficulty", value=task.difficulty.value),
        _labelled_div(
            label="Provider / Model", value=f"{result.provider_name} / {result.model_name}"
        ),
        _labelled_div(label="Status", value=result.status.value),
    ]
    for label, raw_value in (
        ("Input size", task.input_size_label),
        ("Output size", task.output_size_label),
        ("Repeat index", None if task.repeat_index is None else str(task.repeat_index)),
    ):
        if raw_value is not None:
            lines.append(_labelled_div(label=label, value=raw_value))
    badge = render_verdict_badge(result=result, theme=theme)
    if badge is not None:
        lines.append(badge)
    body = "".join(lines)
    return (
        f'<div style="color:{palette.container_fg};border-bottom:1px solid '
        f'{palette.border};padding-bottom:8px;margin-bottom:8px;">{body}</div>'
    )


def render_task_section(*, task: BenchmarkTask) -> str:
    """Render the task section (§6.1 step 2): question, golden answer, criteria."""
    lines = [_labelled_div(label="Question", value=task.question)]
    if task.golden_answer is not None:
        lines.append(_labelled_div(label="Golden answer", value=task.golden_answer))
    if task.pass_criteria:
        lines.append(_labelled_div(label="Pass criteria", value=task.pass_criteria))
    if task.fail_criteria:
        lines.append(_labelled_div(label="Fail criteria", value=task.fail_criteria))
    if task.source_language is not None:
        lines.append(_labelled_div(label="Source language", value=task.source_language))
    if task.target_language is not None:
        lines.append(_labelled_div(label="Target language", value=task.target_language))
    if task.source_material is not None:
        lines.append(_labelled_div(label="Source material", value=task.source_material))
    return f'<div style="margin-bottom:8px;">{"".join(lines)}</div>'


def render_prompts_section(*, result: BenchmarkResult, theme: UiTheme) -> str | None:
    """Render the prompts section (§6.1 step 3), or `None` when neither prompt is set."""
    if result.system_prompt_sent is None and result.user_prompt_sent is None:
        return None
    palette = palette_for(theme)
    blocks: list[str] = []
    if result.system_prompt_sent is not None:
        blocks.append(
            _text_block(label="System prompt", text=result.system_prompt_sent, palette=palette)
        )
    if result.user_prompt_sent is not None:
        blocks.append(
            _text_block(label="User prompt", text=result.user_prompt_sent, palette=palette)
        )
    return f'<div style="margin-bottom:8px;">{"".join(blocks)}</div>'


def render_response_section(*, result: BenchmarkResult, theme: UiTheme) -> str | None:
    """Render the response section (§6.1 step 4), or `None` when no response is set."""
    if result.sanitized_response is None and result.raw_response is None:
        return None
    palette = palette_for(theme)
    blocks: list[str] = []
    if result.sanitized_response is not None:
        blocks.append(
            _text_block(label="Response", text=result.sanitized_response, palette=palette)
        )
    if result.has_thinking_block and result.raw_response is not None:
        blocks.append(
            _text_block(
                label="Raw response (with reasoning)", text=result.raw_response, palette=palette
            )
        )
    if result.response_char_length is not None:
        blocks.append(
            f'<div style="color:{palette.muted_fg};font-size:0.85em;">'
            f"{result.response_char_length} characters</div>"
        )
    return f'<div style="margin-bottom:8px;">{"".join(blocks)}</div>'


def render_performance_section(*, result: BenchmarkResult) -> str | None:
    """Render the performance section (§6.1 step 5); omitted only with zero metrics."""
    metrics = (
        result.ttft_ms,
        result.total_time_ms,
        result.tokens_per_second,
        result.prompt_tokens,
        result.completion_tokens,
    )
    if all(metric is None for metric in metrics):
        return None
    lines = [
        _labelled_div(label="TTFT (s)", value=_render_ms_as_seconds(result.ttft_ms)),
        _labelled_div(label="Total time (s)", value=_render_ms_as_seconds(result.total_time_ms)),
        _labelled_div(label="Tokens/second", value=_render_tps(result.tokens_per_second)),
        _labelled_div(label="Prompt tokens", value=_render_count(result.prompt_tokens)),
        _labelled_div(label="Response tokens", value=_render_count(result.completion_tokens)),
    ]
    return f'<div style="margin-bottom:8px;">{"".join(lines)}</div>'


def _render_term_table(*, result: BenchmarkResult) -> str | None:
    """Render the per-term outcome table, or `None` when `result.terms` is empty."""
    if not result.terms:
        return None
    header = "<tr><th>Term</th><th>Kind</th><th>Similarity</th></tr>"
    row_html: list[str] = []
    for term in result.terms:
        similarity = f"{term.similarity_score:.3f}" if term.similarity_score is not None else _DASH
        row_html.append(
            f"<tr><td>{escape_html(term.term_text)}</td>"
            f"<td>{escape_html(term.term_kind.value)}</td>"
            f"<td>{similarity}</td></tr>"
        )
    return f'<table style="border-collapse:collapse;">{header}{"".join(row_html)}</table>'


def render_grading_section(*, result: BenchmarkResult, run_mode: RunMode) -> str | None:
    """Render the grading section + per-term table (§6.1 step 6); `GRADED` only."""
    if run_mode is not RunMode.GRADED:
        return None
    cosine_text = (
        f"{result.cosine_similarity:.3f}" if result.cosine_similarity is not None else _DASH
    )
    lines = [
        _labelled_div(
            label="Keyword verdict",
            value=result.keyword_verdict.value if result.keyword_verdict is not None else _DASH,
        ),
        _labelled_div(label="Cosine score", value=cosine_text),
        _labelled_div(
            label="Cosine verdict",
            value=result.cosine_verdict.value if result.cosine_verdict is not None else _DASH,
        ),
        _labelled_div(
            label="Judge verdict",
            value=result.judge_verdict.value if result.judge_verdict is not None else _DASH,
        ),
        _labelled_div(
            label="Resolution layer",
            value=(result.resolution_layer.value if result.resolution_layer is not None else _DASH),
        ),
    ]
    if result.judge_reasoning is not None:
        lines.append(_labelled_div(label="Judge reasoning", value=result.judge_reasoning))
    term_table = _render_term_table(result=result)
    if term_table is not None:
        lines.append(term_table)
    return f'<div style="margin-bottom:8px;">{"".join(lines)}</div>'


def render_attempts_section(*, result: BenchmarkResult) -> str | None:
    """Render the attempts table (§6.1 step 7); omitted for one successful attempt."""
    attempts = result.attempts
    should_show = len(attempts) > 1 or any(
        attempt.outcome is not AttemptOutcome.SUCCESS for attempt in attempts
    )
    if not should_show:
        return None
    header = (
        "<tr><th>#</th><th>Timeout (ms)</th><th>Duration (ms)</th>"
        "<th>Outcome</th><th>Error</th></tr>"
    )
    row_html: list[str] = []
    for attempt in attempts:
        duration = _render_count(attempt.duration_ms)
        error_text = attempt.error_message if attempt.error_message is not None else ""
        row_html.append(
            f"<tr><td>{attempt.attempt_index}</td><td>{attempt.timeout_ms}</td>"
            f"<td>{escape_html(duration)}</td><td>{escape_html(attempt.outcome.value)}</td>"
            f"<td>{escape_html(error_text)}</td></tr>"
        )
    return f'<table style="border-collapse:collapse;">{header}{"".join(row_html)}</table>'


def render_error_section(*, result: BenchmarkResult, theme: UiTheme) -> str | None:
    """Render the error section (§6.1 step 8); shown only when the error fields are set."""
    if result.error_kind is None and result.error_message is None:
        return None
    palette = palette_for(theme)
    error_color = palette.severity_colors[LogSeverity.ERROR]
    kind_text = result.error_kind.value if result.error_kind is not None else _DASH
    message_text = result.error_message if result.error_message is not None else ""
    return (
        f'<div style="color:{error_color};border:1px solid {error_color};padding:6px;">'
        f"<div>Error kind: {escape_html(kind_text)}</div>"
        f"<div>{escape_html(message_text)}</div></div>"
    )
