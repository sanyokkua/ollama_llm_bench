"""Cross-boundary DTOs and enums owned by the error-taxonomy module.

``ErrorCategory`` is declared **locally** here rather than imported from
``backend.domain`` — ``backend/errors/`` may import only the standard library and
``msgspec`` (``docs/v3_specification/14_Process_and_Traceability/01_MODULE_INVENTORY.md``
§4.1), so it cannot depend on any project-internal package, including
``backend.domain``.
"""

from enum import StrEnum

import msgspec

__all__: list[str] = [
    "ErrorCategory",
    "ErrorContext",
]


class ErrorCategory(StrEnum):
    """The four error categories every application error belongs to exactly one of.

    See ``docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`` §6.1.
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    USER = "user"
    PROGRAMMER = "programmer"


class ErrorContext(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Redaction-safe diagnostic context carried by a recoverable application error.

    Every field is safe to log verbatim: no secret-bearing value is ever placed on
    ``ErrorContext`` (``17_ERROR_TAXONOMY.md`` §2, §8; ``08_REDACTION_PATTERNS.md``).
    """

    provider_id: str | None = None
    model_id_truncated: str | None = None
    endpoint: str | None = None
    http_status: int | None = None
    provider_error_code: str | None = None
    attempt: int | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    phase: str | None = None
