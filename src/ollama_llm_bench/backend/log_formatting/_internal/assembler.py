"""Assemble a formatted line: tone -> fields -> extract -> escape -> truncate -> join (§6.1, §6.6).

The final fragment is ``timestamp · <span class="tone-...">TAG</span> · field · field ...``
— the timestamp, then the tone-classed kind tag, then each selected-and-present field as
``label: value``, all joined by a thin middot (``" · "``, U+00B7) separator, per the fixed
§6.2 field order. A field selected by the verbosity but absent from the event's payload is
simply omitted — no empty placeholder (§9). The input ``event`` is never mutated.
"""

from collections.abc import Callable

from ollama_llm_bench.backend.domain import RunLogEvent, RunLogVerbosity
from ollama_llm_bench.backend.log_formatting._internal.escaping import escape_and_normalize
from ollama_llm_bench.backend.log_formatting._internal.excerpt import truncate_escaped
from ollama_llm_bench.backend.log_formatting._internal.fields import (
    FIELD_ERROR,
    FIELD_JUDGE,
    FIELD_MODEL,
    FIELD_ORDER,
    FIELD_PROMPT,
    FIELD_PROVIDER,
    FIELD_RESPONSE,
    FIELD_RETRY,
    FIELD_STAGE,
    FIELD_TASK_ID,
    FIELD_TIME_RANGE,
    FIELD_TOKENS,
    FIELD_TOTAL_TIME,
    FIELD_TPS,
    FIELD_TTFT,
    resolve_verbosity_and_fields,
)
from ollama_llm_bench.backend.log_formatting._internal.tone import (
    resolve_tag_label,
    resolve_tone,
    tone_class,
)

__all__: list[str] = ["assemble"]

_MIDDOT_SEPARATOR = " · "

_FieldRenderer = Callable[[RunLogEvent, RunLogVerbosity], str | None]


def assemble(event: RunLogEvent, *, verbosity: RunLogVerbosity) -> str:
    """Render ``event`` at ``verbosity`` into one middot-joined HTML fragment (§6.6).

    Args:
        event: The pipeline event to render; read-only, never mutated.
        verbosity: The requested field density; an unrecognized value falls back to
            ``NORMAL`` (§9).

    Returns:
        A single-line HTML fragment: the timestamp, the tone-classed kind tag, then
        every selected-and-present field, middot-joined.
    """
    effective_verbosity, selected_fields = resolve_verbosity_and_fields(verbosity)
    tone = resolve_tone(event.kind)
    tag_label = resolve_tag_label(event.kind)
    kind_tag = f'<span class="{tone_class(tone)}">{tag_label}</span>'
    parts: list[str] = [event.timestamp, kind_tag]
    parts.extend(_render_selected_fields(event, effective_verbosity, selected_fields))
    return _MIDDOT_SEPARATOR.join(parts)


def _render_selected_fields(
    event: RunLogEvent, effective_verbosity: RunLogVerbosity, selected_fields: frozenset[str]
) -> list[str]:
    rendered: list[str] = []
    for field_id in FIELD_ORDER:
        if field_id not in selected_fields:
            continue
        value = _FIELD_RENDERERS[field_id](event, effective_verbosity)
        if value is not None:
            rendered.append(value)
    return rendered


