from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, List, Optional

from ollama_llm_bench.core.controllers import (
    LogWidgetControllerApi,
    NewRunWidgetControllerApi,
    PreviousRunWidgetControllerApi, ResultWidgetControllerApi,
)
from ollama_llm_bench.core.models import (
    AvgSummaryTableItem, BenchmarkResult, BenchmarkResultStatus, BenchmarkRun,
    BenchmarkRunStatus, BenchmarkTask,
    InferenceResponse, ReporterStatusMsg, SummaryTableItem,
)


class LLMApi(ABC):
    @abstractmethod
    def get_models_list(self) -> list[str]: ...

    @abstractmethod
    def warm_up(self, model_name: str) -> bool: ...

    @abstractmethod
    def inference(self,
                  *,
                  model_name: str,
                  user_prompt: str,
                  system_prompt: Optional[str] = None,
                  on_llm_response: Optional[Callable[[str], None]] = None,
                  on_is_stop_signal: Optional[Callable[[], bool]] = None,
                  is_judge_mode: bool = False,
                  ) -> InferenceResponse: ...


class DataApi(ABC):

    @abstractmethod
    def create_benchmark_run(self, benchmark_run: BenchmarkRun) -> int: ...

    @abstractmethod
    def retrieve_benchmark_run(self, run_id: int) -> BenchmarkRun: ...

    @abstractmethod
    def retrieve_benchmark_runs(self) -> list[BenchmarkRun]: ...

    @abstractmethod
    def retrieve_benchmark_runs_with_status(self, status: BenchmarkRunStatus) -> list[BenchmarkRun]: ...

    @abstractmethod
    def update_benchmark_run(self, benchmark_run: BenchmarkRun) -> None: ...

    @abstractmethod
    def delete_benchmark_run(self, run_id: int) -> None: ...

    @abstractmethod
    def create_benchmark_result(self, benchmark_result: BenchmarkResult) -> int: ...

    @abstractmethod
    def create_benchmark_results(self, benchmark_result: list[BenchmarkResult]) -> None: ...

    @abstractmethod
    def retrieve_benchmark_result(self, result_id: int) -> BenchmarkResult: ...

    @abstractmethod
    def retrieve_benchmark_results_for_run(self, run_id: int) -> list[BenchmarkResult]: ...

    @abstractmethod
    def retrieve_benchmark_results_for_run_with_status(self, *, run_id: int, status: BenchmarkResultStatus) -> list[
        BenchmarkResult]: ...

    @abstractmethod
    def update_benchmark_result(self, benchmark_result: BenchmarkResult) -> None: ...

    @abstractmethod
    def delete_benchmark_result(self, result_id: int) -> None: ...


class ResultApi(ABC):
    def __init__(self, *, data_api: DataApi):
        self._data_api = data_api

    @abstractmethod
    def retrieve_avg_benchmark_results_for_run(self, run_id: int) -> list[AvgSummaryTableItem]: ...

    @abstractmethod
    def retrieve_detailed_benchmark_results_for_run(self, run_id: int) -> list[SummaryTableItem]: ...


class BenchmarkTaskApi(ABC):
    def __init__(self, *, task_folder_path: Path):
        self._task_folder_path = task_folder_path

    @abstractmethod
    def load_tasks(self) -> list[BenchmarkTask]: ...

    @abstractmethod
    def get_task(self, task_id: str) -> BenchmarkTask: ...


class PromptBuilderApi(ABC):
    def __init__(self, *, task_api: BenchmarkTaskApi):
        self._task_api = task_api

    @abstractmethod
    def build_prompt(self, task_id: str) -> str: ...

    @abstractmethod
    def build_judge_prompt(self, benchmark_result: BenchmarkResult) -> tuple[str, str]: ...


class BenchmarkFlowApi(ABC):
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
    def start_execution(self, run_id: int) -> None: ...

    @abstractmethod
    def stop_execution(self) -> None: ...

    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def get_current_run_id(self) -> Optional[int]: ...

    @abstractmethod
    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None: ...


class EventBus(ABC):
    @abstractmethod
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None: ...

    @abstractmethod
    def subscribe_to_run_ids_changed(self, callback: Callable[[list[tuple[int, str]]], None]): ...

    @abstractmethod
    def subscribe_to_models_test_changed(self, callback: Callable[[list[str]], None]) -> None: ...

    @abstractmethod
    def subscribe_to_models_judge_changed(self, callback: Callable[[str], None]) -> None: ...

    @abstractmethod
    def subscribe_to_log_clean(self, callback: Callable[[], None]) -> None: ...

    @abstractmethod
    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None: ...

    @abstractmethod
    def subscribe_to_table_summary_data_changed(self,
                                                callback: Callable[[List[AvgSummaryTableItem]], None],
                                                ) -> None: ...

    @abstractmethod
    def subscribe_to_table_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None: ...

    @abstractmethod
    def subscribe_to_background_thread_is_running(self, callback: Callable[[bool], None]) -> None: ...

    @abstractmethod
    def subscribe_to_background_thread_progress(self, callback: Callable[[ReporterStatusMsg], None]) -> None: ...

    @abstractmethod
    def subscribe_to_global_event_msg(self, callback: Callable[[str], None]) -> None: ...

    @abstractmethod
    def emit_run_id_changed(self, value: Optional[int]) -> None: ...

    @abstractmethod
    def emit_run_ids_changed(self, value: list[tuple[int, str]]) -> None: ...

    @abstractmethod
    def emit_models_test_changed(self, value: list[str]) -> None: ...

    @abstractmethod
    def emit_models_judge_changed(self, value: str) -> None: ...

    @abstractmethod
    def emit_log_clean(self) -> None: ...

    @abstractmethod
    def emit_log_append(self, value: str) -> None: ...

    @abstractmethod
    def emit_table_summary_data_changed(self, value: List[AvgSummaryTableItem]) -> None: ...

    @abstractmethod
    def emit_table_detailed_data_change(self, value: List[SummaryTableItem]) -> None: ...

    @abstractmethod
    def emit_background_thread_is_running(self, value: bool) -> None: ...

    @abstractmethod
    def emit_background_thread_progress(self, value: ReporterStatusMsg) -> None: ...

    @abstractmethod
    def emit_global_event_msg(self, value: str) -> None: ...


class AppContext(ABC):
    @abstractmethod
    def get_event_bus(self) -> EventBus: ...

    @abstractmethod
    def get_previous_run_widget_controller_api(self) -> PreviousRunWidgetControllerApi: ...

    @abstractmethod
    def get_new_run_widget_controller_api(self) -> NewRunWidgetControllerApi: ...

    @abstractmethod
    def get_log_widget_controller_api(self) -> LogWidgetControllerApi: ...

    @abstractmethod
    def get_result_widget_controller_api(self) -> ResultWidgetControllerApi: ...

    @abstractmethod
    def get_data_api(self) -> DataApi: ...

    @abstractmethod
    def get_llm_api(self) -> LLMApi: ...

    @abstractmethod
    def get_result_api(self) -> ResultApi: ...

    @abstractmethod
    def send_initialization_events(self) -> None: ...


class ITableSerializer(ABC):
    @abstractmethod
    def save_summary_as_csv(self, items: list[AvgSummaryTableItem]) -> None: ...

    @abstractmethod
    def save_summary_as_md(self, items: list[AvgSummaryTableItem]) -> None: ...

    @abstractmethod
    def save_details_as_csv(self, items: list[SummaryTableItem]) -> None: ...

    @abstractmethod
    def save_details_as_md(self, items: list[SummaryTableItem]) -> None: ...
