from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Protocol, runtime_checkable

from ollama_llm_bench.backend.core.models import (
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
    EvalLayer,
    EvaluationResult,
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
    ReporterStatusMsg,
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


class LLMApi(ABC):
    """
    Abstract interface for interacting with LLM inference services.
    """

    @abstractmethod
    def get_models_list(self) -> list[str]:
        """
        Retrieve a list of available model names.

        Returns:
            List of model names available for inference.
        """

    @abstractmethod
    def warm_up(self, model_name: str) -> bool:
        """
        Load and initialize a model in memory to reduce inference latency.

        Args:
            model_name: Name of the model to warm up.

        Returns:
            True if warm-up succeeded, False otherwise.
        """

    @abstractmethod
    def inference(
        self,
        *,
        model_name: str,
        user_prompt: str,
        system_prompt: str | None = None,
        on_llm_response: Callable[[str], None] | None = None,
        on_is_stop_signal: Callable[[], bool] | None = None,
        is_judge_mode: bool = False,
    ) -> InferenceResponse:
        """
        Perform inference using the specified model and prompts.

        Args:
            model_name: Name of the model to use for inference.
            user_prompt: Input prompt provided by the user.
            system_prompt: Optional system-level instruction to guide model behavior.
            on_llm_response: Optional callback to stream partial responses.
            on_is_stop_signal: Optional callback that returns True if inference should be interrupted.
            is_judge_mode: If True, configures inference for automated evaluation tasks.

        Returns:
            Response object containing generated text and metadata.
        """


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


class BenchmarkTaskApi(ABC):
    """
    Abstract interface for managing benchmark task definitions.
    """

    def __init__(self, *, task_folder_path: Path):
        self._task_folder_path = task_folder_path

    @abstractmethod
    def load_tasks(self) -> list[BenchmarkTask]:
        """
        Load all benchmark tasks from the configured task directory.

        Returns:
            List of loaded benchmark tasks.
        """

    @abstractmethod
    def get_task(self, task_id: str) -> BenchmarkTask:
        """
        Retrieve a specific task by its identifier.

        Args:
            task_id: Unique ID of the task.

        Returns:
            The requested benchmark task.
        """


class PromptBuilderApi(ABC):
    """
    Abstract interface for constructing prompts used in benchmarking and judging.
    """

    def __init__(self, *, task_api: BenchmarkTaskApi):
        self._task_api = task_api

    @abstractmethod
    def build_prompt(self, task_id: str) -> str:
        """
        Construct a user-facing prompt for executing a benchmark task.

        Args:
            task_id: Identifier of the task to build a prompt for.

        Returns:
            Fully formatted prompt string.
        """

    @abstractmethod
    def build_judge_prompt(self, benchmark_result: BenchmarkResult) -> tuple[str, str]:
        """
        Construct a prompt used to evaluate (judge) a benchmark result.

        Args:
            benchmark_result: Result to be evaluated.

        Returns:
            Tuple containing (judge_prompt, expected_answer).
        """


class BenchmarkFlowApi(ABC):
    """
    Abstract interface for controlling the execution flow of benchmarks.
    """

    def __init__(
        self,
        *,
        data_api: DataApi,
        task_api: BenchmarkTaskApi,
        prompt_builder_api: PromptBuilderApi,
        llm_api: LLMApi,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._data_api = data_api
        self._task_api = task_api
        self._prompt_builder_api = prompt_builder_api
        self._llm_api = llm_api

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
    def subscribe_to_run_id_changed(self, callback: Callable[[int | None], None]) -> None:
        """
        Subscribe to changes in the active run identifier.

        Args:
            callback: Function to call with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_run_ids_changed(self, callback: Callable[[list[tuple[int, str]]], None]) -> None:
        """
        Subscribe to changes in the list of available run IDs and names.

        Args:
            callback: Function to call with updated list of (ID, name) tuples.
        """

    @abstractmethod
    def subscribe_to_models_test_changed(self, callback: Callable[[list[str]], None]) -> None:
        """
        Subscribe to changes in the list of models used for testing.

        Args:
            callback: Function to call with updated model names.
        """

    @abstractmethod
    def subscribe_to_models_judge_changed(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to changes in the model used for judging results.

        Args:
            callback: Function to call with the new judge model name.
        """

    @abstractmethod
    def subscribe_to_log_clean(self, callback: Callable[[], None]) -> None:
        """
        Subscribe to log clear events.

        Args:
            callback: Function to invoke when logs should be cleared.
        """

    @abstractmethod
    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to log append events.

        Args:
            callback: Function to invoke with new log lines.
        """

    @abstractmethod
    def subscribe_to_table_summary_data_changed(
        self,
        callback: Callable[[list[AvgSummaryTableItem]], None],
    ) -> None:
        """
        Subscribe to updates in the summary results table.

        Args:
            callback: Function to invoke with new summary data.
        """

    @abstractmethod
    def subscribe_to_table_detailed_data_change(self, callback: Callable[[list[SummaryTableItem]], None]) -> None:
        """
        Subscribe to updates in the detailed results table.

        Args:
            callback: Function to invoke with new detailed data.
        """

    @abstractmethod
    def subscribe_to_background_thread_is_running(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to background task execution status.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """

    @abstractmethod
    def subscribe_to_background_thread_progress(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """
        Subscribe to progress updates from background tasks.

        Args:
            callback: Function to invoke with progress status messages.
        """

    @abstractmethod
    def subscribe_to_global_event_msg(self, callback: Callable[[str], None]) -> None:
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
    def subscribe_to_benchmark_started(self, callback: Callable[[BenchmarkStartedEvent], None]) -> None: ...

    @abstractmethod
    def emit_benchmark_started(self, event: BenchmarkStartedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_paused(self, callback: Callable[[BenchmarkPausedEvent], None]) -> None: ...

    @abstractmethod
    def emit_benchmark_paused(self, event: BenchmarkPausedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_resumed(self, callback: Callable[[BenchmarkResumedEvent], None]) -> None: ...

    @abstractmethod
    def emit_benchmark_resumed(self, event: BenchmarkResumedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_stopped(self, callback: Callable[[BenchmarkStoppedEvent], None]) -> None: ...

    @abstractmethod
    def emit_benchmark_stopped(self, event: BenchmarkStoppedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_finished(self, callback: Callable[[BenchmarkFinishedEvent], None]) -> None: ...

    @abstractmethod
    def emit_benchmark_finished(self, event: BenchmarkFinishedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_provider_switch(self, callback: Callable[[ProviderSwitchEvent], None]) -> None: ...

    @abstractmethod
    def emit_provider_switch(self, event: ProviderSwitchEvent) -> None: ...

    @abstractmethod
    def subscribe_to_provider_health_check(self, callback: Callable[[ProviderHealthCheckEvent], None]) -> None: ...

    @abstractmethod
    def emit_provider_health_check(self, event: ProviderHealthCheckEvent) -> None: ...

    @abstractmethod
    def subscribe_to_model_switch(self, callback: Callable[[ModelSwitchEvent], None]) -> None: ...

    @abstractmethod
    def emit_model_switch(self, event: ModelSwitchEvent) -> None: ...

    @abstractmethod
    def subscribe_to_task_switch(self, callback: Callable[[TaskSwitchEvent], None]) -> None: ...

    @abstractmethod
    def emit_task_switch(self, event: TaskSwitchEvent) -> None: ...

    @abstractmethod
    def subscribe_to_task_retry(self, callback: Callable[[TaskRetryEvent], None]) -> None: ...

    @abstractmethod
    def emit_task_retry(self, event: TaskRetryEvent) -> None: ...

    @abstractmethod
    def subscribe_to_mode_switch(self, callback: Callable[[ModeSwitchEvent], None]) -> None: ...

    @abstractmethod
    def emit_mode_switch(self, event: ModeSwitchEvent) -> None: ...

    @abstractmethod
    def subscribe_to_task_completed(self, callback: Callable[[TaskCompletedEvent], None]) -> None: ...

    @abstractmethod
    def emit_task_completed(self, event: TaskCompletedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_judge_started(self, callback: Callable[[JudgeStartedEvent], None]) -> None: ...

    @abstractmethod
    def emit_judge_started(self, event: JudgeStartedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_judge_completed(self, callback: Callable[[JudgeCompletedEvent], None]) -> None: ...

    @abstractmethod
    def emit_judge_completed(self, event: JudgeCompletedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_judge_eval_started(self, callback: Callable[[JudgeEvalStartedEvent], None]) -> None: ...

    @abstractmethod
    def emit_judge_eval_started(self, event: JudgeEvalStartedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_judge_eval_retry(self, callback: Callable[[JudgeEvalRetryEvent], None]) -> None: ...

    @abstractmethod
    def emit_judge_eval_retry(self, event: JudgeEvalRetryEvent) -> None: ...

    @abstractmethod
    def subscribe_to_streaming_chunk(self, callback: Callable[[StreamingChunkEvent], None]) -> None: ...

    @abstractmethod
    def emit_streaming_chunk(self, event: StreamingChunkEvent) -> None: ...

    @abstractmethod
    def subscribe_to_inference_started(self, callback: Callable[[InferenceStartedEvent], None]) -> None: ...

    @abstractmethod
    def emit_inference_started(self, event: InferenceStartedEvent) -> None: ...

    @abstractmethod
    def subscribe_to_progress_update(self, callback: Callable[[ProgressUpdateEvent], None]) -> None: ...

    @abstractmethod
    def emit_progress_update(self, event: ProgressUpdateEvent) -> None: ...

    @abstractmethod
    def subscribe_to_judge_summary(self, callback: Callable[[JudgeSummaryEvent], None]) -> None:
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
    def subscribe_to_perf_analysis(self, callback: Callable[[PerfAnalysisEvent], None]) -> None:
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
    def subscribe_to_app_settings_changed(self, callback: Callable[[AppSettingsChangedEvent], None]) -> None:
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
        self, callback: Callable[[ProviderRegistryReloadedEvent], None]
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
    def subscribe_to_previous_runs_refreshed(self, callback: Callable[[PreviousRunsRefreshedEvent], None]) -> None:
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
    def get_llm_api(self) -> LLMApi:
        """
        Retrieve the LLM inference interface.

        Returns:
            LLMApi instance for model interaction.
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


class ITableSerializer(ABC):
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


class LLMProviderApi(Protocol):
    """Protocol for synchronous and streaming LLM inference providers."""

    @property
    def provider_id(self) -> str: ...

    @property
    def provider_type(self) -> str: ...

    def get_available_models(self) -> list[ModelDescriptor]: ...

    def inference_sync(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        reasoning_effort: str = "medium",
    ) -> InferenceResponse: ...

    def inference_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int | None = None,
        reasoning_effort: str = "medium",
    ) -> Generator[StreamChunk, None, InferenceResponse]: ...

    def supports_structured_output(self) -> bool: ...

    def supports_streaming(self) -> bool: ...

    def warm_up(self, model: str) -> bool: ...


class EmbeddingProviderApi(Protocol):
    """Protocol for providers that produce vector embeddings."""

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class ProviderRegistryApi(Protocol):
    """Protocol for the registry that constructs and exposes all LLM providers."""

    def load(self) -> None: ...

    def reload(self) -> None: ...

    def get_provider(self, provider_id: str) -> LLMProviderApi: ...

    def get_all_providers(self) -> list[LLMProviderApi]: ...

    def get_enabled_providers(self) -> list[LLMProviderApi]: ...

    def get_embedding_provider(self) -> EmbeddingProviderApi: ...

    def get_config(self) -> ProvidersConfig | None:
        """Return the currently loaded ProvidersConfig, or None if load() has not succeeded."""
        ...


class ModelNameParserApi(Protocol):
    """Parses Ollama-style model name strings into structured components."""

    def parse(self, model_name: str) -> ParsedModelName: ...


@runtime_checkable
class TaskFileLoaderApi(Protocol):
    """Protocol for loading V2 benchmark tasks from YAML files or directories."""

    def load_tasks(self, file_paths: list[Path]) -> list[BenchmarkTask]: ...

    def get_task(self, task_id: str) -> BenchmarkTask: ...

    def scan_directory(self, directory: Path) -> list[Path]: ...


@runtime_checkable
class EvaluatorApi(Protocol):
    """Protocol for evaluation layers 1-3 (rule-based, keyword, cosine)."""

    @property
    def layer(self) -> EvalLayer: ...

    def evaluate(self, task: BenchmarkTask, result: BenchmarkResult) -> EvaluationResult: ...


@runtime_checkable
class LLMJudgeEvaluatorApi(Protocol):
    """Protocol for evaluation layer 4 — LLM-based judge with provider context."""

    @property
    def layer(self) -> EvalLayer: ...

    def evaluate(
        self,
        task: BenchmarkTask,
        result: BenchmarkResult,
        *,
        judge_provider_id: str,
        judge_model: str,
    ) -> EvaluationResult: ...


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

    def build_inference_prompt(self, task: BenchmarkTask) -> tuple[str, str]: ...

    def build_judge_prompt(self, task: BenchmarkTask, result: BenchmarkResult) -> tuple[str, str]: ...


@runtime_checkable
class AppSettingsServiceApi(Protocol):
    """Protocol for reading and writing typed application settings from persistent storage."""

    def get(self, key: str, default: str | None = None) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def get_bool(self, key: str, default: bool = False) -> bool: ...

    def get_int(self, key: str, default: int = 0) -> int: ...

    def get_float(self, key: str, default: float = 0.0) -> float: ...

    def reset_to_defaults(self) -> None:
        """Reset all settings to their built-in default values."""
        ...


@runtime_checkable
class LogFileWriterApi(Protocol):
    """Protocol for writing structured benchmark log entries to disk."""

    def write_entry(self, run_id: int, entry_type: LogEntryType, content: str) -> None: ...

    def get_log_path(self, run_id: int) -> Path: ...

    def close(self, run_id: int) -> None: ...
