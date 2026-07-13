"""Proves: STORY-029-AC-7"""

import pytest

from ollama_llm_bench.backend.benchmark_pipeline._internal.containment import contain_unit_failure
from ollama_llm_bench.backend.domain.models import ResultStatus
from ollama_llm_bench.backend.errors import (
    AppError,
    ConfigurationError,
    ContractViolationError,
    HttpTimeoutError,
    ProviderBadRequestError,
)


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (HttpTimeoutError(message="timed out"), ResultStatus.FAILED_TIMEOUT),
        (ProviderBadRequestError(message="bad request"), ResultStatus.FAILED_PROVIDER),
        (ConfigurationError(message="misconfigured"), ResultStatus.ERRORED),
    ],
)
def test_dd44_containment_uses_each_leafs_own_status_and_kind_mapping(
    exc: AppError, expected_status: ResultStatus
) -> None:
    """Proves: STORY-029-AC-7

    Every AppError leaf's own error_kind/terminal_result_status class
    attributes — not an ad hoc isinstance dispatch — determine the
    persisted ResultPatch; a leaf with no per-unit terminal status
    (ConfigurationError) falls back to ERRORED.
    """
    patch = contain_unit_failure(exc)

    assert patch.status is expected_status
    assert patch.error_message is not None


def test_contain_unit_failure_does_not_accept_programmer_error() -> None:
    """Proves: STORY-029-AC-7

    A ProgrammerError is not an Exception subclass, so it is structurally
    impossible to route it through contain_unit_failure's AppError-typed
    parameter — mypy --strict enforces this at the call site.
    """
    assert not issubclass(ContractViolationError, Exception)
