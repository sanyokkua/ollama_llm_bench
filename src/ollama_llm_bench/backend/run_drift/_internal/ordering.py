"""Assembly and ordering of the accumulated drift warnings (spec §6.5)."""

from ollama_llm_bench.backend.run_drift.models import DriftSeverity, DriftWarning

__all__: list[str] = ["assemble"]


def assemble(warnings: list[DriftWarning]) -> tuple[DriftWarning, ...]:
    """Sort the accumulated warnings into their final display order (spec §6.5).

    Order: ``BLOCKING`` before ``WARNING``; within a severity, by
    ``provider_id`` (nulls last), then ``model_name`` (nulls last).

    Returns:
        The sorted, immutable tuple the detector returns to its caller.
    """
    return tuple(sorted(warnings, key=_sort_key))


def _sort_key(warning: DriftWarning) -> tuple[bool, bool, str, bool, str]:
    return (
        warning.severity != DriftSeverity.BLOCKING,
        warning.provider_id is None,
        warning.provider_id or "",
        warning.model_name is None,
        warning.model_name or "",
    )
