"""Tests proving the §6.3 leaf-catalogue mapping acceptance criterion of STORY-002.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md``
§6.3 (the leaf catalogue). Expected ``error_kind``/``terminal_result_status`` string
values are cross-checked against the real ``ErrorKind``/``ResultStatus`` enum
``.value``s from ``backend.domain`` — this test module may import ``backend.domain``
even though ``backend/errors/`` production code itself may not.
"""

import pytest

from ollama_llm_bench.backend.domain.models import ErrorKind, ResultStatus
from ollama_llm_bench.backend.errors._internal.hierarchy import (
    ConfigurationError,
    DatabaseDiskFullError,
    DatabaseLockedError,
    EmbeddingUnavailableError,
    HttpConnectionError,
    HttpTimeoutError,
    LLMOutputParseError,
    MissingEnvVarError,
    ModelNotAvailableError,
    OsAdapterError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderContentFilterError,
    ProviderContextLengthError,
    ProviderOverloadedError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitedError,
    ProviderServerError,
    TaskCancelledError,
    TaskFileError,
)
from ollama_llm_bench.backend.errors.models import ErrorCategory

# (leaf type, expected category, expected error_kind, expected terminal_result_status)
# All 20 AppError leaves from §6.3 (excludes the 3 ProgrammerError leaves, which carry
# no error_kind/terminal_result_status mapping in that table).
_LEAF_CASES: tuple[tuple[type[Exception], ErrorCategory, str | None, str | None], ...] = (
    # Transient
    (
        HttpTimeoutError,
        ErrorCategory.TRANSIENT,
        ErrorKind.TIMEOUT.value,
        ResultStatus.FAILED_TIMEOUT.value,
    ),
    (
        HttpConnectionError,
        ErrorCategory.TRANSIENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (
        ProviderRateLimitedError,
        ErrorCategory.TRANSIENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (
        ProviderServerError,
        ErrorCategory.TRANSIENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (
        ProviderOverloadedError,
        ErrorCategory.TRANSIENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (DatabaseLockedError, ErrorCategory.TRANSIENT, ErrorKind.OTHER.value, None),
    # Permanent
    (
        ProviderBadRequestError,
        ErrorCategory.PERMANENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (
        ProviderContentFilterError,
        ErrorCategory.PERMANENT,
        ErrorKind.LLM.value,
        ResultStatus.FAILED_INFERENCE.value,
    ),
    (
        ProviderQuotaExhaustedError,
        ErrorCategory.PERMANENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (
        ProviderContextLengthError,
        ErrorCategory.PERMANENT,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_INFERENCE.value,
    ),
    (
        LLMOutputParseError,
        ErrorCategory.PERMANENT,
        ErrorKind.LLM.value,
        ResultStatus.FAILED_INFERENCE.value,
    ),
    (
        DatabaseDiskFullError,
        ErrorCategory.PERMANENT,
        ErrorKind.OTHER.value,
        ResultStatus.ERRORED.value,
    ),
    (EmbeddingUnavailableError, ErrorCategory.PERMANENT, ErrorKind.OTHER.value, None),
    # User
    (
        ProviderAuthError,
        ErrorCategory.USER,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (ConfigurationError, ErrorCategory.USER, ErrorKind.OTHER.value, None),
    (
        ModelNotAvailableError,
        ErrorCategory.USER,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (
        MissingEnvVarError,
        ErrorCategory.USER,
        ErrorKind.PROVIDER.value,
        ResultStatus.FAILED_PROVIDER.value,
    ),
    (TaskFileError, ErrorCategory.USER, ErrorKind.OTHER.value, None),
    (OsAdapterError, ErrorCategory.USER, ErrorKind.OTHER.value, None),
    (TaskCancelledError, ErrorCategory.USER, None, None),
)


@pytest.mark.parametrize(
    ("leaf_type", "expected_category", "expected_error_kind", "expected_terminal_status"),
    _LEAF_CASES,
    ids=[leaf.__name__ for leaf, *_ in _LEAF_CASES],
)
def test_leaf_category_kind_and_status_mapping(
    leaf_type: type[Exception],
    expected_category: ErrorCategory,
    expected_error_kind: str | None,
    expected_terminal_status: str | None,
) -> None:
    """Proves: STORY-002-AC-2

    Every one of the 20 AppError leaves in the §6.3 catalogue resolves `.category`,
    `.error_kind`, and `.terminal_result_status` to the exact values documented in
    that table — table-driven over the full catalogue, with `error_kind`/
    `terminal_result_status` cross-checked against the real `ErrorKind`/
    `ResultStatus` enum `.value`s.
    """
    # Arrange
    instance = leaf_type(message="boom")  # type: ignore[call-arg]  # every leaf's __init__ is kw-only(message=...)

    # Act
    category = instance.category  # type: ignore[attr-defined]  # dynamic over 19 leaf types sharing the category ClassVar
    error_kind = instance.error_kind  # type: ignore[attr-defined]  # dynamic over leaf types sharing the ClassVar
    terminal_status = instance.terminal_result_status  # type: ignore[attr-defined]  # dynamic ClassVar access

    # Assert
    assert category == expected_category
    assert error_kind == expected_error_kind
    assert terminal_status == expected_terminal_status
