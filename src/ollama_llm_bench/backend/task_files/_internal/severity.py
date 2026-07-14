"""Severity ordering and aggregation (`14_VALIDATION_CASCADE.md` §6.4)."""

from ollama_llm_bench.backend.task_files.models import ValidationSeverity

_SEVERITY_ORDER: tuple[ValidationSeverity, ...] = (
    ValidationSeverity.CLEAN,
    ValidationSeverity.INFO,
    ValidationSeverity.WARNING,
    ValidationSeverity.ERROR,
)


def max_severity(*severities: ValidationSeverity) -> ValidationSeverity:
    """Return the highest-ranked severity among ``severities``.

    Args:
        severities: Zero or more severities to combine, in any order.

    Returns:
        ``ValidationSeverity.CLEAN`` when given no arguments; otherwise the
        maximum severity on the ``clean < info < warning < error`` ordering.
    """
    if not severities:
        return ValidationSeverity.CLEAN
    return max(severities, key=_SEVERITY_ORDER.index)
