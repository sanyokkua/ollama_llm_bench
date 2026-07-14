"""The per-verbosity field-selection matrix (§6.2).

The three sets are built so **Short ⊆ Normal ⊆ Verbose holds by construction**: Normal is
Short plus an extra set, Verbose is Normal plus a further extra set — never three
independently maintained lists.

The §6.2 table lists the "system prompt" and "user prompt (task)" rows separately from
"model response", but the actual ``RunLogEvent`` DTO (`02_DTOS_AND_ENUMS.md` §7.7) carries
only one input-text field (``prompt_excerpt``) and one output-text field
(``response_excerpt``) — there is no separate system/user prompt split on the event
payload. This module therefore collapses the two input-text table rows into the single
``FIELD_PROMPT`` field id, driven by ``prompt_excerpt``.
"""

from typing import Final

import structlog

from ollama_llm_bench.backend.domain import RunLogVerbosity

__all__: list[str] = [
    "FIELD_ERROR",
    "FIELD_JUDGE",
    "FIELD_MODEL",
    "FIELD_ORDER",
    "FIELD_PROMPT",
    "FIELD_PROVIDER",
    "FIELD_RESPONSE",
    "FIELD_RETRY",
    "FIELD_STAGE",
    "FIELD_TASK_ID",
    "FIELD_TIME_RANGE",
    "FIELD_TOKENS",
    "FIELD_TOTAL_TIME",
    "FIELD_TPS",
    "FIELD_TTFT",
    "resolve_verbosity_and_fields",
]

_logger = structlog.get_logger(__name__)

# Field identifiers, in the fixed §6.2 display order (timestamp and the kind tag are
# structural and always emitted first by the assembler — they are not members of this
# selection matrix).
FIELD_PROVIDER: Final = "provider"
FIELD_MODEL: Final = "model"
FIELD_TASK_ID: Final = "task"
FIELD_STAGE: Final = "stage"
FIELD_TIME_RANGE: Final = "time_range"
FIELD_PROMPT: Final = "prompt"
FIELD_RESPONSE: Final = "response"
FIELD_TTFT: Final = "ttft"
FIELD_TOTAL_TIME: Final = "total_time"
FIELD_TPS: Final = "tps"
FIELD_TOKENS: Final = "tokens"
FIELD_RETRY: Final = "retry"
FIELD_ERROR: Final = "error"
FIELD_JUDGE: Final = "judge"

FIELD_ORDER: Final[tuple[str, ...]] = (
    FIELD_PROVIDER,
    FIELD_MODEL,
    FIELD_TASK_ID,
    FIELD_STAGE,
    FIELD_TIME_RANGE,
    FIELD_PROMPT,
    FIELD_RESPONSE,
    FIELD_TTFT,
    FIELD_TOTAL_TIME,
    FIELD_TPS,
    FIELD_TOKENS,
    FIELD_RETRY,
    FIELD_ERROR,
    FIELD_JUDGE,
)

_SHORT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        FIELD_PROVIDER,
        FIELD_MODEL,
        FIELD_TASK_ID,
        FIELD_STAGE,
        FIELD_TIME_RANGE,
        FIELD_PROMPT,
        FIELD_RESPONSE,
        FIELD_RETRY,
        FIELD_ERROR,
        FIELD_JUDGE,
    }
)
_NORMAL_EXTRA_FIELDS: Final[frozenset[str]] = frozenset({FIELD_TOTAL_TIME})
_VERBOSE_EXTRA_FIELDS: Final[frozenset[str]] = frozenset({FIELD_TTFT, FIELD_TPS, FIELD_TOKENS})

_NORMAL_FIELDS: Final[frozenset[str]] = _SHORT_FIELDS | _NORMAL_EXTRA_FIELDS
_VERBOSE_FIELDS: Final[frozenset[str]] = _NORMAL_FIELDS | _VERBOSE_EXTRA_FIELDS

_FIELD_SETS_BY_VERBOSITY: Final[dict[RunLogVerbosity, frozenset[str]]] = {
    RunLogVerbosity.SHORT: _SHORT_FIELDS,
    RunLogVerbosity.NORMAL: _NORMAL_FIELDS,
    RunLogVerbosity.VERBOSE: _VERBOSE_FIELDS,
}


def resolve_verbosity_and_fields(
    verbosity: RunLogVerbosity,
) -> tuple[RunLogVerbosity, frozenset[str]]:
    """Return the effective verbosity and its selected field-id set (§6.2, §9).

    An unrecognized ``verbosity`` value falls back to ``NORMAL`` and logs one
    ``WARNING``-level, PII-free line — it never raises.

    Args:
        verbosity: The requested field density.

    Returns:
        A ``(effective_verbosity, selected_fields)`` pair; ``effective_verbosity`` is
        always a genuine ``RunLogVerbosity`` member.
    """
    fields = _FIELD_SETS_BY_VERBOSITY.get(verbosity)
    if fields is not None:
        return verbosity, fields
    _logger.warning("run_log_verbosity_unrecognized", verbosity=str(verbosity))
    return RunLogVerbosity.NORMAL, _NORMAL_FIELDS
