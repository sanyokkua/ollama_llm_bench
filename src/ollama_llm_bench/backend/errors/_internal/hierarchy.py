"""The application error hierarchy.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md``
§6.2 (the hierarchy), §6.3 (the leaf catalogue), and §6.4 (mixed inheritance for
multi-axis dispatch).

Import-boundary note: this module imports only the standard library, ``msgspec``
(transitively, via ``..models``), and its sibling ``..models`` — never
``backend.domain``. Each leaf's ``error_kind`` and ``terminal_result_status`` class
variables therefore hold the exact ``.value`` string of the corresponding
``backend.domain.models.ErrorKind`` / ``ResultStatus`` member, verified against
``src/ollama_llm_bench/backend/domain/models.py`` at authoring time, rather than a
reference to the enum itself.

Phase-dependent note (§6.3): ``HttpTimeoutError`` and ``ProviderContextLengthError``
map to a different ``ErrorKind`` / terminal ``ResultStatus`` depending on the pipeline
phase in which they are raised (inference vs. judge/analysis). The class-level
defaults below hold the inference-phase value in both cases; resolving the
judge/analysis-phase variant from ``ErrorContext.phase`` is a phase-resolution
refinement layered on by the benchmark pipeline in a later story, not by this one.
"""

from typing import ClassVar

from ollama_llm_bench.backend.errors.models import ErrorCategory, ErrorContext

__all__: list[str] = [
    "AppError",
    "ConfigurationError",
    "ContractViolationError",
    "DatabaseDiskFullError",
    "DatabaseIntegrityError",
    "DatabaseLockedError",
    "EmbeddingUnavailableError",
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
]


class AppError(Exception):
    """Root of every recoverable application error.

    Descends from ``Exception`` (unlike ``ProgrammerError``), so ``except Exception``
    catches every recoverable error — §6.2.
    """

    def __init__(self, *, message: str, context: ErrorContext | None = None) -> None:
        self.message = message
        self.context = context
        super().__init__(message)


class TransientError(AppError):
    """A momentary failure likely to succeed on retry (§6.1)."""

    category: ClassVar[ErrorCategory] = ErrorCategory.TRANSIENT


class PermanentError(AppError):
    """A real failure retrying cannot fix (§6.1)."""

    category: ClassVar[ErrorCategory] = ErrorCategory.PERMANENT


class UserError(AppError):
    """A condition the user can fix and re-run (§6.1)."""

    category: ClassVar[ErrorCategory] = ErrorCategory.USER


class ProgrammerError(BaseException):
    """Root of every programmer-error leaf.

    Descends directly from ``BaseException``, **outside** ``Exception``, so it
    survives ``except Exception:`` catch-all nets and reaches the process-terminal
    hook (§6.2). Never carries an ``ErrorContext`` — a programmer error is not a
    recoverable, context-carrying condition.
    """

    category: ClassVar[ErrorCategory] = ErrorCategory.PROGRAMMER

    def __init__(self, *, message: str) -> None:
        self.message = message
        super().__init__(message)


class ProviderError:
    """Marker mixin for leaves dispatched on the provider-surface axis (§6.4).

    Carries no ``category`` attribute and does not derive from ``Exception``/
    ``AppError`` — it exists purely so ``isinstance(err, ProviderError)`` works,
    without affecting the ``category`` MRO resolution of the leaves that mix it in.
    """


# --------------------------------------------------------------------------- #
# Transient leaves
# --------------------------------------------------------------------------- #


class HttpTimeoutError(TransientError, ProviderError):
    """A provider request exceeded the transport time budget (§6.3).

    The ``ErrorContext.phase`` field carries the pipeline phase so the pipeline can
    route the failure to the correct terminal status; the class-level defaults below
    hold the inference-phase value (see the module docstring's phase-dependent note).
    """

    error_kind: ClassVar[str | None] = "timeout"
    terminal_result_status: ClassVar[str | None] = "failed_timeout"


