from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

from ollama_llm_bench.backend.core.models import (
    AppReadinessChangedEvent,
    AppSetting,
    AppSettingsChangedEvent,
    AvgSummaryTableItem,
    BenchmarkFinishedEvent,
    BenchmarkPausedEvent,
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkResumedEvent,
    BenchmarkRun,
    BenchmarkRunStatus,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    BenchmarkTask,
    EmbeddingConfig,
    EvalLayer,
    EvaluationResult,
    HealthProbeResult,
    InferenceResponse,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeEvalRetryEvent,
    JudgeEvalStartedEvent,
    JudgeStartedEvent,
    JudgeSummaryEvent,
    LogEntryType,
    ModelDescriptor,
    ModelSwitchEvent,
    ModeSwitchEvent,
    ParsedModelName,
    PerfAnalysisEvent,
    PreviousRunsRefreshedEvent,
    ProgressUpdateEvent,
    PromptVariant,
    ProviderConfig,
    ProviderHealthCheckEvent,
    ProviderRegistryReloadedEvent,
    ProvidersConfig,
    ProviderSwitchEvent,
    ReadinessVerdict,
    ReporterStatusMsg,
    RunMode,
    RunRenamedEvent,
    StreamChunk,
    StreamingChunkEvent,
    SummaryTableItem,
    TaskCompletedEvent,
    TaskRetryEvent,
    TaskSwitchEvent,
)
from ollama_llm_bench.backend.core.ui_controllers import (
    LogWidgetControllerApi,
    ResultWidgetControllerApi,
    RunConfigControllerApi,
    SettingsWidgetControllerApi,
)


class DataApi(ABC):
    """
    Abstract interface for persistent storage and retrieval of benchmark data.
    """

    @abstractmethod
    def create_benchmark_run(self, benchmark_run: BenchmarkRun) -> int:
        """
        Persist a new benchmark run and assign a unique identifier.

        Args:
            benchmark_run: The benchmark run to store.

        Returns:
            Unique ID assigned to the created run.
        """

    @abstractmethod
    def retrieve_benchmark_run(self, run_id: int) -> BenchmarkRun:
        """
        Fetch a specific benchmark run by its identifier.

        Args:
            run_id: Unique ID of the benchmark run.

        Returns:
            The requested benchmark run instance.
        """

    @abstractmethod
    def retrieve_benchmark_runs(self) -> list[BenchmarkRun]:
        """
        Retrieve all stored benchmark runs.

        Returns:
            List of all benchmark runs.
        """

    @abstractmethod
    def retrieve_benchmark_runs_with_status(self, status: BenchmarkRunStatus) -> list[BenchmarkRun]:
        """
        Retrieve benchmark runs filtered by execution status.

        Args:
            status: Status to filter runs by.

        Returns:
            List of benchmark runs matching the given status.
        """

    @abstractmethod
    def update_benchmark_run(self, benchmark_run: BenchmarkRun) -> None:
        """
        Update an existing benchmark run in storage.

        Args:
            benchmark_run: The updated benchmark run instance.
        """

    @abstractmethod
    def delete_benchmark_run(self, run_id: int) -> None:
        """
        Remove a benchmark run from storage.

        Args:
            run_id: Unique ID of the run to delete.
        """

    @abstractmethod
    def create_benchmark_result(self, benchmark_result: BenchmarkResult) -> int:
        """
        Store a single benchmark result and assign a unique identifier.

        Args:
            benchmark_result: The result to persist.

        Returns:
            Unique ID assigned to the created result.
        """

    @abstractmethod
    def create_benchmark_results(self, benchmark_result: list[BenchmarkResult]) -> None:
        """
        Store multiple benchmark results in bulk.

        Args:
            benchmark_result: List of results to persist.
        """

    @abstractmethod
    def retrieve_benchmark_result(self, result_id: int) -> BenchmarkResult:
        """
        Fetch a specific benchmark result by its identifier.

        Args:
            result_id: Unique ID of the result.

        Returns:
            The requested benchmark result.
        """

    @abstractmethod
    def retrieve_benchmark_results_for_run(self, run_id: int) -> list[BenchmarkResult]:
        """
        Retrieve all results associated with a specific benchmark run.

        Args:
            run_id: Unique ID of the parent benchmark run.

        Returns:
            List of results belonging to the specified run.
        """

    @abstractmethod
    def retrieve_benchmark_results_for_run_with_status(
        self, *, run_id: int, status: BenchmarkResultStatus
    ) -> list[BenchmarkResult]:
        """
        Retrieve benchmark results for a run, filtered by status.

        Args:
            run_id: Unique ID of the parent benchmark run.
            status: Status to filter results by.

        Returns:
            List of results matching the run ID and status.
        """

    @abstractmethod
    def retrieve_status_counts_for_run(self, run_id: int) -> dict[str, int]:
        """Return a mapping of status value → row count for the given run.

        Args:
            run_id: Benchmark run to aggregate.

        Returns:
            Dict mapping BenchmarkResultStatus string values to their counts.
            Keys present only for statuses that have at least one row.
        """

    @abstractmethod
    def update_benchmark_result(self, benchmark_result: BenchmarkResult) -> None:
        """
        Update an existing benchmark result in storage.

        Args:
            benchmark_result: The updated result instance.
        """

    @abstractmethod
    def delete_benchmark_result(self, result_id: int) -> None:
        """
        Remove a benchmark result from storage.

        Args:
            result_id: Unique ID of the result to delete.
        """

    @abstractmethod
    def get_app_setting(self, key: str) -> AppSetting | None:
        """Retrieve an app setting by key, or None if not set.

        Args:
            key: Setting key to look up.

        Returns:
            The AppSetting if found, or None if the key is not stored.
        """

    @abstractmethod
    def set_app_setting(self, *, key: str, value: str) -> None:
        """Persist or update an app setting key-value pair.

        Args:
            key: Setting key to create or overwrite.
            value: New value to store for the key.
        """

    @abstractmethod
    def get_all_app_settings(self) -> list[AppSetting]:
        """Retrieve all stored app settings.

        Returns:
            List of all AppSetting records; empty if none exist.
        """

    @abstractmethod
    def create_prompt_variant(self, variant: PromptVariant) -> None:
        """Store a new prompt variant for a Prompt Eval run.

        Args:
            variant: PromptVariant record to persist.
        """

    @abstractmethod
    def retrieve_prompt_variants_for_run(self, run_id: int) -> list[PromptVariant]:
        """Retrieve all prompt variants associated with a benchmark run.

        Args:
            run_id: Unique ID of the parent benchmark run.

        Returns:
            List of PromptVariant records for the run; empty if none exist.
        """

    @abstractmethod
    def update_run_perf_analysis(self, *, run_id: int, analysis: str) -> None:
        """Persist the LLM-generated performance analysis text for a finished run.

        Args:
            run_id: Unique ID of the benchmark run.
            analysis: Analysis text produced by the judge LLM.
        """

    @abstractmethod
    def update_run_name(self, *, run_id: int, run_name: str) -> None:
        """Persist a user-supplied display name for a benchmark run.

        Args:
            run_id: Unique ID of the benchmark run.
            run_name: New display name for the run.
        """

    @abstractmethod
    def reset_results(self, result_ids: list[int]) -> None:
        """Reset listed result rows to NOT_COMPLETED, clearing all inferred fields.

        Preserved: result_id, run_id, all identity columns (provider, model, task,
        prompt fields), created_at.
        Cleared: status → NOT_COMPLETED; completed_at, raw_response, all scoring
        fields, all eval-layer fields, final_verdict, resolution_layer,
        has_inference_error, inference_error_message, has_judge_error,
        judge_error_message.

        Args:
            result_ids: IDs of the benchmark results to reset.
        """

    @abstractmethod
    def get_model_capability(self, provider_id: str, model_name: str, capability: str) -> int | None:
        """Retrieve a stored model capability flag.

        Args:
            provider_id: Provider identifier (e.g. ``"ollama_local"``).
            model_name: Model identifier (e.g. ``"gemma3:1b"``).
            capability: Capability key (e.g. ``"thinking"``).

        Returns:
            1 if supported, 0 if not supported, -1 if unknown, None if no row exists.
        """

    @abstractmethod
    def set_model_capability(
        self,
        provider_id: str,
        model_name: str,
        capability: str,
        *,
        supported: bool,
        observed_via: str,
        detail: str | None = None,
    ) -> None:
        """Persist or update a model capability observation.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key.
            supported: True if the capability is supported, False otherwise.
            observed_via: Short label describing how the observation was made
                (e.g. ``"warm_up_400"``).
            detail: Optional additional context, such as the raw error message.
        """

    @abstractmethod
    def count_providers(self) -> int:
        """Return the total number of provider rows in the providers table.

        Returns:
            Row count as an integer; 0 if the table is empty.
        """

    @abstractmethod
    def load_all_providers(self) -> list[ProviderConfig]:
        """Load all provider rows from the providers table.

        Returns:
            List of ProviderConfig instances; empty list if no rows exist.
        """

    @abstractmethod
    def upsert_provider(self, provider: ProviderConfig) -> None:
        """Insert or replace a provider row.

        Args:
            provider: ProviderConfig instance to persist.
        """

    @abstractmethod
    def delete_provider(self, provider_id: str) -> None:
        """Delete a provider row by its identifier.

        Args:
            provider_id: The unique provider ID to delete.
        """

    @abstractmethod
    def load_embedding_config(self) -> EmbeddingConfig | None:
        """Load the singleton embedding config row.

        Returns:
            EmbeddingConfig if the row exists, None otherwise.
        """

    @abstractmethod
    def upsert_embedding_config(self, config: EmbeddingConfig) -> None:
        """Insert or replace the singleton embedding config row.

        Args:
            config: EmbeddingConfig instance to persist.
        """

    @abstractmethod
    def replace_all_providers(self, providers: list[ProviderConfig]) -> None:
        """Delete all existing providers and insert providers atomically.

        Args:
            providers: Replacement list of ProviderConfig instances.
        """

    @abstractmethod
    def update_provider_test_status(self, provider_id: str, status: str, tested_at: str, message: str) -> None:
        """Persist the last health-check result for a provider row.

        Args:
            provider_id: Provider to update.
            status: Health status string (e.g. "healthy" or "down").
            tested_at: ISO-8601 UTC timestamp of the test.
            message: Human-readable result message.
        """


