"""Resume widget actions: Clone, Delete, Export Run Analysis, Show run-log (STORY-056).

Source of truth: ``docs/v3_specification/03_Resume_Benchmark_Widget/description.md``
§3.6 (Clone as new retry run algorithm), §3.5/§4.2 (Export/File/Destructive gating),
§9 (EC-RB-8, EC-RB-9). Every function takes its minimal explicit collaborators so
``controller.py`` can wire each to its menu action via ``functools.partial`` --
this module stays a plain function library, never a class.

The delete confirmation is an inline stock ``QMessageBox.question`` (no themed
dialog exists for it and no acceptance criterion tests one); the
``log_file_exists``/``log_file`` derivation lives entirely behind
``FileSystemActions.run_log_path_str`` (STORY-056's own extension of that
Protocol), so this module never touches ``backend/infra`` directly.
"""

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget
import structlog

from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.adapters.native_pickers import NativePickers, SavePickerOptions
from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ResultStatus,
    RunId,
    RunStatus,
)
from ollama_llm_bench.backend.errors import OsAdapterError
from ollama_llm_bench.backend.events import (
    SIGNAL_GLOBAL_MESSAGE,
    SIGNAL_RUN_LIST_CHANGED,
    EventBus,
    GlobalMessageEvent,
    RunListChangedEvent,
)
from ollama_llm_bench.ui.resume_benchmark._internal.view_model_select import effective_run_name
from ollama_llm_bench.ui.resume_benchmark.protocols import ResumeGateway

__all__: list[str] = [
    "clone_as_new_retry_run",
    "confirm_and_delete_run",
    "export_run_analysis",
    "export_table_not_yet_available",
    "show_run_log_file",
]

logger = structlog.get_logger(__name__)

_NO_ANALYSIS_MESSAGE = "No analysis for this run"
_COULD_NOT_OPEN_LOG_MESSAGE = "Could not open the run log file"


def clone_as_new_retry_run(*, gateway: ResumeGateway, source_run_id: RunId) -> RunId:
    """Clone a run as a new retry run per §3.6's five-step algorithm.

    Event emission for the new selection is the controller's responsibility
    (the ``Cloning -> Classify`` transition), so this function stays a plain
    Gateway-only transformation.

    Args:
        gateway: The Resume widget's own adapter gateway.
        source_run_id: The run being cloned.

    Returns:
        The new run's id.
    """
    logger.debug("resume_clone_started", source_run_id=source_run_id)
    source = gateway.get_run(source_run_id)
    tasks = gateway.list_tasks(source_run_id)
    results = gateway.list_results(source_run_id)
    new_run = BenchmarkRun(
        run_id=0,
        run_name=f"{effective_run_name(source)} (retry)",
        timestamp=source.timestamp,
        run_mode=source.run_mode,
        status=RunStatus.INCOMPLETE,
        total_tasks=source.total_tasks,
        completed_tasks=0,
        total_elapsed_ms=0,
        run_analysis=None,
        judge_provider_id=source.judge_provider_id,
        judge_provider_name=source.judge_provider_name,
        embedding_provider_name=source.embedding_provider_name,
        embedding_model_name=source.embedding_model_name,
        schema_version=source.schema_version,
        created_at=source.created_at,
        models=source.models,
        providers=source.providers,
        settings_snapshot=source.settings_snapshot,
    )
    new_run_id = gateway.create_run(new_run)
    gateway.create_tasks(new_run_id, tasks)
    new_results = tuple(_clone_result(result, new_run_id=new_run_id) for result in results)
    gateway.create_results(new_results)
    logger.debug("resume_clone_completed", source_run_id=source_run_id, new_run_id=new_run_id)
    return new_run_id


def _clone_result(result: BenchmarkResult, *, new_run_id: RunId) -> BenchmarkResult:
    """Copy a COMPLETED result as-is; reset every other result to PENDING."""
    if result.status is ResultStatus.COMPLETED:
        return msgspec_replace_run_id(result, new_run_id=new_run_id)
    return BenchmarkResult(
        result_id=result.result_id,
        run_id=new_run_id,
        task_id=result.task_id,
        provider_id=result.provider_id,
        provider_name=result.provider_name,
        model_name=result.model_name,
        status=ResultStatus.PENDING,
        created_at=result.created_at,
    )


def msgspec_replace_run_id(result: BenchmarkResult, *, new_run_id: RunId) -> BenchmarkResult:
    """Return a copy of ``result`` re-parented onto ``new_run_id``, fields unchanged."""
    return BenchmarkResult(
        result_id=result.result_id,
        run_id=new_run_id,
        task_id=result.task_id,
        provider_id=result.provider_id,
        provider_name=result.provider_name,
        model_name=result.model_name,
        status=result.status,
        verdict=result.verdict,
        created_at=result.created_at,
        started_at=result.started_at,
        finished_at=result.finished_at,
        system_prompt_sent=result.system_prompt_sent,
        user_prompt_sent=result.user_prompt_sent,
        raw_response=result.raw_response,
        sanitized_response=result.sanitized_response,
        has_thinking_block=result.has_thinking_block,
        response_char_length=result.response_char_length,
        total_time_ms=result.total_time_ms,
        ttft_ms=result.ttft_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        tokens_per_second=result.tokens_per_second,
        tokens_estimated=result.tokens_estimated,
        sanity_check_passed=result.sanity_check_passed,
        keyword_verdict=result.keyword_verdict,
        cosine_similarity=result.cosine_similarity,
        cosine_verdict=result.cosine_verdict,
        judge_verdict=result.judge_verdict,
        judge_reasoning=result.judge_reasoning,
        judge_time_ms=result.judge_time_ms,
        judge_completion_tokens=result.judge_completion_tokens,
        resolution_layer=result.resolution_layer,
        error_kind=result.error_kind,
        error_message=result.error_message,
        terms=result.terms,
        attempts=result.attempts,
    )