class HttpConnectionError(TransientError, ProviderError):
    """A connection was refused, reset, or DNS failed (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class ProviderRateLimitedError(TransientError, ProviderError):
    """The provider returned a rate-limit response (HTTP 429) (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"

    def __init__(
        self,
        *,
        message: str,
        context: ErrorContext | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message=message, context=context)
        self.retry_after = retry_after


class ProviderServerError(TransientError, ProviderError):
    """The provider returned a 5xx server error (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class ProviderOverloadedError(TransientError, ProviderError):
    """The provider reported temporary saturation (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class DatabaseLockedError(TransientError):
    """A SQLite write was blocked past the busy timeout (§6.3).

    Terminal ``ResultStatus`` is ``ERRORED`` only if it escapes the persistence
    retry wrapper; the class default is ``None`` because it is not, by default, a
    per-unit failure.
    """

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = None


# --------------------------------------------------------------------------- #
# Permanent leaves
# --------------------------------------------------------------------------- #


class ProviderBadRequestError(PermanentError, ProviderError):
    """The provider rejected the request as malformed (HTTP 400) (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class ProviderContentFilterError(PermanentError, ProviderError):
    """The provider refused on a content-policy ground (§6.3)."""

    error_kind: ClassVar[str | None] = "llm"
    terminal_result_status: ClassVar[str | None] = "failed_inference"


class ProviderQuotaExhaustedError(PermanentError, ProviderError):
    """The provider account quota is exhausted (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class ProviderContextLengthError(PermanentError, ProviderError):
    """The provider rejected the request because the prompt exceeded the model's
    context window (§6.3).

    Permanent — retrying cannot shrink the prompt. The class-level defaults below
    hold the inference-phase value (``failed_inference``); the judge-phase variant
    (``errored``) is a phase-dependent refinement layered on by the pipeline in a
    later story (see the module docstring's phase-dependent note).
    """

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_inference"


class LLMOutputParseError(PermanentError):
    """The judge or inference output could not be parsed into the expected shape
    (§6.3)."""

    error_kind: ClassVar[str | None] = "llm"
    terminal_result_status: ClassVar[str | None] = "failed_inference"


class DatabaseDiskFullError(PermanentError):
    """A SQLite write failed because the disk is full (§6.3)."""

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = "errored"


class EmbeddingUnavailableError(PermanentError):
    """The embedding endpoint could not produce a vector at the run-start fail-fast
    embedding probe (§6.3).

    Raised only there; it settles the **run** ``FAILED`` before any inference and is
    never a per-result ``ERRORED`` — the class default is therefore ``None``.
    """

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = None


class PersistenceError(PermanentError):
    """A persistence-store operation failed (`08-E_interfaces_contracts.md` §7).

    Raised by every public method of the six per-aggregate persistence stores
    (`RunsStore`, `TasksStore`, `ResultsStore`, `ProvidersStore`,
    `ModelCapabilitiesStore`, `AppSettingsStore`) on a storage failure — a wrapped
    `sqlite3.Error`, a missing row where the contract requires one, or a duplicate-name
    constraint violation. Not itself a `sqlite3` type: the persistence layer wraps every
    `sqlite3.Error` into this leaf at the store boundary, per the same adapter-boundary
    translation pattern used for provider SDK exceptions.
    """

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = "errored"


# --------------------------------------------------------------------------- #
# User leaves
# --------------------------------------------------------------------------- #


class ProviderAuthError(UserError, ProviderError):
    """The provider rejected the credential (HTTP 401/403) (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class ConfigurationError(UserError):
    """A required configuration value is missing, malformed, or contradictory
    (§6.3). Rarely a per-unit failure; usually caught pre-run."""

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = None


class ModelNotAvailableError(UserError, ProviderError):
    """The requested model is not available on the provider (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class MissingEnvVarError(UserError, ProviderError):
    """The environment variable named by a provider's API key is unset or empty, so
    the secret could not be resolved (§6.3)."""

    error_kind: ClassVar[str | None] = "provider"
    terminal_result_status: ClassVar[str | None] = "failed_provider"


class TaskFileError(UserError):
    """A task file or folder could not be read or parsed as YAML at all (§6.3). Not
    a per-unit failure — caught before the run starts."""

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = None


class OsAdapterError(UserError):
    """An OS integration call failed — clipboard, file manager, picker subsystem
    (§6.3). Not a per-unit failure."""

    error_kind: ClassVar[str | None] = "other"
    terminal_result_status: ClassVar[str | None] = None


class TaskCancelledError(UserError):
    """The user paused or stopped the run; raised by
    ``CancellationToken.raise_if_cancelled()`` (§6.3). Not an error kind, not a
    failure — produces a clean halt."""

    error_kind: ClassVar[str | None] = None
    terminal_result_status: ClassVar[str | None] = None


# --------------------------------------------------------------------------- #
# Programmer-error leaves
# --------------------------------------------------------------------------- #


class DatabaseIntegrityError(ProgrammerError):
    """A schema invariant is broken — a foreign key or uniqueness constraint the
    application logic should have guaranteed (§6.3)."""


class ContractViolationError(ProgrammerError):
    """A contract or assertion is violated — an impossible state, a "this cannot
    happen" branch (§6.3)."""


class ValidationError(ProgrammerError):
    """A domain value violated a declared ``msgspec.Meta`` constraint at
    construction time; a programmer error, never an expected runtime condition
    (§6.3)."""