class ModelCapabilityServiceApi(Protocol):
    """Protocol for querying and persisting model capability observations."""

    def supports_thinking(self, provider_id: str, model_name: str) -> bool | None:
        """Return whether the model supports extended thinking.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.

        Returns:
            True if supported, False if not supported, None if unknown.
        """
        ...

    def remember(
        self,
        provider_id: str,
        model_name: str,
        capability: str,
        *,
        supported: bool,
        observed_via: str,
        detail: str | None = None,
    ) -> None:
        """Persist a capability observation.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key.
            supported: True if the capability is supported, False otherwise.
            observed_via: Short label describing how the observation was made.
            detail: Optional additional context.
        """
        ...

    def get(self, provider_id: str, model_name: str, capability: str) -> bool | None:
        """Retrieve a stored capability flag.

        Args:
            provider_id: Provider identifier.
            model_name: Model identifier.
            capability: Capability key.

        Returns:
            True if supported, False if not supported, None if unknown or absent.
        """
        ...


class ResultApi(ABC):
    """
    Abstract interface for computing and retrieving benchmark summaries.
    """

    def __init__(self, *, data_api: DataApi):
        self._data_api = data_api

    @abstractmethod
    def retrieve_avg_benchmark_results_for_run(self, run_id: int) -> list[AvgSummaryTableItem]:
        """
        Compute and retrieve averaged performance metrics for all models in a run.

        Args:
            run_id: Unique ID of the benchmark run.

        Returns:
            List of averaged summary items, one per model.
        """

    @abstractmethod
    def retrieve_detailed_benchmark_results_for_run(self, run_id: int) -> list[SummaryTableItem]:
        """
        Retrieve detailed per-task results for a benchmark run.

        Args:
            run_id: Unique ID of the benchmark run.

        Returns:
            List of detailed summary items for each task and model combination.
        """


