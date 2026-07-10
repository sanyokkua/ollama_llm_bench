"""Error taxonomy + redaction.

Defines the categorised application error hierarchy — ``AppError`` (root of
recoverable errors) with its ``TransientError``/``PermanentError``/``UserError``
category roots and every leaf, the ``ProviderError`` marker, and ``ProgrammerError``
(outside ``Exception``) with its leaves — plus the secret-redaction module applied at
the two sanctioned surfaces named in
``docs/v3_specification/10_Domain_and_Data/08_REDACTION_PATTERNS.md``:
``redact(text)`` and the ``redact_for_log`` structlog processor.

See ``docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md`` for the
full hierarchy and leaf catalogue.
"""

from ollama_llm_bench.backend.errors._internal.hierarchy import (
    AppError,
    ConfigurationError,
    ContractViolationError,
    DatabaseDiskFullError,
    DatabaseIntegrityError,
    DatabaseLockedError,
    EmbeddingUnavailableError,
    HttpConnectionError,
    HttpTimeoutError,
    LLMOutputParseError,
    MissingEnvVarError,
    ModelNotAvailableError,
    OsAdapterError,
    PermanentError,
    PersistenceError,
    ProgrammerError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderContentFilterError,
    ProviderContextLengthError,
    ProviderError,
    ProviderOverloadedError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitedError,
    ProviderServerError,
    TaskCancelledError,
    TaskFileError,
    TransientError,
    UserError,
    ValidationError,
)
from ollama_llm_bench.backend.errors.api import redact, redact_for_log
from ollama_llm_bench.backend.errors.models import ErrorCategory, ErrorContext

__all__: list[str] = [
    "AppError",
    "ConfigurationError",
    "ContractViolationError",
    "DatabaseDiskFullError",
    "DatabaseIntegrityError",
    "DatabaseLockedError",
    "EmbeddingUnavailableError",
    "ErrorCategory",
    "ErrorContext",
    "HttpConnectionError",
    "HttpTimeoutError",
    "LLMOutputParseError",
    "MissingEnvVarError",
    "ModelNotAvailableError",
    "OsAdapterError",
    "PermanentError",
    "PersistenceError",
    "ProgrammerError",
    "ProviderAuthError",
    "ProviderBadRequestError",
    "ProviderContentFilterError",
    "ProviderContextLengthError",
    "ProviderError",
    "ProviderOverloadedError",
    "ProviderQuotaExhaustedError",
    "ProviderRateLimitedError",
    "ProviderServerError",
    "TaskCancelledError",
    "TaskFileError",
    "TransientError",
    "UserError",
    "ValidationError",
    "redact",
    "redact_for_log",
]
