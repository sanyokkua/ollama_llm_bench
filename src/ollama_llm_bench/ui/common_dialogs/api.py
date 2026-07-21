"""Public factories for ``ui/common_dialogs/`` -- Run Summary/Rename Run (STORY-055/056)
and Resume Summary/Retry Selection (STORY-057).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§8 (preflight re-check), §12 (Start Effects); ``resume_summary_dialog.md`` §2, §12
(§13 Function Inventory "Open dialog" gate); ``retry_selection_dialog.md`` §2, §12
(state machine "Loading -> [*]: run has no result rows", EC-RT-1).
"""

import icontract
from PySide6.QtWidgets import QDialog, QWidget

from ollama_llm_bench.backend.domain import (
    AppReadinessSnapshot,
    BenchmarkRun,
    RunId,
    RunStartRequest,
)
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.ui.common_dialogs._internal.generate_analysis_view import (
    GenerateAnalysisDialog,
)
from ollama_llm_bench.ui.common_dialogs._internal.rename_run_view import RenameRunDialog
from ollama_llm_bench.ui.common_dialogs._internal.resume_summary_select import (
    select_resume_summary_view_model,
)
from ollama_llm_bench.ui.common_dialogs._internal.resume_summary_view import ResumeSummaryDialog
from ollama_llm_bench.ui.common_dialogs._internal.retry_selection_select import (
    select_retry_selection_view_model,
)
from ollama_llm_bench.ui.common_dialogs._internal.retry_selection_view import RetrySelectionDialog
from ollama_llm_bench.ui.common_dialogs._internal.view import RunSummaryDialog
from ollama_llm_bench.ui.common_dialogs._internal.view_model_select import (
    select_run_summary_view_model,
)
from ollama_llm_bench.ui.common_dialogs.models import GenerateAnalysisCollaborators
from ollama_llm_bench.ui.common_dialogs.protocols import (
    RenameRunGateway,
    ResumeSummaryGateway,
    RetrySelectionGateway,
    RunSummaryGateway,
)
from ollama_llm_bench.ui.new_benchmark.models import RunValidationSeverity, ValidationEntry
from ollama_llm_bench.ui.new_benchmark.protocols import RunValidator

__all__: list[str] = [
    "make_generate_analysis_dialog",
    "make_rename_run_dialog",
    "make_resume_summary_dialog",
    "make_retry_selection_dialog",
    "make_run_summary_dialog",
]


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


@icontract.require(lambda gateway: gateway is not None, "gateway is a required collaborator")
@icontract.require(lambda run_id: run_id > 0, "run_id must be a valid positive id")
@icontract.ensure(lambda result: isinstance(result, QDialog))
def make_rename_run_dialog(
    *,
    gateway: RenameRunGateway,
    run_id: RunId,
    current_custom_name: str | None,
    computed_default_name: str,
    parent: QWidget | None = None,
) -> QDialog:
    """Construct the Rename Run dialog for one run (rename_run_dialog.md).

    Unlike ``make_run_summary_dialog``, this factory never returns ``None``
    -- the Rename dialog has no readiness-gate precondition in its spec,
    only live in-dialog validation, so it always constructs.

    Args:
        gateway: Wraps ``list_runs`` (V-5 uniqueness) and ``rename_run``
            (commit).
        run_id: The run being renamed.
        current_custom_name: The run's current custom name, or ``None`` if
            it currently uses the generated default.
        computed_default_name: The precomputed default-name preview string
            (``Run N — <Mode> — YYYY-MM-DD HH:MM``), computed by the caller
            since ``RenameRunGateway`` carries no mode-label-formatting
            logic.
        parent: The dialog's parent widget, if any.

    Returns:
        The constructed, unshown ``QDialog``.
    """
    return RenameRunDialog(
        gateway=gateway,
        run_id=run_id,
        current_custom_name=current_custom_name,
        computed_default_name=computed_default_name,
        parent=parent,
    )


@icontract.require(lambda gateway: gateway is not None, "gateway is a required collaborator")
@icontract.require(lambda event_bus: event_bus is not None, "event_bus is a required collaborator")
@icontract.require(lambda run_id: run_id > 0, "run_id must be a valid positive id")
@icontract.ensure(lambda result: result is None or isinstance(result, QDialog))
def make_resume_summary_dialog(
    *,
    gateway: ResumeSummaryGateway,
    event_bus: EventBus,
    run_id: RunId,
    parent: QWidget | None = None,
) -> QDialog | None:
    """Build the Resume Summary dialog, or ``None`` if the run has no resumable result (EC-RES-6).

    Args:
        gateway: The dialog's own narrow adapter gateway (D-R-06).
        event_bus: Used only for the Fix-in-Settings not-yet-available toast.
        run_id: The run to resume.
        parent: The parent widget the dialog is centred over, if any.

    Returns:
        The mountable, modal ``QDialog``, or ``None`` when the run has zero
        resumable results (the caller is responsible for surfacing a toast).
    """
    run = gateway.get_run(run_id)
    resumable = gateway.resumable_results(run_id)
    if not resumable:
        return None
    drift_warnings = gateway.detect_drift(run_id)
    view_model = select_resume_summary_view_model(
        run=run, resumable_results=resumable, drift_warnings=drift_warnings
    )
    return ResumeSummaryDialog(
        gateway=gateway, event_bus=event_bus, view_model=view_model, parent=parent
    )


@icontract.require(lambda gateway: gateway is not None, "gateway is a required collaborator")
@icontract.require(lambda run_id: run_id > 0, "run_id must be a valid positive id")
@icontract.ensure(lambda result: result is None or isinstance(result, QDialog))
def make_retry_selection_dialog(
    *,
    gateway: RetrySelectionGateway,
    run_id: RunId,
    parent: QWidget | None = None,
) -> QDialog | None:
    """Build the Retry Selection dialog, or ``None`` if the run has zero result rows.

    Args:
        gateway: The dialog's own narrow adapter gateway (D-R-06).
        run_id: The run whose result rows are offered for retry.
        parent: The parent widget the dialog is centred over, if any.

    Returns:
        The mountable, modal ``QDialog``, or ``None`` when the run has no
        result rows at all (EC-RT-1; state machine §12).
    """
    results = gateway.list_results(run_id)
    if not results:
        return None
    view_model = select_retry_selection_view_model(run_id=run_id, results=results)
    return RetrySelectionDialog(gateway=gateway, view_model=view_model, parent=parent)


@icontract.require(lambda run: run is not None, "run is a required collaborator")
@icontract.require(
    lambda collaborators: collaborators is not None, "collaborators is a required bundle"
)
@icontract.ensure(lambda result: isinstance(result, QDialog))
def make_generate_analysis_dialog(
    *,
    run: BenchmarkRun,
    collaborators: GenerateAnalysisCollaborators,
    parent: QWidget | None = None,
) -> QDialog:
    """Build the Generate/Regenerate Analysis dialog (generate_analysis_dialog.md).

    Unlike ``make_run_summary_dialog``, this factory never returns ``None`` -- the
    dialog has no readiness-gate precondition; it always constructs and gates purely
    on Confirm (§8, STORY-065-AC-6).

    Args:
        run: The run under analysis; determines the Generate/Regenerate title and
            button label (§3) and the default provider pre-fill (§5).
        collaborators: The dispatcher, shared dropdown collaborators, and event bus
            this dialog depends on (D-R-06; coding-style.md's 4-parameter rule).
        parent: The dialog's parent widget, if any.

    Returns:
        The constructed, unshown ``QDialog``.
    """
    return GenerateAnalysisDialog(run=run, collaborators=collaborators, parent=parent)


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