def confirm_and_delete_run(
    *,
    gateway: ResumeGateway,
    event_bus: EventBus,
    run_id: RunId,
    run_name: str,
    parent: QWidget,
) -> bool:
    """Show an inline confirm dialog then delete the run on Yes.

    Args:
        gateway: The Resume widget's own adapter gateway.
        event_bus: Emits ``_run_list_changed`` on a confirmed deletion.
        run_id: The run to delete.
        run_name: The run's effective name, shown in the confirmation text.
        parent: The dialog's parent widget.

    Returns:
        True if the run was deleted; False if the user declined.
    """
    answer = QMessageBox.question(
        parent,
        "Delete run",
        f'Delete "{run_name}"? This cannot be undone.',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer is not QMessageBox.StandardButton.Yes:
        logger.debug("resume_delete_declined", run_id=run_id)
        return False
    gateway.delete_run(run_id)
    logger.debug("resume_delete_confirmed", run_id=run_id)
    event_bus.emit(
        SIGNAL_RUN_LIST_CHANGED,
        RunListChangedEvent(runs=(), change_kind="deleted", affected_run_id=run_id),
    )
    return True


def export_run_analysis(
    *,
    gateway: ResumeGateway,
    native_pickers: NativePickers,
    event_bus: EventBus,
    run_id: RunId,
    effective_run_name: str,
) -> None:
    """Write ``BenchmarkRun.run_analysis`` verbatim to a user-chosen ``.md`` path.

    Args:
        gateway: The Resume widget's own adapter gateway.
        native_pickers: Chooses the export destination.
        event_bus: Emits the outcome toast.
        run_id: The run whose analysis is exported.
        effective_run_name: The run's display name, for the suggested filename.
    """
    run = gateway.get_run(run_id)
    if not run.run_analysis:
        logger.debug("resume_export_analysis_empty", run_id=run_id)
        event_bus.emit(
            SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text=_NO_ANALYSIS_MESSAGE, severity="info")
        )
        return
    path = native_pickers.save_file(
        SavePickerOptions(
            title="Export Run Analysis",
            suggested_name=f"{effective_run_name}_RunAnalysis.md",
            filters=("Markdown (*.md)",),
        )
    )
    if path is None:
        logger.debug("resume_export_analysis_cancelled", run_id=run_id)
        return
    Path(path).write_text(run.run_analysis, encoding="utf-8")
    logger.debug("resume_export_analysis_written", run_id=run_id)
    event_bus.emit(SIGNAL_GLOBAL_MESSAGE, GlobalMessageEvent(text="Exported", severity="info"))


def export_table_not_yet_available(*, event_bus: EventBus) -> None:
    """Toast that Export Summary/Details wiring is not yet available.

    ``ResumeGateway`` (08-E §7b.3) has no ``serialize_table``-equivalent
    method, unlike its sibling ``ResultGateway`` -- so the Export Summary
    (CSV/Markdown) and Export Details (CSV/Markdown) menu items (always
    enabled per AC-4) are gated correctly but cannot be legally wired to
    real export content yet (STORY-056 Escalation; see the story's Notes
    section for the follow-up-story tracking).

    Args:
        event_bus: Emits the toast.
    """
    logger.debug("resume_export_table_not_yet_available")
    event_bus.emit(
        SIGNAL_GLOBAL_MESSAGE,
        GlobalMessageEvent(text="Export not yet available", severity="info"),
    )


def show_run_log_file(
    *, file_system_actions: FileSystemActions, event_bus: EventBus, run_id: RunId, started_at: str
) -> None:
    """Reveal the run's log file; toast a failure message if the OS call raises.

    Args:
        file_system_actions: Derives the run's log path and reveals it.
        event_bus: Emits a failure toast if the reveal call raises.
        run_id: The run whose log file is revealed.
        started_at: The run's ``started_at`` timestamp, for path derivation.
    """
    path_str = file_system_actions.run_log_path_str(run_id=run_id, started_at=started_at)
    try:
        file_system_actions.open_in_file_manager(path_str)
    except OsAdapterError:
        logger.debug("resume_show_log_failed", run_id=run_id)
        event_bus.emit(
            SIGNAL_GLOBAL_MESSAGE,
            GlobalMessageEvent(text=_COULD_NOT_OPEN_LOG_MESSAGE, severity="error"),
        )
        return
    logger.debug("resume_show_log_opened", run_id=run_id)
