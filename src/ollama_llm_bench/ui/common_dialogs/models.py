"""Frozen ViewModel structs for ``ui/common_dialogs/`` -- Run Summary (STORY-055) and
Resume Summary / Retry Selection (STORY-057), the Generate Analysis dialog's
collaborator bundle (STORY-065), and the About / Error dialogs (STORY-070).

Source of truth: ``docs/v3_specification/07_Common_Dialogs/run_summary_dialog.md``
§3-§7; ``resume_summary_dialog.md`` §3-§7; ``retry_selection_dialog.md`` §4, §6, §7;
``generate_analysis_dialog.md`` §4; ``about_dialog.md`` §4-§6; ``error_dialog.md`` §2,
§5-§6.
"""

from collections.abc import Callable
from enum import StrEnum

import msgspec

from ollama_llm_bench.adapters.clipboard import Clipboard
from ollama_llm_bench.adapters.file_system_actions import FileSystemActions
from ollama_llm_bench.backend.domain import ResultId, RunId, RunMode, TaskIdStr
from ollama_llm_bench.backend.events import EventBus
from ollama_llm_bench.backend.run_drift import DriftWarning
from ollama_llm_bench.ui.common_dialogs.protocols import RunAnalysisDispatcher
from ollama_llm_bench.ui.shared.model_dropdown import ModelFetcher
from ollama_llm_bench.ui.shared.provider_dropdown import ProviderListSource

__all__: list[str] = [
    "AboutDialogCollaborators",
    "AboutDialogViewModel",
    "ErrorDialogAction",
    "ErrorDialogPattern",
    "ErrorDialogPayload",
    "GenerateAnalysisCollaborators",
    "ResumeSummaryViewModel",
    "RetryFilterOption",
    "RetryPickerRow",
    "RetrySelectionViewModel",
    "RunSummaryViewModel",
    "TaskPickerRow",
]


class AboutDialogCollaborators(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """Dependency bundle for ``make_about_dialog`` (coding-style.md's 4-parameter
    hard maximum).

    ``event_bus`` backs the Copy-path / Open-folder / repository-link
    confirmation and failure toasts (about_dialog.md §6.1, §8, §11 --
    EC-AB-2, EC-AB-3, EC-AB-7).
    """

    clipboard: Clipboard
    file_system_actions: FileSystemActions
    event_bus: EventBus


class AboutDialogViewModel(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The About dialog's full displayed state, in one frozen snapshot (§4-§5).

    Attributes:
        app_name: The application's display name, rendered as the identity
            block's heading.
        version: The injected build-version string, or ``None`` when no
            version was injected at build time -- the version line is then
            omitted entirely (EC-AB-6).
        description: The fixed muted description of what the application is.
        repository_url: The fixed build-time GitHub repository URL.
        data_folder_path: The resolved, absolute application-data folder
            path, as reported by the path service.
    """

    app_name: str
    version: str | None
    description: str
    repository_url: str
    data_folder_path: str


class ErrorDialogPattern(StrEnum):
    """The Error dialog's three fixed patterns (error_dialog.md §5).

    A UI-local closed value domain describing *how the dialog renders*,
    distinct from ``backend.errors.ErrorCategory``, which classifies *why an
    error happened*. The two are never conflated or reused for each other.
    """

    RECOVERABLE = "recoverable"
    ACTION_AVAILABLE = "action_available"
    FATAL = "fatal"


class ErrorDialogAction(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The action-available pattern's caller-supplied recovery action (§5.2)."""

    label: str
    callback: Callable[[], None]


class ErrorDialogPayload(msgspec.Struct, frozen=True, kw_only=True, gc=False):
    """The caller-supplied Error dialog payload (error_dialog.md §2), rendered
    verbatim with no redaction and no derivation (§6, §7).

    Attributes:
        title: The dialog's heading -- a short statement of what failed.
        message: A one- or two-sentence plain-language description.
        detail: The redacted diagnostic text, or ``None`` when the error is
            self-explanatory (EC-ERR-1) -- omits the detail block and the
            Copy Details button entirely.
        pattern: One of the three fixed patterns (§5).
        action: The recovery action, required when ``pattern`` is
            ``ACTION_AVAILABLE`` (§5.2).
        quit_callback: The clean-shutdown callback, required when ``pattern``
            is ``FATAL`` (§5.3).
    """

    title: str
    message: str
    detail: str | None
    pattern: ErrorDialogPattern
    action: ErrorDialogAction | None = None
    quit_callback: Callable[[], None] | None = None


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
