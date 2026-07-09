"""The secret-redaction implementation.

Source of truth: ``docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md``
§3 (the regex denylist), §4 (the never-log key-name list), §5 (the length cap), §7
(the API surface), §8 (order of operations), §10 (test cases), §11 (edge cases).

Scope note (STORY-002): the order-of-operations in §8 names three steps — known-value
masking, then regex substitution, then the length cap. **Known-value masking is out of
scope for this story** — it requires a live provider-registry snapshot of resolved
secret values that does not exist yet. This module implements regex substitution and
the length cap only. The AC-4 env-var-name exception (``api_key=ANTHROPIC_API_KEY``
left unchanged) is implemented as pattern-local logic inside the ``api_key_kv``
substitution callback, not as known-value masking.
"""

import re
from typing import Final

REDACTED: Final[str] = "<redacted>"

_LENGTH_CAP: Final[int] = 4000

# Names on the never-log list (§4), compared case-insensitively.
_NEVER_LOG_KEYS: Final[frozenset[str]] = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "secret_key",
        "secret",
        "client_secret",
        "authorization",
        "auth",
        "bearer",
        "password",
        "passwd",
        "token",
        "x-api-key",
    }
)

# Named structured fields exempt from the value-shape patterns (azure_key,
# generic_long_token) per the safe-field exemption (§8, EC-RD-6).
_SAFE_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "correlation_id",
        "run_id",
        "result_id",
        "task_id",
    }
)


def _is_safe_field_name(name: str) -> bool:
    """Return ``True`` for the safe-field exemption's named fields (§8, EC-RD-6).

    Exempt fields are ``correlation_id``, ``run_id``, ``result_id``, ``task_id``, and
    any model-digest-named field (matched by the substring ``digest``, case
    insensitively — e.g. ``model_digest``, ``response_digest``).
    """
    lowered = name.lower()
    return lowered in _SAFE_FIELD_NAMES or "digest" in lowered


# --------------------------------------------------------------------------- #
# Pattern 8's env-var-name exception (§3 Rules)
# --------------------------------------------------------------------------- #

_ENV_VAR_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[\"']?[A-Z][A-Z0-9]*(_[A-Z0-9]+)+[\"']?$")


def _redact_api_key_kv(match: re.Match[str]) -> str:
    """Replacement callback for pattern 8 (``api_key_kv``).

    Preserves the key name; replaces the value unless it matches the env-var-name
    exception — an UPPER_SNAKE identifier with at least one underscore, optionally
    quoted (§3 Rules, RT-13/RT-13a).
    """
    key_name = match.group(1)
    value = match.group(2)
    separator_start = match.start(2)
    between = match.string[match.end(1) : separator_start]
    if _ENV_VAR_NAME_RE.match(value):
        return match.group(0)
    return f"{key_name}{between}{REDACTED}"


def _redact_authorization_header(match: re.Match[str]) -> str:
    """Replacement callback for pattern 7 (``authorization_header``).

    Preserves the ``Authorization`` key name and its separator; only the value
    side is replaced — the same "key preserved, value redacted" rule pattern 8
    follows (§3 Rules: "For the key: value patterns (7 and 8) only the value
    side is replaced; the key name is kept so the redacted text remains
    readable").
    """
    key_name = match.group(1)
    separator_start = match.start(2)
    between = match.string[match.end(1) : separator_start]
    return f"{key_name}{between}{REDACTED}"


# --------------------------------------------------------------------------- #
# The ordered regex denylist (§3, patterns 1-10)
# --------------------------------------------------------------------------- #

_PATTERN_OPENAI_KEY: Final[re.Pattern[str]] = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
_PATTERN_ANTHROPIC_KEY: Final[re.Pattern[str]] = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")
_PATTERN_GOOGLE_KEY: Final[re.Pattern[str]] = re.compile(r"AIza[A-Za-z0-9_-]{30,}")
_PATTERN_GITHUB_TOKEN: Final[re.Pattern[str]] = re.compile(r"gho_[A-Za-z0-9]{20,}")
_PATTERN_AZURE_KEY: Final[re.Pattern[str]] = re.compile(r"\b[A-Fa-f0-9]{32}\b")
_PATTERN_BEARER_TOKEN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*"
)
_PATTERN_AUTHORIZATION_HEADER: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(Authorization)\s*[:=]\s*(\S.*\S|\S)"
)
_PATTERN_API_KEY_KV: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(api[_-]?key|apikey|access[_-]?token|secret[_-]?key|client[_-]?secret)\b"
    r"\s*[:=]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
