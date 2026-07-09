"""Tests proving the error-hierarchy acceptance criteria of STORY-002.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/17_ERROR_TAXONOMY.md``
§6.2 (the hierarchy) and §6.4 (mixed inheritance for multi-axis dispatch).
"""

import pytest

from ollama_llm_bench.backend.errors._internal.hierarchy import (
    HttpConnectionError,
    HttpTimeoutError,
    MissingEnvVarError,
    ModelNotAvailableError,
    PermanentError,
    ProgrammerError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderContentFilterError,
    ProviderError,
    ProviderOverloadedError,
    ProviderQuotaExhaustedError,
    ProviderRateLimitedError,
    ProviderServerError,
    TransientError,
    UserError,
)
from ollama_llm_bench.backend.errors.models import ErrorCategory

# The 11 ProviderError-marked leaves per §6.4, with the category root each mixes in
# first (and therefore the category that must win MRO resolution).
_PROVIDER_ERROR_LEAVES: tuple[tuple[type[Exception], ErrorCategory], ...] = (
    (HttpTimeoutError, ErrorCategory.TRANSIENT),
    (HttpConnectionError, ErrorCategory.TRANSIENT),
    (ProviderRateLimitedError, ErrorCategory.TRANSIENT),
    (ProviderServerError, ErrorCategory.TRANSIENT),
    (ProviderOverloadedError, ErrorCategory.TRANSIENT),
    (ProviderBadRequestError, ErrorCategory.PERMANENT),
    (ProviderContentFilterError, ErrorCategory.PERMANENT),
    (ProviderQuotaExhaustedError, ErrorCategory.PERMANENT),
    (ProviderAuthError, ErrorCategory.USER),
    (ModelNotAvailableError, ErrorCategory.USER),
    (MissingEnvVarError, ErrorCategory.USER),
)


def test_programmer_error_is_outside_exception() -> None:
    """Proves: STORY-002-AC-1

    ProgrammerError sits outside Exception so `except Exception` never catches it,
    while every category root resolves to its own `category` ClassVar.
    """
    # Arrange / Act / Assert
    assert issubclass(ProgrammerError, Exception) is False
    assert issubclass(ProgrammerError, BaseException) is True
    assert TransientError.category == ErrorCategory.TRANSIENT
    assert PermanentError.category == ErrorCategory.PERMANENT
    assert UserError.category == ErrorCategory.USER
    assert ProgrammerError.category == ErrorCategory.PROGRAMMER


def test_except_exception_does_not_catch_programmer_error() -> None:
    """Proves: STORY-002-AC-1

    A raised ProgrammerError is not intercepted by a bare `except Exception` net —
    the concrete behavioural consequence of sitting outside `Exception`.
    """
    # Arrange
    caught_as_exception = False

    # Act
    try:
        try:
            raise ProgrammerError(message="invariant broken")
        except Exception:  # noqa: BLE001  # deliberately proving this does NOT catch
            caught_as_exception = True
    except ProgrammerError:
        pass

    # Assert
    assert caught_as_exception is False


@pytest.mark.parametrize(
    ("leaf_type", "expected_category"),
    _PROVIDER_ERROR_LEAVES,
    ids=[leaf.__name__ for leaf, _ in _PROVIDER_ERROR_LEAVES],
)
def test_mixed_inheritance_mro_gives_category_root(
    leaf_type: type[Exception], expected_category: ErrorCategory
) -> None:
    """Proves: STORY-002-AC-3

    Every ProviderError-marked leaf is simultaneously an instance of ProviderError
    (the provider-surface axis) and resolves `.category` to its first-listed
    category root via MRO (the retry axis) — table-driven over all 11 leaves named
    in §6.4.
    """
    # Arrange
    instance = leaf_type(message="boom")  # type: ignore[call-arg]  # every leaf's __init__ is kw-only(message=...)

    # Act / Assert
    assert isinstance(instance, ProviderError)
    category = instance.category  # type: ignore[attr-defined]  # dynamic over 11 leaf types sharing the category ClassVar
    assert category == expected_category
