"""Public functions for the error-taxonomy and redaction module.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md``
§7 (the API surface).
"""

import icontract

from ollama_llm_bench.backend.errors._internal.redaction import (
    _LENGTH_CAP,
    redact_for_log_impl,
    redact_impl,
)

__all__: list[str] = [
    "redact",
    "redact_for_log",
]

_TRUNCATION_SUFFIX_MAX_LEN = 64  # generous bound on " …[truncated, N more characters]"


@icontract.ensure(
    lambda result: len(result) <= _LENGTH_CAP + _TRUNCATION_SUFFIX_MAX_LEN,
    "the returned text must respect the 4000-character length cap plus a bounded "
    "truncation suffix — a violation here means this module's own substitution/cap "
    "implementation is broken, not that the input was malformed",
)
def redact(text: str | None) -> str:
    """Mask every known secret pattern in ``text``, then cap length at 4000 chars.

    Used by provider adapters when wrapping an SDK exception into
    ``AppError.message`` before it is placed on the exception (§7.1). ``None`` or an
    empty string is a sanctioned input (EC-RD-5), not a contract violation — it
    returns an empty string.

    Args:
        text: The text to scrub, or ``None``.

    Returns:
        The redacted, length-capped text; ``""`` if ``text`` is ``None`` or empty.
    """
    return redact_impl(text)


@icontract.require(
    lambda method_name: isinstance(method_name, str),
    "method_name is supplied by this codebase's own structlog wiring, never by "
    "external input — a non-str value here is a programmer error in the logging "
    "setup, not a malformed log record",
)
@icontract.ensure(
    lambda result: isinstance(result, dict),
    "the processor must always return a dict — a structlog processor pipeline "
    "invariant this implementation itself owns",
)
def redact_for_log(
    logger: object, method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    """Redact a structured log record before it reaches the ``app.*`` stream.

    Installed as the ``app.*`` namespace's structlog processor (§7.2) — never
    ``run.*``. Two-step behaviour: (1) replace any never-log-key field's value with
    ``<redacted>`` regardless of shape; (2) run the remaining field values through
    the same regex denylist ``redact()`` uses, then apply the length cap.

    Typed structurally to match a structlog processor's call shape without
    importing ``structlog`` itself — ``backend/errors/`` may import only the
    standard library and ``msgspec``.

    Args:
        logger: The bound logger instance (structlog processor call shape; unused).
        method_name: The log method name that produced this record (e.g. ``"info"``).
        event_dict: The structured record's fields.

    Returns:
        A new dict with every never-log field replaced and every remaining string
        field passed through the regex denylist and length cap.
    """
    return redact_for_log_impl(logger, method_name, event_dict)
