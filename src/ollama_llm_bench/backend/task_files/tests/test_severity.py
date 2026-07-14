"""General coverage of ``max_severity`` — not tied to one acceptance criterion."""

import pytest

from ollama_llm_bench.backend.task_files._internal.severity import max_severity
from ollama_llm_bench.backend.task_files.models import ValidationSeverity


def test_max_severity_with_no_arguments_returns_clean() -> None:
    """``max_severity()`` with no arguments is the cascade's identity element."""
    assert max_severity() == ValidationSeverity.CLEAN


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ((ValidationSeverity.CLEAN,), ValidationSeverity.CLEAN),
        ((ValidationSeverity.INFO, ValidationSeverity.CLEAN), ValidationSeverity.INFO),
        (
            (ValidationSeverity.WARNING, ValidationSeverity.INFO, ValidationSeverity.CLEAN),
            ValidationSeverity.WARNING,
        ),
        (
            (
                ValidationSeverity.ERROR,
                ValidationSeverity.WARNING,
                ValidationSeverity.INFO,
                ValidationSeverity.CLEAN,
            ),
            ValidationSeverity.ERROR,
        ),
        ((ValidationSeverity.ERROR, ValidationSeverity.ERROR), ValidationSeverity.ERROR),
    ],
)
def test_max_severity_returns_the_highest_ranked_input(
    severities: tuple[ValidationSeverity, ...], expected: ValidationSeverity
) -> None:
    """``max_severity`` follows the ``clean < info < warning < error`` ordering
    regardless of input order."""
    assert max_severity(*severities) == expected
