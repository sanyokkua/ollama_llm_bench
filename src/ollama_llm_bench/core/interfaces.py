from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, List, Optional

from ollama_llm_bench.core.models import (
    AvgSummaryTableItem, BenchmarkResult, BenchmarkResultStatus, BenchmarkRun,
    BenchmarkRunStatus, BenchmarkTask,
    InferenceResponse, ReporterStatusMsg, SummaryTableItem,
)
from ollama_llm_bench.core.ui_controllers import (
    LogWidgetControllerApi,
    NewRunWidgetControllerApi,
    PreviousRunWidgetControllerApi, ResultWidgetControllerApi,
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
    def inference(self,
                  *,
                  model_name: str,
                  user_prompt: str,
                  system_prompt: Optional[str] = None,
                  on_llm_response: Optional[Callable[[str], None]] = None,
                  on_is_stop_signal: Optional[Callable[[], bool]] = None,
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
    def retrieve_benchmark_results_for_run_with_status(self, *, run_id: int, status: BenchmarkResultStatus) -> list[
        BenchmarkResult]:
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

    def __init__(self,
                 *,
                 data_api: DataApi,
                 task_api: BenchmarkTaskApi,
                 prompt_builder_api: PromptBuilderApi,
                 llm_api: LLMApi,
                 ):
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
    def get_current_run_id(self) -> Optional[int]:
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
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        """
        Subscribe to changes in the active run identifier.

        Args:
            callback: Function to call with the new run ID (or None).
        """

    @abstractmethod
    def subscribe_to_run_ids_changed(self, callback: Callable[[list[tuple[int, str]]], None]):
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
    def subscribe_to_table_summary_data_changed(self,
                                                callback: Callable[[List[AvgSummaryTableItem]], None],
                                                ) -> None:
        """
        Subscribe to updates in the summary results table.

        Args:
            callback: Function to invoke with new summary data.
        """

    @abstractmethod
    def subscribe_to_table_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None:
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
    def emit_run_id_changed(self, value: Optional[int]) -> None:
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
    def emit_table_summary_data_changed(self, value: List[AvgSummaryTableItem]) -> None:
        """
        Broadcast updated summary table data.

        Args:
            value: New list of summary items.
        """

    @abstractmethod
    def emit_table_detailed_data_change(self, value: List[SummaryTableItem]) -> None:
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
    def get_previous_run_widget_controller_api(self) -> PreviousRunWidgetControllerApi:
        """
        Retrieve the controller for the previous run widget.

        Returns:
            Controller API for managing previous run UI.
        """

    @abstractmethod
    def get_new_run_widget_controller_api(self) -> NewRunWidgetControllerApi:
        """
        Retrieve the controller for the new run widget.

        Returns:
            Controller API for managing new run UI.
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
