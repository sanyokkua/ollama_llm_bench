"""DD-44 exception containment: every AppError leaf becomes result-row data via its
own error_kind/terminal_result_status class attributes (17_ERROR_TAXONOMY.md §6.3)."""

from ollama_llm_bench.backend.domain.models import ErrorKind, ResultPatch, ResultStatus
from ollama_llm_bench.backend.errors import AppError


def contain_unit_failure(exc: AppError) -> ResultPatch:
    """Convert one unit's caught AppError leaf into a terminal ResultPatch.

    Args:
        exc: The AppError leaf the unit's Future raised. Its concrete leaf
            class already carries the DD-44 status/kind mapping via its
            error_kind/terminal_result_status class attributes
            (17_ERROR_TAXONOMY.md §6.3) — this function does not
            re-derive the mapping via isinstance dispatch. Never called
            with a ProgrammerError (not an Exception subclass, cannot
            reach this signature) or a TaskCancelledError (propagates to
            the dispatcher's halt path uncontained).

    Returns:
        A ResultPatch moving the row to the leaf's own terminal status,
        falling back to ERRORED when the leaf has no per-unit terminal
        status (e.g. a ConfigurationError caught mid-run), with
        error_kind/error_message set from the leaf.
    """
    terminal_status: str | None = getattr(exc, "terminal_result_status", None)
    error_kind_value: str | None = getattr(exc, "error_kind", None)
    status = ResultStatus(terminal_status) if terminal_status is not None else ResultStatus.ERRORED
    error_kind = ErrorKind(error_kind_value) if error_kind_value is not None else None
    return ResultPatch(status=status, error_kind=error_kind, error_message=exc.message)
