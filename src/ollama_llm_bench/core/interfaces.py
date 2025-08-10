from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

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


class BenchmarkApplicationControllerApi(ABC):
    # LLM Model Ops
    @abstractmethod
    def get_models_list(self) -> list[str]: ...

    @abstractmethod
    def set_current_judge_model(self, model_name: str) -> None: ...

    @abstractmethod
    def set_current_test_models(self, model_names: list[str]) -> None: ...

    # Benchmark Run Ops
    @abstractmethod
    def get_runs_list(self) -> list[tuple[int, str]]: ...

    @abstractmethod
    def get_current_run_id(self) -> int: ...

    @abstractmethod
    def set_current_run_id(self, run_id: Optional[int] = None) -> None: ...

    @abstractmethod
    def delete_run(self) -> None: ...

    # Benchmark Process Ops
    @abstractmethod
    def start_benchmark(self) -> int: ...

    @abstractmethod
    def stop_benchmark(self) -> None: ...

    # Benchmark Result Ops

    @abstractmethod
    def get_summary_data(self) -> list[AvgSummaryTableItem]: ...

    @abstractmethod
    def get_detailed_data(self) -> list[SummaryTableItem]: ...

    @abstractmethod
    def generate_summary_csv_report(self) -> None: ...

    @abstractmethod
    def generate_summary_markdown_report(self) -> None: ...

    @abstractmethod
    def generate_detailed_csv_report(self) -> None: ...

    @abstractmethod
    def generate_detailed_markdown_report(self) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_run_id_changed_events(self, callback: Callable[[Optional[int]], None]) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None: ...

    @abstractmethod
    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None: ...