class BenchmarkFlowApi(ABC):
    """
    Abstract interface for controlling the execution flow of benchmarks.
    """

    def __init__(
        self,
        *,
        data_api: DataApi,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._data_api = data_api

    @abstractmethod
    def start_execution(self, run_id: int) -> None:
        """
        Begin executing a benchmark run asynchronously.

        Args:
            run_id: Identifier of the run to execute.
        """

    @abstractmethod
    def stop_execution(self) -> None:
        """
        Request cancellation of the currently running benchmark.
        """

    @abstractmethod
    def is_running(self) -> bool:
        """
        Check whether a benchmark run is currently in progress.

        Returns:
            True if a run is active, False otherwise.
        """

    @abstractmethod
    def get_current_run_id(self) -> int | None:
        """
        Retrieve the ID of the currently executing run.

        Returns:
            Run ID if one is running, None otherwise.
        """

    @abstractmethod
    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None:
        """
        Register a listener for execution start/stop events.

        Args:
            callback: Function to invoke with True (started) or False (stopped).
        """

    @abstractmethod
    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None:
        """
        Register a listener for raw output logs during execution.

        Args:
            callback: Function to invoke with output strings.
        """

    @abstractmethod
    def pause_execution(self) -> None:
        """Pause the running benchmark at the next task boundary."""

    @abstractmethod
    def resume_execution(self) -> None:
        """Resume a paused benchmark run."""

    @abstractmethod
    def shutdown(self, *, timeout_ms: int = 5000) -> None:
        """Stop any running benchmark and wait for the worker thread to finish.

        Args:
            timeout_ms: Maximum milliseconds to wait for clean thread termination.
        """

    @abstractmethod
    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """
        Register a listener for progress updates during benchmark execution.

        Args:
            callback: Function to invoke with progress status messages.
        """


class EventBus(ABC):
    """
    Abstract interface for a publish-subscribe system to decouple application components.
    """

    @abstractmethod
    def subscribe_to_run_id_changed(
        self, callback: Callable[[int | None], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to changes in the active run identifier.

        Args:
            callback: Function to call with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_run_ids_changed(
        self, callback: Callable[[list[tuple[int, str]]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to changes in the list of available run IDs and names.

        Args:
            callback: Function to call with updated list of (ID, name) tuples.
        """

    @abstractmethod
    def subscribe_to_models_test_changed(
        self, callback: Callable[[list[str]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to changes in the list of models used for testing.

        Args:
            callback: Function to call with updated model names.
        """

    @abstractmethod
    def subscribe_to_models_judge_changed(
        self, callback: Callable[[str], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to changes in the model used for judging results.

        Args:
            callback: Function to call with the new judge model name.
        """

    @abstractmethod
    def subscribe_to_log_clean(self, callback: Callable[[], None], *, parent: QObject | None = None) -> None:
        """
        Subscribe to log clear events.

        Args:
            callback: Function to invoke when logs should be cleared.
        """

    @abstractmethod
    def subscribe_to_log_append(self, callback: Callable[[str], None], *, parent: QObject | None = None) -> None:
        """
        Subscribe to log append events.

        Args:
            callback: Function to invoke with new log lines.
        """

    @abstractmethod
    def subscribe_to_table_summary_data_changed(
        self,
        callback: Callable[[list[AvgSummaryTableItem]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """
        Subscribe to updates in the summary results table.

        Args:
            callback: Function to invoke with new summary data.
        """

    @abstractmethod
    def subscribe_to_table_detailed_data_change(
        self, callback: Callable[[list[SummaryTableItem]], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to updates in the detailed results table.

        Args:
            callback: Function to invoke with new detailed data.
        """

    @abstractmethod
    def subscribe_to_background_thread_is_running(
        self, callback: Callable[[bool], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to background task execution status.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """

    @abstractmethod
    def subscribe_to_background_thread_progress(
        self, callback: Callable[[ReporterStatusMsg], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to progress updates from background tasks.

        Args:
            callback: Function to invoke with progress status messages.
        """

    @abstractmethod
    def subscribe_to_global_event_msg(self, callback: Callable[[str], None], *, parent: QObject | None = None) -> None:
        """
        Subscribe to global application event messages.

        Args:
            callback: Function to invoke with event message strings.
        """

    @abstractmethod
    def emit_run_id_changed(self, value: int | None) -> None:
        """
        Broadcast a change in the active run ID.

        Args:
            value: New run ID or None.
        """

    @abstractmethod
    def emit_run_ids_changed(self, value: list[tuple[int, str]]) -> None:
        """
        Broadcast a change in the list of available run IDs.

        Args:
            value: Updated list of (ID, name) tuples.
        """

    @abstractmethod
    def emit_models_test_changed(self, value: list[str]) -> None:
        """
        Broadcast a change in the test model list.

        Args:
            value: Updated list of model names.
        """

    @abstractmethod
    def emit_models_judge_changed(self, value: str) -> None:
        """
        Broadcast a change in the judge model.

        Args:
            value: New judge model name.
        """

    @abstractmethod
    def emit_log_clean(self) -> None:
        """
        Broadcast a request to clear all logs.
        """

    @abstractmethod
    def emit_log_append(self, value: str) -> None:
        """
        Broadcast a new log entry.

        Args:
            value: Log line to append.
        """

    @abstractmethod
    def emit_table_summary_data_changed(self, value: list[AvgSummaryTableItem]) -> None:
        """
        Broadcast updated summary table data.

        Args:
            value: New list of summary items.
        """

    @abstractmethod
    def emit_table_detailed_data_change(self, value: list[SummaryTableItem]) -> None:
        """
        Broadcast updated detailed table data.

        Args:
            value: New list of detailed items.
        """

    @abstractmethod
    def emit_background_thread_is_running(self, value: bool) -> None:
        """
        Broadcast the current execution state of background tasks.

        Args:
            value: True if running, False otherwise.
        """

    @abstractmethod
    def emit_background_thread_progress(self, value: ReporterStatusMsg) -> None:
        """
        Broadcast a progress update from background execution.

        Args:
            value: Status message describing current progress.
        """

    @abstractmethod
    def emit_global_event_msg(self, value: str) -> None:
        """
        Broadcast a general application event message.

        Args:
            value: Message to broadcast.
        """

    @abstractmethod
    def subscribe_to_benchmark_started(
        self, callback: Callable[[BenchmarkStartedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark start events.

        Args:
            callback: Function to invoke with BenchmarkStartedEvent when a run begins.
        """
        ...

    @abstractmethod
    def emit_benchmark_started(self, event: BenchmarkStartedEvent) -> None:
        """
        Broadcast a benchmark start event.

        Args:
            event: BenchmarkStartedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_benchmark_paused(
        self, callback: Callable[[BenchmarkPausedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark pause events.

        Args:
            callback: Function to invoke with BenchmarkPausedEvent when a run pauses.
        """
        ...

    @abstractmethod
    def emit_benchmark_paused(self, event: BenchmarkPausedEvent) -> None:
        """
        Broadcast a benchmark pause event.

        Args:
            event: BenchmarkPausedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_benchmark_resumed(
        self, callback: Callable[[BenchmarkResumedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark resume events.

        Args:
            callback: Function to invoke with BenchmarkResumedEvent when a run resumes.
        """
        ...

    @abstractmethod
    def emit_benchmark_resumed(self, event: BenchmarkResumedEvent) -> None:
        """
        Broadcast a benchmark resume event.

        Args:
            event: BenchmarkResumedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_benchmark_stopped(
        self, callback: Callable[[BenchmarkStoppedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark stop events.

        Args:
            callback: Function to invoke with BenchmarkStoppedEvent when a run stops.
        """
        ...

    @abstractmethod
    def emit_benchmark_stopped(self, event: BenchmarkStoppedEvent) -> None:
        """
        Broadcast a benchmark stop event.

        Args:
            event: BenchmarkStoppedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_benchmark_finished(
        self, callback: Callable[[BenchmarkFinishedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark finish events.

        Args:
            callback: Function to invoke with BenchmarkFinishedEvent when a run completes.
        """
        ...

    @abstractmethod
    def emit_benchmark_finished(self, event: BenchmarkFinishedEvent) -> None:
        """
        Broadcast a benchmark finish event.

        Args:
            event: BenchmarkFinishedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_provider_switch(
        self, callback: Callable[[ProviderSwitchEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to provider switch events.

        Args:
            callback: Function to invoke with ProviderSwitchEvent when the active provider changes.
        """
        ...

    @abstractmethod
    def emit_provider_switch(self, event: ProviderSwitchEvent) -> None:
        """
        Broadcast a provider switch event.

        Args:
            event: ProviderSwitchEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_provider_health_check(
        self, callback: Callable[[ProviderHealthCheckEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to provider health check events.

        Args:
            callback: Function to invoke with ProviderHealthCheckEvent for connectivity status.
        """
        ...

    @abstractmethod
    def emit_provider_health_check(self, event: ProviderHealthCheckEvent) -> None:
        """
        Broadcast a provider health check event.

        Args:
            event: ProviderHealthCheckEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_model_switch(
        self, callback: Callable[[ModelSwitchEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to model switch events.

        Args:
            callback: Function to invoke with ModelSwitchEvent when the selected model changes.
        """
        ...

    @abstractmethod
    def emit_model_switch(self, event: ModelSwitchEvent) -> None:
        """
        Broadcast a model switch event.

        Args:
            event: ModelSwitchEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_task_switch(
        self, callback: Callable[[TaskSwitchEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to task switch events.

        Args:
            callback: Function to invoke with TaskSwitchEvent when the active task changes.
        """
        ...

    @abstractmethod
    def emit_task_switch(self, event: TaskSwitchEvent) -> None:
        """
        Broadcast a task switch event.

        Args:
            event: TaskSwitchEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_task_retry(
        self, callback: Callable[[TaskRetryEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to task retry events.

        Args:
            callback: Function to invoke with TaskRetryEvent when a task is retried.
        """
        ...

    @abstractmethod
    def emit_task_retry(self, event: TaskRetryEvent) -> None:
        """
        Broadcast a task retry event.

        Args:
            event: TaskRetryEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_mode_switch(
        self, callback: Callable[[ModeSwitchEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to benchmark mode switch events.

        Args:
            callback: Function to invoke with ModeSwitchEvent when the mode changes.
        """
        ...

    @abstractmethod
    def emit_mode_switch(self, event: ModeSwitchEvent) -> None:
        """
        Broadcast a mode switch event.

        Args:
            event: ModeSwitchEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_task_completed(
        self, callback: Callable[[TaskCompletedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to task completion events.

        Args:
            callback: Function to invoke with TaskCompletedEvent when a task finishes.
        """
        ...

    @abstractmethod
    def emit_task_completed(self, event: TaskCompletedEvent) -> None:
        """
        Broadcast a task completion event.

        Args:
            event: TaskCompletedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_judge_started(
        self, callback: Callable[[JudgeStartedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to judge start events.

        Args:
            callback: Function to invoke with JudgeStartedEvent when judging begins.
        """
        ...

    @abstractmethod
    def emit_judge_started(self, event: JudgeStartedEvent) -> None:
        """
        Broadcast a judge start event.

        Args:
            event: JudgeStartedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_judge_completed(
        self, callback: Callable[[JudgeCompletedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to judge completion events.

        Args:
            callback: Function to invoke with JudgeCompletedEvent when judging finishes.
        """
        ...

    @abstractmethod
    def emit_judge_completed(self, event: JudgeCompletedEvent) -> None:
        """
        Broadcast a judge completion event.

        Args:
            event: JudgeCompletedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_judge_eval_started(
        self, callback: Callable[[JudgeEvalStartedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to judge evaluation start events.

        Args:
            callback: Function to invoke with JudgeEvalStartedEvent when evaluation begins.
        """
        ...

    @abstractmethod
    def emit_judge_eval_started(self, event: JudgeEvalStartedEvent) -> None:
        """
        Broadcast a judge evaluation start event.

        Args:
            event: JudgeEvalStartedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_judge_eval_retry(
        self, callback: Callable[[JudgeEvalRetryEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to judge evaluation retry events.

        Args:
            callback: Function to invoke with JudgeEvalRetryEvent when evaluation is retried.
        """
        ...

    @abstractmethod
    def emit_judge_eval_retry(self, event: JudgeEvalRetryEvent) -> None:
        """
        Broadcast a judge evaluation retry event.

        Args:
            event: JudgeEvalRetryEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_streaming_chunk(
        self, callback: Callable[[StreamingChunkEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to streaming chunk events.

        Args:
            callback: Function to invoke with StreamingChunkEvent for each token streamed.
        """
        ...

    @abstractmethod
    def emit_streaming_chunk(self, event: StreamingChunkEvent) -> None:
        """
        Broadcast a streaming chunk event.

        Args:
            event: StreamingChunkEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_inference_started(
        self, callback: Callable[[InferenceStartedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to inference start events.

        Args:
            callback: Function to invoke with InferenceStartedEvent when inference begins.
        """
        ...

    @abstractmethod
    def emit_inference_started(self, event: InferenceStartedEvent) -> None:
        """
        Broadcast an inference start event.

        Args:
            event: InferenceStartedEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_progress_update(
        self, callback: Callable[[ProgressUpdateEvent], None], *, parent: QObject | None = None
    ) -> None:
        """
        Subscribe to progress update events.

        Args:
            callback: Function to invoke with ProgressUpdateEvent for execution progress.
        """
        ...

    @abstractmethod
    def emit_progress_update(self, event: ProgressUpdateEvent) -> None:
        """
        Broadcast a progress update event.

        Args:
            event: ProgressUpdateEvent to emit.
        """
        ...

    @abstractmethod
    def subscribe_to_judge_summary(
        self, callback: Callable[[JudgeSummaryEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to judge summary events.

        Args:
            callback: function to invoke with the generated JudgeSummaryEvent.
        """

    @abstractmethod
    def emit_judge_summary(self, event: JudgeSummaryEvent) -> None:
        """Emit a judge summary event.

        Args:
            event: the JudgeSummaryEvent containing run_id and summary_text.
        """

    @abstractmethod
    def subscribe_to_perf_analysis(
        self, callback: Callable[[PerfAnalysisEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to performance analysis events.

        Args:
            callback: Function to invoke with the generated PerfAnalysisEvent.
        """

    @abstractmethod
    def emit_perf_analysis(self, event: PerfAnalysisEvent) -> None:
        """Emit a performance analysis event.

        Args:
            event: PerfAnalysisEvent containing run_id and analysis_text.
        """

    @abstractmethod
    def subscribe_to_app_settings_changed(
        self, callback: Callable[[AppSettingsChangedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to app settings changed events.

        Args:
            callback: Function to invoke with the AppSettingsChangedEvent when settings are saved.
        """

    @abstractmethod
    def emit_app_settings_changed(self, event: AppSettingsChangedEvent) -> None:
        """Emit an app settings changed event.

        Args:
            event: AppSettingsChangedEvent with the keys that changed.
        """

    @abstractmethod
    def subscribe_to_provider_registry_reloaded(
        self,
        callback: Callable[[ProviderRegistryReloadedEvent], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to provider registry reloaded events.

        Args:
            callback: Function to invoke with the event after reload completes.
        """

    @abstractmethod
    def emit_provider_registry_reloaded(self, event: ProviderRegistryReloadedEvent) -> None:
        """Emit a provider registry reloaded event.

        Args:
            event: The reload completion event.
        """

    @abstractmethod
    def subscribe_to_previous_runs_refreshed(
        self, callback: Callable[[PreviousRunsRefreshedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to previous runs refreshed events.

        Args:
            callback: Function to invoke after the Previous Runs list is refreshed from DB.
        """

    @abstractmethod
    def emit_previous_runs_refreshed(self, event: PreviousRunsRefreshedEvent) -> None:
        """Emit a previous runs refreshed event.

        Args:
            event: The refresh completion event.
        """

    @abstractmethod
    def emit_app_readiness_changed(self, event: AppReadinessChangedEvent) -> None:
        """Emit an app readiness changed event.

        Args:
            event: The readiness snapshot to broadcast.
        """

    @abstractmethod
    def subscribe_to_app_readiness_changed(
        self, callback: Callable[[AppReadinessChangedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to app readiness changed events.

        Args:
            callback: Function to invoke with the new readiness snapshot.
        """

    @abstractmethod
    def subscribe_to_run_renamed(
        self, callback: Callable[[RunRenamedEvent], None], *, parent: QObject | None = None
    ) -> None:
        """Subscribe to run renamed events.

        Args:
            callback: Function to invoke with the RunRenamedEvent when a run is renamed.
        """

    @abstractmethod
    def emit_run_renamed(self, event: RunRenamedEvent) -> None:
        """Broadcast a run renamed event.

        Args:
            event: RunRenamedEvent containing the run_id and new_name.
        """


class AppContext(ABC):
    """
    Abstract interface providing access to core application components and controllers.
    """

    @abstractmethod
    def get_event_bus(self) -> EventBus:
        """
        Retrieve the global event bus instance.

        Returns:
            EventBus for pub/sub communication.
        """

    @abstractmethod
    def get_log_widget_controller_api(self) -> LogWidgetControllerApi:
        """
        Retrieve the controller for the log display widget.

        Returns:
            Controller API for managing log output UI.
        """

    @abstractmethod
    def get_result_widget_controller_api(self) -> ResultWidgetControllerApi:
        """
        Retrieve the controller for the results display widget.

        Returns:
            Controller API for managing results UI.
        """

    @abstractmethod
    def get_data_api(self) -> DataApi:
        """
        Retrieve the data persistence interface.

        Returns:
            DataApi instance for storage operations.
        """

    @abstractmethod
    def get_result_api(self) -> ResultApi:
        """
        Retrieve the result computation interface.

        Returns:
            ResultApi instance for generating summaries.
        """

    @abstractmethod
    def send_initialization_events(self) -> None:
        """
        Trigger initial event broadcasts to synchronize UI components.
        """

    @abstractmethod
    def get_provider_registry(self) -> ProviderRegistryApi:
        """
        Retrieve the provider registry interface.

        Returns:
            ProviderRegistryApi for accessing LLM and embedding providers.
        """

    @abstractmethod
    def get_app_settings_service(self) -> AppSettingsServiceApi:
        """Retrieve the application settings KV-store service.

        Returns:
            AppSettingsServiceApi for reading and writing typed application settings.
        """

    @abstractmethod
    def get_task_file_loader(self) -> TaskFileLoaderApi:
        """Retrieve the V2 benchmark task file loader.

        Returns:
            TaskFileLoaderApi for loading tasks from YAML files or directories.
        """

    @abstractmethod
    def get_judge_prompt_service(self) -> JudgePromptServiceApi:
        """Retrieve the judge prompt builder service.

        Returns:
            JudgePromptServiceApi for constructing inference and judge prompts.
        """

    @abstractmethod
    def get_log_file_writer(self) -> LogFileWriterApi:
        """Retrieve the log file writer service.

        Returns:
            LogFileWriterApi for writing structured benchmark log entries to disk.
        """

    @abstractmethod
    def get_settings_widget_controller(self) -> SettingsWidgetControllerApi:
        """Retrieve the settings dialog controller.

        Returns:
            SettingsWidgetControllerApi for provider and feature flag management.
        """

    @abstractmethod
    def get_run_config_controller(self) -> RunConfigControllerApi:
        """Retrieve the unified run configuration controller.

        Returns:
            RunConfigControllerApi for provider/model discovery and benchmark lifecycle.
        """

    @abstractmethod
    def get_benchmark_flow_api(self) -> BenchmarkFlowApi:
        """Retrieve the benchmark execution flow controller.

        Returns:
            BenchmarkFlowApi for lifecycle control of benchmark runs.
        """


class TableSerializerApi(ABC):
    """
    Abstract interface for exporting benchmark result tables to files.
    """

    @abstractmethod
    def save_summary_as_csv(self, items: list[AvgSummaryTableItem]) -> None:
        """
        Export averaged summary results to a CSV file.

        Args:
            items: List of summary items to save.
        """

    @abstractmethod
    def save_summary_as_md(self, items: list[AvgSummaryTableItem]) -> None:
        """
        Export averaged summary results to a Markdown file.

        Args:
            items: List of summary items to save.
        """

    @abstractmethod
    def save_details_as_csv(self, items: list[SummaryTableItem]) -> None:
        """
        Export detailed benchmark results to a CSV file.

        Args:
            items: List of detailed items to save.
        """

    @abstractmethod
    def save_details_as_md(self, items: list[SummaryTableItem]) -> None:
        """
        Export detailed benchmark results to a Markdown file.

        Args:
            items: List of detailed items to save.
        """

    @abstractmethod
    def save_summary_as_csv_to_path(self, path: Path, items: list[AvgSummaryTableItem]) -> None:
        """Export averaged summary results to a CSV file at the given path.

        Args:
            path: Full file path to write to.
            items: List of averaged summary items to save.
        """

    @abstractmethod
    def save_summary_as_md_to_path(self, path: Path, items: list[AvgSummaryTableItem]) -> None:
        """Export averaged summary results to a Markdown file at the given path.

        Args:
            path: Full file path to write to.
            items: List of averaged summary items to save.
        """

    @abstractmethod
    def save_details_as_csv_to_path(self, path: Path, items: list[SummaryTableItem]) -> None:
        """Export detailed benchmark results to a CSV file at the given path.

        Args:
            path: Full file path to write to.
            items: List of detailed result items to save.
        """

    @abstractmethod
    def save_details_as_md_to_path(self, path: Path, items: list[SummaryTableItem]) -> None:
        """Export detailed benchmark results to a Markdown file at the given path.

        Args:
            path: Full file path to write to.
            items: List of detailed result items to save.
        """


class ProviderConfigLoaderApi(Protocol):
    """Protocol for loading and querying the providers.yaml configuration file."""

    def load(self, path: Path) -> ProvidersConfig:
        """Load and validate a providers.yaml file.

        Args:
            path: Path to the providers.yaml file.

        Returns:
            Parsed and validated ProvidersConfig.
        """
        ...

    def get_enabled_providers(self, config: ProvidersConfig) -> list[ProviderConfig]:
        """Return only the enabled providers from a loaded config.

        Args:
            config: A previously loaded ProvidersConfig.

        Returns:
            List of ProviderConfig instances where enabled is True.
        """
        ...

    def resolve_env_vars(self, providers: list[ProviderConfig]) -> list[ProviderConfig]:
        """Resolve ${ENV_VAR} placeholders in api_key_raw for each provider.

        Args:
            providers: List of ProviderConfig instances with raw (unresolved) api_key_raw fields.

        Returns:
            List of ProviderConfig instances with api_key field populated from environment variables.
        """
        ...

    def serialize_config(self, config: ProvidersConfig) -> dict[str, object]:
        """Serialize a ProvidersConfig to a YAML-dumpable dict.

        Args:
            config: The ProvidersConfig to serialize.

        Returns:
            A dict ready for yaml.safe_dump.
        """
        ...


class AppReadinessServiceApi(Protocol):
    """Protocol for the app-wide readiness probe service."""

    def compute_snapshot(self) -> AppReadinessChangedEvent: ...

    def verdict_for(self, mode: RunMode, snapshot: AppReadinessChangedEvent) -> ReadinessVerdict: ...


class LLMProviderApi(Protocol):
    """Protocol for synchronous and streaming LLM inference providers."""

    @property
    def provider_id(self) -> str:
        """
        Retrieve the unique identifier of this provider.

        Returns:
            Unique provider ID string (e.g., "openai", "anthropic", "gemini").
        """
        ...

    @property
    def provider_type(self) -> str:
        """
        Retrieve the provider type classification.

        Returns:
            Provider type string indicating the service category.
        """
        ...

    def get_available_models(self) -> list[ModelDescriptor]:
        """
        Retrieve the list of models available from this provider.

        Returns:
            List of ModelDescriptor objects describing available models.
        """
        ...

    def inference_sync(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        reasoning_effort: str = "medium",
        response_format: dict[str, str] | None = None,
    ) -> InferenceResponse:
        """
        Perform synchronous inference (blocking) with the specified model.

        Args:
            model: Name of the model to use.
            messages: List of message dictionaries with role and content.
            temperature: Sampling temperature controlling randomness (0.0-1.0).
            max_tokens: Maximum tokens to generate, or None for default.
            reasoning_effort: Reasoning effort level for models that support extended thinking.
            response_format: Optional format hint, e.g. ``{"type": "json_object"}`` for
                providers that support structured output.

        Returns:
            InferenceResponse containing the generated text and metadata.
        """
        ...

    def inference_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        reasoning_effort: str = "medium",
    ) -> Generator[StreamChunk, None, InferenceResponse]:
        """
        Perform streaming inference, yielding tokens as they are generated.

        Args:
            model: Name of the model to use.
            messages: List of message dictionaries with role and content.
            temperature: Sampling temperature controlling randomness (0.0-1.0).
            max_tokens: Maximum tokens to generate, or None for default.
            reasoning_effort: Reasoning effort level for models that support extended thinking.

        Yields:
            StreamChunk objects containing partial response tokens.

        Returns:
            Final InferenceResponse after streaming completes.
        """
        ...

    def supports_structured_output(self) -> bool:
        """
        Check whether this provider supports structured output (JSON mode).

        Returns:
            True if structured output is supported, False otherwise.
        """
        ...

    def supports_streaming(self) -> bool:
        """
        Check whether this provider supports token streaming.

        Returns:
            True if streaming is supported, False otherwise.
        """
        ...

    def warm_up(self, model: str) -> bool:
        """
        Load and initialize a model to reduce first-inference latency.

        Args:
            model: Name of the model to warm up.

        Returns:
            True if warm-up succeeded, False otherwise.
        """
        ...

    def probe_health(self) -> HealthProbeResult:
        """Perform a live network probe to verify reachability and credentials.

        Returns:
            HealthProbeResult with reachable=True on success, or reachable=False
            with error_message on any connection or authentication failure.
        """
        ...


class EmbeddingProviderApi(Protocol):
    """Protocol for providers that produce vector embeddings."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        """
        Encode text strings into vector embeddings.

        Args:
            texts: List of text strings to encode.

        Returns:
            List of embedding vectors, one per input text, each a list of floats.
        """
        ...


class ProviderRegistryApi(Protocol):
    """Protocol for the registry that constructs and exposes all LLM providers."""

    def load(self) -> None:
        """
        Load all configured LLM providers from the providers.yaml file.
        """
        ...

    def reload(self) -> None:
        """
        Reload the providers.yaml file and refresh all provider instances.
        """
        ...

    def get_provider(self, provider_id: str) -> LLMProviderApi:
        """
        Retrieve a specific provider by its unique identifier.

        Args:
            provider_id: Unique ID of the provider to retrieve.

        Returns:
            LLMProviderApi instance for the requested provider.
        """
        ...

    def get_all_providers(self) -> list[LLMProviderApi]:
        """
        Retrieve all loaded providers, both enabled and disabled.

        Returns:
            List of all LLMProviderApi instances.
        """
        ...

    def get_enabled_providers(self) -> list[LLMProviderApi]:
        """
        Retrieve only the providers that are marked as enabled in the configuration.

        Returns:
            List of enabled LLMProviderApi instances.
        """
        ...

    def get_embedding_provider(self) -> EmbeddingProviderApi:
        """
        Retrieve the configured embedding provider.

        Returns:
            EmbeddingProviderApi instance for vector embeddings.
        """
        ...

    def get_config(self) -> ProvidersConfig | None:
        """Return the currently loaded ProvidersConfig, or None if load() has not succeeded."""
        ...


class ModelNameParserApi(Protocol):
    """Parses Ollama-style model name strings into structured components."""

    def parse(self, model_name: str) -> ParsedModelName:
        """
        Parse a model name string into named components.

        Args:
            model_name: Model name string (e.g., "registry/namespace/repo:tag").

        Returns:
            ParsedModelName containing registry, namespace, repo, and tag.
        """
        ...


@runtime_checkable
class TaskFileLoaderApi(Protocol):
    """Protocol for loading V2 benchmark tasks from YAML files or directories."""

    def load_tasks(self, file_paths: list[Path]) -> list[BenchmarkTask]:
        """
        Load benchmark tasks from a list of YAML file paths.

        Args:
            file_paths: List of paths to YAML task files to load.

        Returns:
            List of BenchmarkTask objects parsed from the files.
        """
        ...

    def get_task(self, task_id: str) -> BenchmarkTask:
        """
        Retrieve a previously loaded task by its identifier.

        Args:
            task_id: Unique ID of the task to retrieve.

        Returns:
            The requested BenchmarkTask.
        """
        ...

    def scan_directory(self, directory: Path) -> list[Path]:
        """
        Scan a directory for YAML benchmark task files.

        Args:
            directory: Path to directory containing task files.

        Returns:
            List of paths to YAML files found in the directory.
        """
        ...


@runtime_checkable
class EvaluatorApi(Protocol):
    """Protocol for evaluation layers 1-3 (rule-based, keyword, cosine)."""

    @property
    def layer(self) -> EvalLayer:
        """
        Retrieve the evaluation layer this evaluator implements.

        Returns:
            EvalLayer enum value identifying this evaluator's layer.
        """
        ...

    def evaluate(self, task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult:
        """
        Evaluate a benchmark result against its task.

        Args:
            task: The benchmark task definition.
            result: The result to evaluate.

        Returns:
            EvaluationResult containing score and metadata.
        """
        ...


@runtime_checkable
class LLMJudgeEvaluatorApi(Protocol):
    """Protocol for evaluation layer 4 — LLM-based judge with provider context."""

    @property
    def layer(self) -> EvalLayer:
        """
        Retrieve the evaluation layer this evaluator implements.

        Returns:
            EvalLayer enum value for layer 4 (LLM judge).
        """
        ...

    def evaluate(
        self,
        task: BenchmarkTask,
        result: BenchmarkResult,
        *,
        judge_provider_id: str,
        judge_model: str,
    ) -> EvaluationResult:
        """
        Evaluate a result using an LLM judge from a specific provider.

        Args:
            task: The benchmark task definition.
            result: The result to evaluate.
            judge_provider_id: ID of the provider to use for judging.
            judge_model: Model name to use from the judge provider.

        Returns:
            EvaluationResult containing the judge's score and reasoning.
        """
        ...


@runtime_checkable
class JudgeSummaryServiceApi(Protocol):
    """Generates a prose summary of a completed benchmark run using the judge model."""

    def generate_summary(
        self,
        *,
        run: BenchmarkRun,
        results: list[BenchmarkResult],
    ) -> str:
        """Generate and return a prose summary string.

        Args:
            run: the completed benchmark run metadata.
            results: all benchmark results for this run.

        Returns:
            Prose summary text from the judge model.
        """
        ...


@runtime_checkable
class JudgePromptServiceApi(Protocol):
    """Protocol for building inference and judge prompts from benchmark tasks."""

    def build_inference_prompt(self, task: BenchmarkTask) -> tuple[str, str]:
        """
        Construct a prompt for inference (testing phase).

        Args:
            task: The benchmark task to build a prompt for.

        Returns:
            Tuple of (system_prompt, user_prompt).
        """
        ...

    def build_judge_prompt(self, task: BenchmarkTask, result: BenchmarkResult) -> tuple[str, str]:
        """
        Construct a prompt for judge evaluation.

        Args:
            task: The benchmark task being evaluated.
            result: The result (model response) to evaluate.

        Returns:
            Tuple of (system_prompt, judge_prompt) for the judge model.
        """
        ...


@runtime_checkable
class AppSettingsServiceApi(Protocol):
    """Protocol for reading and writing typed application settings from persistent storage."""

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Retrieve a string setting value.

        Args:
            key: Setting key to look up.
            default: Value to return if key is not found.

        Returns:
            The setting value, or default if not set.
        """
        ...

    def set(self, key: str, value: str) -> None:
        """
        Persist a string setting value.

        Args:
            key: Setting key to store.
            value: Value to persist.
        """
        ...

    def get_bool(self, key: str, default: bool = False) -> bool:
        """
        Retrieve a boolean setting value.

        Args:
            key: Setting key to look up.
            default: Value to return if key is not found.

        Returns:
            The setting value parsed as boolean, or default if not set.
        """
        ...

    def get_int(self, key: str, default: int = 0) -> int:
        """
        Retrieve an integer setting value.

        Args:
            key: Setting key to look up.
            default: Value to return if key is not found.

        Returns:
            The setting value parsed as integer, or default if not set.
        """
        ...

    def get_float(self, key: str, default: float = 0.0) -> float:
        """
        Retrieve a float setting value.

        Args:
            key: Setting key to look up.
            default: Value to return if key is not found.

        Returns:
            The setting value parsed as float, or default if not set.
        """
        ...

    def reset_to_defaults(self) -> None:
        """Reset all settings to their built-in default values."""
        ...


@runtime_checkable
class ProviderCircuitBreakerApi(Protocol):
    """Protocol for per-provider stuck-detection state machine."""

    def record_failure(self, provider_id: str, *, model_name: str, reason: str) -> None:
        """Record an inference failure for a provider.

        Args:
            provider_id: Provider identifier.
            model_name: Model that produced the failure.
            reason: Short snake_case description of the failure cause.
        """
        ...

    def record_success(self, provider_id: str) -> None:
        """Record a successful inference, resetting the circuit to healthy.

        Args:
            provider_id: Provider identifier.
        """
        ...

    def state(self, provider_id: str) -> str:
        """Return the current circuit state: ``"healthy"``, ``"tripped"``, or ``"probing"``.

        Args:
            provider_id: Provider identifier.

        Returns:
            Current state string.
        """
        ...

    def should_dispatch(self, provider_id: str) -> bool:
        """Return True when tasks may be dispatched to this provider.

        Args:
            provider_id: Provider identifier.

        Returns:
            True for healthy or probing states, False when tripped.
        """
        ...

    def reset(self, provider_id: str) -> None:
        """Fully reset the circuit state for a provider.

        Args:
            provider_id: Provider identifier.
        """
        ...


@runtime_checkable
class LogFileWriterApi(Protocol):
    """Protocol for writing structured benchmark log entries to disk."""

    def write_entry(self, run_id: int, entry_type: LogEntryType, content: str) -> None:
        """
        Write a structured log entry to the log file for a benchmark run.

        Args:
            run_id: ID of the benchmark run to log for.
            entry_type: Type of log entry (e.g., INFERENCE, JUDGE, ERROR).
            content: Log entry content.
        """
        ...

    def get_log_path(self, run_id: int) -> Path:
        """
        Retrieve the file path for logs of a specific benchmark run.

        Args:
            run_id: ID of the benchmark run.

        Returns:
            Path to the log file for this run.
        """
        ...

    def close(self, run_id: int) -> None:
        """
        Close the log file for a benchmark run and flush pending writes.

        Args:
            run_id: ID of the benchmark run.
        """
        ...


@runtime_checkable
class ProviderConfigRepositoryApi(Protocol):
    """Protocol for SQLite-backed provider configuration storage."""

    def count(self) -> int:
        """Return the number of stored provider rows.

        Returns:
            Row count; 0 if the table is empty.
        """
        ...

    def load_all(self) -> list[ProviderConfig]:
        """Load all provider rows from persistent storage.

        Returns:
            List of ProviderConfig instances; empty list if no rows exist.
        """
        ...

    def save(self, provider: ProviderConfig) -> None:
        """Persist a provider, inserting or replacing the existing row.

        Args:
            provider: ProviderConfig instance to persist.
        """
        ...

    def delete(self, provider_id: str) -> None:
        """Remove a provider row by its identifier.

        Args:
            provider_id: The unique provider ID to delete.
        """
        ...

    def load_embedding_config(self) -> EmbeddingConfig | None:
        """Load the singleton embedding config row.

        Returns:
            EmbeddingConfig if the row exists, None otherwise.
        """
        ...

    def save_embedding_config(self, config: EmbeddingConfig) -> None:
        """Persist the singleton embedding config row.

        Args:
            config: EmbeddingConfig instance to persist.
        """
        ...

    def replace_all(self, providers: list[ProviderConfig]) -> None:
        """Replace all stored provider rows with the given list.

        Deletes all existing rows then inserts each provider in order.

        Args:
            providers: Replacement list of ProviderConfig instances.
        """
        ...

    def set_last_test_status(self, provider_id: str, status: str, tested_at: str, message: str) -> None:
        """Persist the last health-check result for a provider.

        Args:
            provider_id: Provider to update.
            status: Health status string (e.g. "healthy" or "down").
            tested_at: ISO-8601 UTC timestamp of the test.
            message: Human-readable result message.
        """
        ...