def _render_provider(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.provider_id is None:
        return None
    return f"provider: {escape_and_normalize(event.provider_id)}"


def _render_model(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.model_name is None:
        return None
    return f"model: {escape_and_normalize(event.model_name)}"


def _render_task(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.task_id is None:
        return None
    return f"task: {escape_and_normalize(event.task_id)}"


def _render_stage(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.stage is None:
        return None
    return f"stage: {event.stage}"


def _render_time_range(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.started_at is not None and event.finished_at is not None:
        return f"time: {event.started_at} → {event.finished_at}"
    if event.started_at is not None:
        return f"time: started {event.started_at}"
    if event.finished_at is not None:
        return f"time: finished {event.finished_at}"
    return None


def _render_counts(char_count: int, token_count: int | None) -> str:
    """Render the char/token "counts" pair for a prompt/response field (§6.2, §9).

    A ``None`` token count (the provider transport did not report one) is omitted
    gracefully — the character count alone is shown, never a placeholder.
    """
    if token_count is None:
        return f"{char_count} chars"
    return f"{char_count} chars, {token_count} tokens"


def _render_text_field(
    raw: str | None, token_count: int | None, *, effective_verbosity: RunLogVerbosity
) -> str | None:
    if raw is None:
        return None
    counts = _render_counts(len(raw), token_count)
    if effective_verbosity is RunLogVerbosity.SHORT:
        return counts
    escaped = escape_and_normalize(raw)
    if effective_verbosity is RunLogVerbosity.NORMAL:
        return f"{truncate_escaped(escaped)} ({counts})"
    return f"{escaped} ({counts})"


def _render_prompt(event: RunLogEvent, verbosity: RunLogVerbosity) -> str | None:
    value = _render_text_field(
        event.prompt_excerpt, event.prompt_tokens, effective_verbosity=verbosity
    )
    return None if value is None else f"prompt: {value}"


def _render_response(event: RunLogEvent, verbosity: RunLogVerbosity) -> str | None:
    value = _render_text_field(
        event.response_excerpt, event.completion_tokens, effective_verbosity=verbosity
    )
    return None if value is None else f"response: {value}"


def _render_ttft(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.ttft_ms is None:
        return None
    return f"ttft: {event.ttft_ms}ms"


def _render_total_time(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.total_time_ms is None:
        return None
    return f"total: {event.total_time_ms}ms"


def _render_tps(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.tokens_per_second is None:
        return None
    return f"tps: {event.tokens_per_second:.2f}"


def _render_tokens(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    parts: list[str] = []
    if event.prompt_tokens is not None:
        parts.append(f"prompt {event.prompt_tokens}")
    if event.completion_tokens is not None:
        parts.append(f"completion {event.completion_tokens}")
    if not parts:
        return None
    return f"tokens: {' / '.join(parts)}"


def _render_retry(event: RunLogEvent, verbosity: RunLogVerbosity) -> str | None:
    reason = escape_and_normalize(event.retry_reason) if event.retry_reason is not None else None
    if verbosity is RunLogVerbosity.SHORT:
        if event.retry_attempt is None:
            return None
        return f"attempts: {event.retry_attempt}"
    if verbosity is RunLogVerbosity.NORMAL:
        if reason is None:
            return None
        return f"retry: {reason}"
    parts: list[str] = []
    if event.retry_attempt is not None:
        parts.append(f"attempts: {event.retry_attempt}")
    if reason is not None:
        parts.append(f"reason: {reason}")
    if not parts:
        return None
    return _MIDDOT_SEPARATOR.join(parts)


def _render_error(event: RunLogEvent, _verbosity: RunLogVerbosity) -> str | None:
    if event.error_text is None:
        return None
    return f"error: {escape_and_normalize(event.error_text)}"


def _render_judge(event: RunLogEvent, verbosity: RunLogVerbosity) -> str | None:
    if event.judge_verdict is None:
        return None
    verdict_text = f"verdict: {event.judge_verdict.value.upper()}"
    if verbosity is RunLogVerbosity.SHORT:
        return verdict_text
    if event.judge_reasoning is None:
        return verdict_text
    reasoning = escape_and_normalize(event.judge_reasoning)
    return f"{verdict_text} · reasoning: {reasoning}"


_FIELD_RENDERERS: dict[str, _FieldRenderer] = {
    FIELD_PROVIDER: _render_provider,
    FIELD_MODEL: _render_model,
    FIELD_TASK_ID: _render_task,
    FIELD_STAGE: _render_stage,
    FIELD_TIME_RANGE: _render_time_range,
    FIELD_PROMPT: _render_prompt,
    FIELD_RESPONSE: _render_response,
    FIELD_TTFT: _render_ttft,
    FIELD_TOTAL_TIME: _render_total_time,
    FIELD_TPS: _render_tps,
    FIELD_TOKENS: _render_tokens,
    FIELD_RETRY: _render_retry,
    FIELD_ERROR: _render_error,
    FIELD_JUDGE: _render_judge,
}
