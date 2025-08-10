import logging
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from ollama_llm_bench.core.interfaces import (
    BenchmarkApplicationControllerApi,
    BenchmarkFlowApi, BenchmarkTaskApi, DataApi,
    LLMApi, ResultApi,
)
from ollama_llm_bench.core.models import (
    AvgSummaryTableItem,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunStatus,
    ReporterStatusMsg,
    SummaryTableItem,
)
from ollama_llm_bench.qt_classes.meta_class import MetaQObjectABC

logger = logging.getLogger(__name__)


class QtBenchmarkControllerAPI(QObject, BenchmarkApplicationControllerApi, metaclass=MetaQObjectABC):
    """Controller that manages the benchmark application state and coordinates between UI and backend"""

    benchmark_run_id_changed_events = pyqtSignal(int)
    benchmark_status_events = pyqtSignal(bool)
    benchmark_output_events = pyqtSignal(str)
    benchmark_progress_events = pyqtSignal(ReporterStatusMsg)

    def __init__(
        self,
        *,
        data_api: DataApi,
        llm_api: LLMApi,
        task_api: BenchmarkTaskApi,
        benchmark_flow_api: BenchmarkFlowApi,
        result_api: ResultApi,
    ) -> None:
        super().__init__()
        self._data_api = data_api
        self._llm_api = llm_api
        self._task_api = task_api
        self._benchmark_flow_api = benchmark_flow_api
        self._result_api = result_api

        # Initialize state
        self._current_run_id: Optional[int] = None
        self._current_judge_model: Optional[str] = None
        self._current_test_models: Optional[list[str]] = None

        # Connect to flow API signals
        self._connect_flow_api_signals()

        logger.info("QtBenchmarkControllerAPI initialized")

    def _connect_flow_api_signals(self) -> None:
        """Connect to the benchmark flow API signals"""
        logger.debug("Connecting to benchmark flow API signals")
        self._benchmark_flow_api.subscribe_to_benchmark_status_events(self._on_benchmark_status_changed)
        self._benchmark_flow_api.subscribe_to_benchmark_output_events(self._on_benchmark_output)
        self._benchmark_flow_api.subscribe_to_benchmark_progress_events(self._on_benchmark_progress)

    def _on_benchmark_status_changed(self, is_running: bool) -> None:
        """Handle benchmark status changes from the flow API"""
        status = "running" if is_running else "stopped"
        logger.info(f"Benchmark execution status changed to: {status}")
        self.benchmark_status_events.emit(is_running)

    def _on_benchmark_output(self, message: str) -> None:
        """Handle log/output messages from the flow API"""
        logger.debug(f"Benchmark output: {message}")
        self.benchmark_output_events.emit(message)

    def _on_benchmark_progress(self, status_msg: ReporterStatusMsg) -> None:
        """Handle progress updates from the flow API"""
        logger.debug(
            f"Progress update - {status_msg.completed_amount_of_tasks}/{status_msg.total_amount_of_tasks} tasks completed. "
            f"Current model: {status_msg.current_model_name}, Task: {status_msg.current_task_id}",
        )
        self.benchmark_progress_events.emit(status_msg)

    def _set_current_run_id(self, run_id: Optional[int]) -> None:
        """Internal method to update current run ID with proper signaling"""
        if self._current_run_id == run_id:
            return

        previous_run_id = self._current_run_id
        self._current_run_id = run_id

        logger.info(
            f"Current run ID changed from {previous_run_id} to {run_id}"
            if run_id is not None else f"Current run ID cleared (was {previous_run_id})",
        )
        self.benchmark_run_id_changed_events.emit(run_id)

    def get_models_list(self) -> list[str]:
        """Get available LLM models from the API"""
        try:
            models = self._llm_api.get_models_list()
            logger.info(f"Retrieved {len(models)} models from LLM API")
            return models
        except Exception as e:
            logger.error(f"Failed to retrieve models list: {str(e)}")
            raise

    def set_current_judge_model(self, model_name: str) -> None:
        """Set the model to use for judging responses"""
        if not model_name and not self._current_run_id:
            logger.warning("Attempted to set empty judge model name")
            raise ValueError("Model name cannot be empty")

        if model_name not in self.get_models_list() and not self._current_run_id:
            logger.warning(f"Attempted to set non-existent judge model: {model_name}")
            raise ValueError(f"Model '{model_name}' is not available")

        self._current_judge_model = model_name
        logger.info(f"Set current judge model to: {model_name}")

    def set_current_test_models(self, model_names: list[str]) -> None:
        """Set the models to test in the benchmark"""
        if not model_names and not self._current_run_id:
            logger.warning("Attempted to set empty test models list")
            raise ValueError("At least one model must be specified for testing")

        available_models = self.get_models_list()
        invalid_models = [m for m in model_names if m not in available_models]

        if len(invalid_models) > 0 and not self._current_run_id:
            logger.warning(f"Attempted to set invalid test models: {invalid_models}")
            err_models = ', '.join(invalid_models)
            raise ValueError(f"Invalid models: {err_models}")

        self._current_test_models = model_names
        logger.info(f"Set current test models: {', '.join(model_names)}")

    def get_runs_list(self) -> list[tuple[int, str]]:
        """Get list of all benchmark runs"""
        try:
            runs = self._data_api.retrieve_benchmark_runs()
            logger.info(f"Retrieved {len(runs)} benchmark runs")

            # Sort by timestamp (newest first)
            runs.sort(key=lambda r: r.timestamp, reverse=True)
            return [(run.run_id, run.timestamp) for run in runs]
        except Exception as e:
            logger.error(f"Failed to retrieve benchmark runs: {str(e)}")
            raise

    def get_current_run_id(self) -> int:
        """Get the ID of the currently selected run"""
        if self._current_run_id is None:
            logger.warning("Attempted to get current run ID when none is selected")
            raise RuntimeError("No benchmark run is currently selected")
        return self._current_run_id

    def set_current_run_id(self, run_id: Optional[int] = None) -> None:
        """Set the currently selected run ID"""
        if run_id is not None:
            try:
                # Verify the run exists
                self._data_api.retrieve_benchmark_run(run_id)
            except Exception as e:
                logger.error(f"Attempted to set invalid run ID {run_id}: {str(e)}")
                raise ValueError(f"Invalid run ID: {run_id}") from e

        self._set_current_run_id(run_id)
        logger.info(f"Set current run ID to {run_id}" if run_id is not None else "Cleared current run ID")

    def delete_run(self) -> None:
        """Delete the currently selected benchmark run"""
        if self._current_run_id is None:
            logger.warning("Attempted to delete run when none is selected")
            return

        try:
            self._data_api.delete_benchmark_run(self._current_run_id)
            logger.info(f"Deleted benchmark run with ID: {self._current_run_id}")

            # Clear current run ID if it was the one deleted
            if self._current_run_id is not None:
                self._set_current_run_id(None)

            runs = self.get_runs_list()
            if len(runs)>0 and runs[0]:
                latest_run = runs[0]
                self._set_current_run_id(latest_run[0])
        except Exception as e:
            logger.error(f"Failed to delete run {self._current_run_id}: {str(e)}")
            raise

    def start_benchmark(self) -> int:
        """Start a new benchmark execution and return the new run ID"""
        # Validate prerequisites
        if not self._current_judge_model:
            logger.error("Cannot start benchmark: judge model not set")
            raise RuntimeError("Judge model must be set before starting a benchmark")

        if not self._current_test_models:
            logger.error("Cannot start benchmark: no test models selected")
            raise RuntimeError("At least one test model must be selected")

        if self._benchmark_flow_api.is_running():
            logger.warning("Attempted to start benchmark while one is already running")
            raise RuntimeError("A benchmark is already running")
        run_id = None
        try:
            # Create new benchmark run
            timestamp = datetime.now().isoformat()
            run = BenchmarkRun(
                run_id=0,  # Will be set by data API
                timestamp=timestamp,
                judge_model=self._current_judge_model,
                status=BenchmarkRunStatus.NOT_COMPLETED,
            )
            run_id = self._data_api.create_benchmark_run(run)
            logger.info(f"Created new benchmark run with ID: {run_id}")

            # Initialize benchmark results for all model/task combinations
            self._initialize_benchmark_results(run_id)

            # Set as current run and start execution
            self._set_current_run_id(run_id)
            self._benchmark_flow_api.start_execution(run_id)

            logger.info(f"Started benchmark execution for run ID: {run_id}")
            return run_id

        except Exception as e:
            logger.exception(f"Failed to start benchmark: {str(e)}")
            # Clean up partially created run
            try:
                if run_id:
                    self._data_api.delete_benchmark_run(run_id)
            except:
                pass
            raise

    def _initialize_benchmark_results(self, run_id: int) -> None:
        """Create benchmark results for all model/task combinations"""

        # Get all tasks (assuming you have access to these APIs elsewhere)
        tasks = self._task_api.load_tasks()

        logger.info(f"Initializing {len(tasks) * len(self._current_test_models)} benchmark results for run ID {run_id}")

        results = []
        for model_name in self._current_test_models:
            for task in tasks:
                result = BenchmarkResult(
                    result_id=0,  # Will be set by data API
                    run_id=run_id,
                    task_id=task.task_id,
                    model_name=model_name,
                )
                results.append(result)

        # Batch create all results for efficiency
        self._data_api.create_benchmark_results(results)
        logger.debug(f"Initialized {len(results)} benchmark results")

    def stop_benchmark(self) -> None:
        """Stop the currently running benchmark"""
        if not self._benchmark_flow_api.is_running():
            logger.warning("Attempted to stop benchmark when none is running")
            raise RuntimeError("No benchmark is currently running")

        try:
            self._benchmark_flow_api.stop_execution()
            logger.info("Requested benchmark execution stop")
        except Exception as e:
            logger.error(f"Failed to stop benchmark: {str(e)}")
            raise

    def get_summary_data(self) -> list[AvgSummaryTableItem]:
        """Get summary data for the current run"""
        if self._current_run_id is None:
            logger.warning("Attempted to get summary data when no run is selected")
            return []

        try:
            summary = self._result_api.retrieve_avg_benchmark_results_for_run(self._current_run_id)
            logger.info(
                f"Retrieved summary data for run ID {self._current_run_id} "
                f"with {len(summary)} model summaries",
            )
            return summary
        except Exception as e:
            logger.error(f"Failed to retrieve summary data for run {self._current_run_id}: {str(e)}")
            raise

    def get_detailed_data(self) -> list[SummaryTableItem]:
        """Get detailed data for the current run"""
        if self._current_run_id is None:
            logger.warning("Attempted to get detailed data when no run is selected")
            return []

        try:
            detailed = self._result_api.retrieve_detailed_benchmark_results_for_run(self._current_run_id)
            logger.info(
                f"Retrieved detailed data for run ID {self._current_run_id} "
                f"with {len(detailed)} task results",
            )
            return detailed
        except Exception as e:
            logger.error(f"Failed to retrieve detailed data for run {self._current_run_id}: {str(e)}")
            raise

    def generate_summary_csv_report(self) -> None:
        """Generate CSV summary report for the current run"""
        if self._current_run_id is None:
            logger.warning("Attempted to generate summary CSV report when no run is selected")
            raise RuntimeError("No benchmark run is currently selected")

        try:
            # In a real implementation, this would generate the actual report
            logger.info(f"Generating summary CSV report for run ID {self._current_run_id}")
            # Actual report generation would happen here
        except Exception as e:
            logger.error(f"Failed to generate summary CSV report for run {self._current_run_id}: {str(e)}")
            raise

    def generate_summary_markdown_report(self) -> None:
        """Generate Markdown summary report for the current run"""
        if self._current_run_id is None:
            logger.warning("Attempted to generate summary Markdown report when no run is selected")
            raise RuntimeError("No benchmark run is currently selected")

        try:
            logger.info(f"Generating summary Markdown report for run ID {self._current_run_id}")
            # Actual report generation would happen here
        except Exception as e:
            logger.error(f"Failed to generate summary Markdown report for run {self._current_run_id}: {str(e)}")
            raise

    def generate_detailed_csv_report(self) -> None:
        """Generate CSV detailed report for the current run"""
        if self._current_run_id is None:
            logger.warning("Attempted to generate detailed CSV report when no run is selected")
            raise RuntimeError("No benchmark run is currently selected")

        try:
            logger.info(f"Generating detailed CSV report for run ID {self._current_run_id}")
            # Actual report generation would happen here
        except Exception as e:
            logger.error(f"Failed to generate detailed CSV report for run {self._current_run_id}: {str(e)}")
            raise

    def generate_detailed_markdown_report(self) -> None:
        """Generate Markdown detailed report for the current run"""
        if self._current_run_id is None:
            logger.warning("Attempted to generate detailed Markdown report when no run is selected")
            raise RuntimeError("No benchmark run is currently selected")

        try:
            logger.info(f"Generating detailed Markdown report for run ID {self._current_run_id}")
            # Actual report generation would happen here
        except Exception as e:
            logger.error(f"Failed to generate detailed Markdown report for run {self._current_run_id}: {str(e)}")
            raise

    def subscribe_to_benchmark_run_id_changed_events(self, callback: Callable[[Optional[int]], None]) -> None:
        """Subscribe to run ID changes"""
        self.benchmark_run_id_changed_events.connect(callback)
        # Notify of current state
        # callback(self._current_run_id)

    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None:
        """Subscribe to execution status changes"""
        self.benchmark_status_events.connect(callback)
        # Notify of current state
        callback(self._benchmark_flow_api.is_running())

    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None:
        """Subscribe to log/output messages"""
        self.benchmark_output_events.connect(callback)

    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """Subscribe to progress updates"""
        self.benchmark_progress_events.connect(callback)
