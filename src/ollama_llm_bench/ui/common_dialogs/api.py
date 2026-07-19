"""Public factory for ``ui/common_dialogs/`` -- the Run Summary dialog (STORY-055).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§8 (preflight re-check), §12 (Start Effects). Scoped to exactly the Run Summary
dialog -- see this package's ``__init__.py`` docstring for why the other Common
Dialogs are out of scope.
"""

import icontract
from PySide6.QtWidgets import QDialog, QWidget

from ollama_llm_bench.backend.domain import AppReadinessSnapshot, RunStartRequest
from ollama_llm_bench.ui.common_dialogs._internal.view import RunSummaryDialog
from ollama_llm_bench.ui.common_dialogs._internal.view_model_select import (
    select_run_summary_view_model,
)
from ollama_llm_bench.ui.common_dialogs.protocols import RunSummaryGateway
from ollama_llm_bench.ui.new_benchmark.models import RunValidationSeverity, ValidationEntry
from ollama_llm_bench.ui.new_benchmark.protocols import RunValidator

__all__: list[str] = ["make_run_summary_dialog"]


@icontract.require(lambda gateway: gateway is not None, "gateway is a required collaborator")
@icontract.require(
    lambda run_validator: run_validator is not None, "run_validator is a required collaborator"
)
@icontract.require(lambda request: request is not None, "request is a required collaborator")
@icontract.ensure(lambda result: result is None or isinstance(result, QDialog))
def make_run_summary_dialog(
    *,
    gateway: RunSummaryGateway,
    run_validator: RunValidator,
    request: RunStartRequest,
    parent: QWidget | None = None,
) -> QDialog | None:
    """Build the Run Summary dialog, or return ``None`` if the preflight re-check fails.

    Runs the preflight re-check (§8) immediately, before constructing any dialog
    UI, so a failed check never shows a broken dialog -- "the dialog does not
    open" is literally "this factory returns ``None``"; no half-built dialog ever
    exists to close (STORY-055-AC-7).

    Args:
        gateway: The dialog's own narrow adapter gateway (D-R-06).
        run_validator: The Run Validator collaborator, re-run for the preflight
            re-check and to build the Warnings callout.
        request: The assembled ``RunStartRequest`` under review.
        parent: The parent widget the dialog is centred over, if any.

    Returns:
        The mountable, modal ``QDialog``, or ``None`` when the preflight
        re-check detects a broken environment (§8) -- the caller (the New
        Benchmark controller) is responsible for surfacing a toast and leaving
        every widget field intact; this factory raises nothing and shows
        nothing itself, keeping presentation decisions in the caller.
    """
    validation_entries = run_validator.validate(request)
    readiness = gateway.readiness_snapshot()
    if not _preflight_passes(
        request=request, readiness=readiness, validation_entries=validation_entries
    ):
        return None
    view_model = select_run_summary_view_model(
        request=request, readiness=readiness, validation_entries=validation_entries
    )
    return RunSummaryDialog(gateway=gateway, request=request, view_model=view_model, parent=parent)


def _preflight_passes(
    *,
    request: RunStartRequest,
    readiness: AppReadinessSnapshot,
    validation_entries: tuple[ValidationEntry, ...],
) -> bool:
    """Re-run the Start-gating hard-error checks (§8), plus the reachable-provider,
    required-judge, and required-embedding conditions the spec calls out by name."""
    hard_error = any(
        entry.severity is RunValidationSeverity.HARD_ERROR for entry in validation_entries
    )
    reachable_provider_ids = {p.provider_id for p in readiness.per_provider if p.reachable}
    no_reachable_test_model = not any(
        target.provider_id in reachable_provider_ids for target in request.test_models
    )
    judge_missing = request.judge_analysis_enabled and request.judge_model is None
    embedding_unreachable = (
        request.embedding_model is not None and not readiness.embedding_reachable
    )
    return not (hard_error or no_reachable_test_model or judge_missing or embedding_unreachable)
