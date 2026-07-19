"""Pure ``BenchmarkRun/BenchmarkResult/DriftWarning -> ResumeSummaryViewModel`` derivation
(STORY-057).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/resume_summary_dialog.md`` §4-§7.

Per-row drift blocking is approximated at the section level: any unresolved
BLOCKING warning disables every not-yet-completed row, because the
``DriftWarning`` DTO carries only an aggregate ``pending_results_affected``
count, not per-row result-id attribution (see the story's plan, design
decision #3). No Qt, no I/O.

Display never shows a raw ``provider_id`` (an internal UUID4) -- every
provider reference is resolved to its frozen snapshot ``name`` via
``BenchmarkRun.providers`` before it reaches a display string, per the
project's non-negotiable "``provider_id`` is never shown to the user" rule.
"""

from ollama_llm_bench.backend.domain import (
    BenchmarkResult,
    BenchmarkRun,
    ModelRole,
    ProviderIdStr,
    ResultStatus,
)
from ollama_llm_bench.backend.run_drift import DriftSeverity, DriftWarning
from ollama_llm_bench.ui.common_dialogs.models import ResumeSummaryViewModel, TaskPickerRow

__all__: list[str] = ["select_resume_summary_view_model"]

_NOT_YET_COMPLETED_CHIP_LABELS: dict[ResultStatus, str] = {
    ResultStatus.PENDING: "Pending",
    ResultStatus.RUNNING_INFERENCE: "In progress",
    ResultStatus.AWAITING_KEYWORD_CHECK: "In progress",
    ResultStatus.AWAITING_COSINE_CHECK: "In progress",
    ResultStatus.AWAITING_JUDGE_CHECK: "In progress",
    ResultStatus.FAILED_INFERENCE: "Failed (provider)",
    ResultStatus.FAILED_PROVIDER: "Failed (provider)",
    ResultStatus.FAILED_TIMEOUT: "Failed (timeout)",
    ResultStatus.FAILED_JUDGE_TIMEOUT: "Failed (judge timeout)",
    ResultStatus.ERRORED: "Errored",
}


def select_resume_summary_view_model(
    *,
    run: BenchmarkRun,
    resumable_results: tuple[BenchmarkResult, ...],
    drift_warnings: tuple[DriftWarning, ...],
    drift_override_confirmed: bool = False,
) -> ResumeSummaryViewModel:
    """Derive the Resume Summary dialog's full ViewModel.

    Args:
        run: The run under review.
        resumable_results: Every resumable result row (from ``resumable_results``).
        drift_warnings: The Run Drift Detector's output for this run.
        drift_override_confirmed: Whether the user has ticked "Resume anyway".

    Returns:
        The frozen ViewModel the dialog renders.
    """
    blocking = tuple(w for w in drift_warnings if w.severity is DriftSeverity.BLOCKING)
    warning_only = tuple(w for w in drift_warnings if w.severity is DriftSeverity.WARNING)
    drift_blocks_rows = bool(blocking) and not drift_override_confirmed
    task_rows = tuple(
        _to_task_picker_row(result, drift_blocks_rows=drift_blocks_rows)
        for result in resumable_results
    )
    return ResumeSummaryViewModel(
        run_id=run.run_id,
        run_name_display=run.run_name or f"Run {run.run_id}",
        original_config_rows=_original_config_rows(run),
        current_progress_rows=_current_progress_rows(run, resumable_results),
        blocking_warnings=blocking,
        warning_warnings=warning_only,
        settings_note=(
            "This run resumes against the settings it was created with. "
            "Later changes to application settings do not affect it."
        ),
        task_rows=task_rows,
        intro_legend=(
            "Environment changed since this run started. Review the warnings, then choose "
            "which tasks to resume."
            if drift_warnings
            else "Choose which tasks to resume."
        ),
    )


def _to_task_picker_row(result: BenchmarkResult, *, drift_blocks_rows: bool) -> TaskPickerRow:
    is_completed = result.status is ResultStatus.COMPLETED
    is_enabled = is_completed or not drift_blocks_rows
    is_checked = is_enabled and not is_completed
    return TaskPickerRow(
        result_id=result.result_id,
        task_id=result.task_id,
        status_chip_label=_chip_label(result),
        is_checked=is_checked,
        is_enabled=is_enabled,
    )


def _chip_label(result: BenchmarkResult) -> str:
    if result.status is ResultStatus.COMPLETED:
        verdict = result.verdict.value.upper() if result.verdict is not None else "?"
        return f"Completed · {verdict}"
    return _NOT_YET_COMPLETED_CHIP_LABELS[result.status]


def _original_config_rows(run: BenchmarkRun) -> tuple[str, ...]:
    provider_name_by_id: dict[ProviderIdStr, str] = {p.provider_id: p.name for p in run.providers}
    rows = [f"Mode: {run.run_mode.value}"]
    test_models = [m for m in run.models if m.role is ModelRole.TEST]
    rows.append(f"Test models: {len(test_models)}")
    rows.extend(
        f"{provider_name_by_id.get(m.provider_id, m.provider_id)} · {m.model_name}"
        for m in test_models
    )
    judge_entry = next((m for m in run.models if m.role is ModelRole.JUDGE), None)
    if judge_entry is not None:
        judge_provider_display = provider_name_by_id.get(
            judge_entry.provider_id, judge_entry.provider_id
        )
        rows.append(f"Judge: {judge_provider_display} · {judge_entry.model_name}")
    else:
        rows.append("Judge: none")
    if run.embedding_model_name is not None:
        embedding_provider_display = run.embedding_provider_name or ""
        rows.append(f"Embedding: {embedding_provider_display} · {run.embedding_model_name}")
    return tuple(rows)


def _current_progress_rows(
    run: BenchmarkRun, resumable_results: tuple[BenchmarkResult, ...]
) -> tuple[str, ...]:
    completed = run.completed_tasks
    pending_or_retryable = len(resumable_results)
    return (
        f"Completed: {completed}/{run.total_tasks}",
        f"Resume will process the pending and retryable rows: {pending_or_retryable}",
    )
