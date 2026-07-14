"""Compact single-line log fragment builder (`20_HTML_RENDERING.md` §6.2)."""

from ollama_llm_bench.backend.html_rendering._internal.escaping import escape_html
from ollama_llm_bench.backend.html_rendering._internal.palette import palette_for
from ollama_llm_bench.backend.html_rendering.models import LogEntry, UiTheme


def render_log_line(*, entry: LogEntry, theme: UiTheme) -> str:
    """Render one compact log-line HTML fragment: timestamp, severity tag, chips, message (§6.2)."""
    palette = palette_for(theme)
    severity_color = palette.severity_colors[entry.severity]
    parts = [
        f'<span style="color:{palette.muted_fg};">{escape_html(entry.timestamp)}</span>',
        f'<span style="color:{severity_color};font-weight:600;">'
        f"{escape_html(entry.severity.value.upper())}</span>",
    ]
    for chip_value in (entry.provider_id, entry.model_name, entry.task_id):
        if chip_value is not None:
            parts.append(
                f'<span style="color:{palette.muted_fg};background-color:'
                f'{palette.monospace_bg};border-radius:3px;padding:0 4px;">'
                f"{escape_html(chip_value)}</span>"
            )
    parts.append(f"<span>{escape_html(entry.message)}</span>")
    return f'<div style="white-space:nowrap;">{" ".join(parts)}</div>'
