"""Frozen ViewModel structs for ``ui/common_dialogs/`` -- Run Summary (STORY-055) and
Resume Summary / Retry Selection (STORY-057), plus the Generate Analysis dialog's
collaborator bundle (STORY-065).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§3-§7; ``resume_summary_dialog.md`` §3-§7; ``retry_selection_dialog.md`` §4, §6, §7;
``generate_analysis_dialog.md`` §4.
"""

from enum import StrEnum

import msgspec

from ollama_llm_bench.backend.domain import ResultId, RunId, RunMode, TaskIdStr
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.ui.common_dialogs.protocols import RunAnalysisDispatcher
from ollama_llm_bench.ui.shared.model_dropdown import ModelFetcher
from ollama_llm_bench.ui.shared.provider_dropdown import ProviderListSource

__all__: list[str] = [
    "GenerateAnalysisCollaborators",
    "ResumeSummaryViewModel",
    "RetryFilterOption",
    "RetryPickerRow",
    "RetrySelectionViewModel",
    "RunSummaryViewModel",
    "TaskPickerRow",
]


class GenerateAnalysisCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_generate_analysis_dialog`` (coding-style.md's
    4-parameter hard maximum)."""

    dispatcher: RunAnalysisDispatcher
    provider_source: ProviderListSource
    model_fetcher: ModelFetcher
    event_bus: EventBus


class RunSummaryViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Run Summary dialog's full displayed state, in one frozen snapshot.

    Attributes:
        run_mode: The run mode this dialog previews.
        run_name_preview: The previewed run-name display string (§4). A
            simplified preview -- the canonical ``Run N -- ... -- YYYY-MM-DD
            HH:MM`` format needs the next run number and creation timestamp,
            both resolved by the (out-of-scope) run-creation use case at Start.
        test_model_rows: One ``"provider · model"`` row per benchmark target (§4).
        work_to_be_done: The inference/judge call-count summary line; no
            duration is ever shown (§4).
        warnings: Every non-blocking Run Validator finding; empty omits the
            Warnings callout (§4).
        synthetic_matrix_rows: The synthetic prompt matrix rows, ``SYNTHETIC``
            only (§6.1); ``None`` otherwise.
        task_file_summary: The task-file count summary, ``TASKS``/``GRADED``
            only (§6.2, §6.3); ``None`` otherwise.
        judge_summary: The Judge section's summary line, every mode (§6).
        embedding_summary: The embedding readiness summary, ``GRADED`` only
            (§6.3); ``None`` otherwise.
        inference_snapshot_rows: ``"value · setting.key"`` rows for the
            Inference snapshot section (§7) -- limited to the per-run
            overrides actually carried on the request; the full resolved
            snapshot needs the (out-of-scope) ``RunSnapshotBuilder``.
        pipeline_events_rows: ``"value · setting.key"`` rows for the Pipeline
            events snapshot section (§7); same scoping note as above.
        evaluation_phase_rows: ``"value · setting.key"`` rows for the
            Evaluation phases snapshot section, ``GRADED`` only; ``None``
            otherwise.
    """

    run_mode: RunMode
    run_name_preview: str
    test_model_rows: tuple[str, ...]
    work_to_be_done: str
    warnings: tuple[str, ...]
    synthetic_matrix_rows: tuple[str, ...] | None
    task_file_summary: str | None
    judge_summary: str
    embedding_summary: str | None
    inference_snapshot_rows: tuple[str, ...]
    pipeline_events_rows: tuple[str, ...]
    evaluation_phase_rows: tuple[str, ...] | None


class TaskPickerRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row of the Resume Summary dialog's inline Tasks-to-resume picker (§7)."""

    result_id: ResultId
    task_id: TaskIdStr
    status_chip_label: str
    is_checked: bool
    is_enabled: bool


class ResumeSummaryViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Resume Summary dialog's full displayed state, in one frozen snapshot.

    Attributes:
        run_id: The run under review.
        run_name_display: The run's effective display name.
        original_config_rows: "label: value" lines for the Original config section (§4.1).
        current_progress_rows: "label: value" lines for the Current progress section (§4.2).
        blocking_warnings: Unresolved BLOCKING-severity drift warnings, detector order.
        warning_warnings: WARNING-severity drift warnings, detector order.
        settings_note: The fixed §4.4 settings-note line.
        task_rows: The inline Tasks-to-resume picker rows (§7), pre-checked/enabled per the
            pre-check rule and the drift-block approximation (design decision #3).
        intro_legend: The conditional intro legend text (§3).
    """

    run_id: RunId
    run_name_display: str
    original_config_rows: tuple[str, ...]
    current_progress_rows: tuple[str, ...]
    blocking_warnings: tuple[DriftWarning, ...]
    warning_warnings: tuple[DriftWarning, ...]
    settings_note: str
    task_rows: tuple[TaskPickerRow, ...]
    intro_legend: str


class RetryFilterOption(StrEnum):
    """The Retry Selection dialog's Filter dropdown options (§5)."""

    ALL = "all"
    ONLY_FAILED = "only_failed"
    ONLY_INCOMPLETE = "only_incomplete"
    ONLY_COMPLETED = "only_completed"


class RetryPickerRow(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """One row of the Retry Selection dialog's checkable result table (§4, §6, §7)."""

    result_id: ResultId
    task_id: TaskIdStr
    filter_group: RetryFilterOption
    status_chip_label: str
    reason_text: str
    is_checked: bool


class RetrySelectionViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The Retry Selection dialog's full displayed state, in one frozen snapshot."""

    run_id: RunId
    rows: tuple[RetryPickerRow, ...]
