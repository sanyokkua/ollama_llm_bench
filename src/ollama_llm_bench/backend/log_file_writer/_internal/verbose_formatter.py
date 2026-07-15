"""Render one ``RunLogEvent`` at the full Verbose field density, for the run-log file.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/15_LOG_FORMATTING.md``
§7 — the run-log file always records the full Verbose field set regardless of the
on-screen ``ui.run_log_verbosity``. This formatter is independent of
``backend/log_formatting/`` (the on-screen HTML formatter): it renders one plain-text
line, not HTML, and carries no verbosity parameter because it always emits every
present field.
"""

from typing import Final

from ollama_llm_bench.backend.domain import RunLogEvent

__all__: list[str] = ["format_verbose_line"]

# The fixed field order this formatter emits, after the leading timestamp and kind.
_FIELD_NAMES: Final[tuple[str, ...]] = (
    "provider_id",
    "model_name",
    "task_id",
    "stage",
    "started_at",
    "finished_at",
    "total_time_ms",
    "ttft_ms",
    "tokens_per_second",
    "prompt_tokens",
    "completion_tokens",
    "prompt_excerpt",
    "response_excerpt",
    "retry_attempt",
    "retry_reason",
    "error_text",
    "judge_verdict",
    "judge_reasoning",
)


def _one_line(value: str) -> str:
    """Collapse an embedded newline/carriage-return so the record stays one physical line."""
    return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _render_value(value: object) -> str:
    """Render one field value: an enum-like member via ``.value``, else ``str()``."""
    rendered = value.value if hasattr(value, "value") else str(value)
    return _one_line(rendered)


def format_verbose_line(event: RunLogEvent) -> str:
    """Render ``event`` as one plain-text line at the full Verbose field density.

    Every field defined on ``RunLogEvent`` beyond the leading timestamp and kind is
    emitted in a fixed order when present; a field that is ``None`` on the event is
    omitted entirely — no empty placeholder is rendered (matching
    ``backend/log_formatting``'s own precedent). ``provider_id`` is rendered verbatim;
    resolving it to a display name is out of scope for this formatter.

    Args:
        event: The pipeline event to render; not mutated.

    Returns:
        A single physical line (no embedded ``\\n``/``\\r``), with no trailing newline.
    """
    segments = [_one_line(event.timestamp), _one_line(event.kind.value)]
    for field_name in _FIELD_NAMES:
        value = getattr(event, field_name)
        if value is None:
            continue
        segments.append(f"{field_name}={_render_value(value)}")
    return " ".join(segments)
