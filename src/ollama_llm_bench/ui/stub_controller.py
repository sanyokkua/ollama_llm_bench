from typing import Callable, Optional

from ollama_llm_bench.core.interfaces import BenchmarkApplicationControllerApi
from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem


class StubBenchmarkApplicationControllerApi(BenchmarkApplicationControllerApi):
    def __init__(self) -> None:
        self._current_run_id = 0
        self._current_judge_model = ''
        self._current_test_models = []

    def get_models_list(self) -> list[str]:
        print('Getting models list')
        return ['model1', 'model2', 'model3']

    def set_current_judge_model(self, model_name: str) -> None:
        print(f'Setting current judge model to: {model_name}')
        self._current_judge_model = model_name

    def set_current_test_models(self, model_names: list[str]) -> None:
        print(f'Setting current test models to: {model_names}')
        self._current_test_models = model_names

    def get_runs_list(self) -> list[tuple[int, str]]:
        print('Getting runs list')
        return [(1, 'run1'), (2, 'run2'), (3, 'run3')]

    def get_current_run_id(self) -> int:
        print('Getting current run ID')
        return self._current_run_id

    def set_current_run_id(self, run_id: Optional[int] = None) -> None:
        print(f'Setting current run ID to: {run_id}')
        self._current_run_id = run_id

    def delete_run(self) -> None:
        print(f'Deleting run: {self._current_run_id}')

    def start_benchmark(self) -> int:
        print(f'Starting benchmark with judge model: {self._current_judge_model} and test models: {self._current_test_models}')
        return self._current_run_id

    def stop_benchmark(self) -> None:
        print('Benchmark stopped')

    def get_summary_data(self) -> list[AvgSummaryTableItem]:
        print('Getting summary data')
        return []

    def get_detailed_data(self) -> list[SummaryTableItem]:
        print('Getting detailed data')
        return []

    def generate_summary_csv_report(self) -> None:
        print('Generating summary CSV report')

    def generate_summary_markdown_report(self) -> None:
        print('Generating summary Markdown report')

    def generate_detailed_csv_report(self) -> None:
        print('Generating detailed CSV report')

    def generate_detailed_markdown_report(self) -> None:
        print('Generating detailed Markdown report')

    def subscribe_to_benchmark_run_id_changed_events(self, callback: Callable[[Optional[int]], None]) -> None:
        print('Subscribed to benchmark run ID changed events')

    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None:
        print('Subscribed to benchmark status events')

    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None:
        print('Subscribed to benchmark output events')