_PATTERN_JWT: Final[re.Pattern[str]] = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
)
_PATTERN_GENERIC_LONG_TOKEN: Final[re.Pattern[str]] = re.compile(r"\b[A-Za-z0-9_-]{40,}\b")

# Applied in order (§3, §8 step 2). Each entry is (pattern, replacement).
# `str` replacements use `re.sub`'s literal-string form; `None` marks a
# callback-based substitution handled explicitly in `_apply_denylist` below.
_DENYLIST: Final[tuple[tuple[re.Pattern[str], str | None], ...]] = (
    (_PATTERN_OPENAI_KEY, REDACTED),
    (_PATTERN_ANTHROPIC_KEY, REDACTED),
    (_PATTERN_GOOGLE_KEY, REDACTED),
    (_PATTERN_GITHUB_TOKEN, REDACTED),
    (_PATTERN_AZURE_KEY, REDACTED),
    (_PATTERN_BEARER_TOKEN, REDACTED),
    (_PATTERN_AUTHORIZATION_HEADER, None),  # callback: preserves the key name.
    (_PATTERN_API_KEY_KV, None),  # callback: preserves the key name.
    (_PATTERN_JWT, REDACTED),
    (_PATTERN_GENERIC_LONG_TOKEN, REDACTED),
)


def _apply_denylist(text: str) -> str:
    """Apply the ordered regex denylist (§3, §8 step 2), global substitution."""
    result = text
    for pattern, replacement in _DENYLIST:
        if pattern is _PATTERN_AUTHORIZATION_HEADER:
            result = pattern.sub(_redact_authorization_header, result)
        elif pattern is _PATTERN_API_KEY_KV:
            result = pattern.sub(_redact_api_key_kv, result)
        else:
            assert replacement is not None  # noqa: S101  # narrows for mypy; always set
            result = pattern.sub(replacement, result)
    return result


def _apply_length_cap(text: str) -> str:
    """Truncate to the 4000-character cap and append the truncation suffix (§5)."""
    if len(text) <= _LENGTH_CAP:
        return text
    removed = len(text) - _LENGTH_CAP
    return f"{text[:_LENGTH_CAP]} …[truncated, {removed} more characters]"


def redact_impl(text: str | None) -> str:
    """Implement ``redact()`` (§7.1): regex substitution, then the length cap.

    ``None`` or an empty string returns an empty string with no error (EC-RD-5).
    """
    if not text:
        return ""
    substituted = _apply_denylist(text)
    return _apply_length_cap(substituted)


def _redact_field_value(name: str, value: object) -> object:
    """Apply the never-log and safe-field rules to a single named field's value."""
    if name.lower() in _NEVER_LOG_KEYS:
        return REDACTED
    if _is_safe_field_name(name):
        return value
    if isinstance(value, str):
        return _apply_denylist(value)
    return value


def redact_for_log_impl(
    logger: object,  # noqa: ARG001  # part of the structlog-processor call shape
    method_name: str,  # noqa: ARG001  # part of the structlog-processor call shape
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Implement ``redact_for_log()`` (§7.2): never-log field replacement, then
    free-text scrubbing of the remaining fields, then the length cap.

    Typed structurally as a structlog processor (``logger``, ``method_name``,
    ``event_dict``) without importing ``structlog`` — ``backend/errors/`` may import
    only the standard library and ``msgspec``.
    """
    result: dict[str, object] = {}
    for name, value in event_dict.items():
        redacted_value = _redact_field_value(name, value)
        if isinstance(redacted_value, str):
            redacted_value = _apply_length_cap(redacted_value)
        result[name] = redacted_value
    return result
