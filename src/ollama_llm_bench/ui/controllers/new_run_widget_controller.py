import logging
from datetime import datetime
from typing import Callable, List, override

from ollama_llm_bench.core.interfaces import BenchmarkFlowApi, BenchmarkTaskApi, DataApi, EventBus, LLMApi
from ollama_llm_bench.core.models import BenchmarkResult, BenchmarkRun, BenchmarkRunStatus, NewRunWidgetStartEvent
from ollama_llm_bench.core.ui_controllers import NewRunWidgetControllerApi

logger = logging.getLogger(__name__)


class NewRunWidgetController(NewRunWidgetControllerApi):
    """
    Controller implementation for managing the 'New Run' widget.
    Handles user interactions for starting new benchmark runs and model selection.
    """

    def __init__(self, *,
                 data_api: DataApi,
                 llm_api: LLMApi,
                 task_api: BenchmarkTaskApi,
                 benchmark_flow_api: BenchmarkFlowApi,
                 event_bus: EventBus,
                 ):
        """
        Initialize the new run widget controller.

        Args:
            data_api: Interface for persisting benchmark runs and results.
            llm_api: Interface for retrieving available LLM models.
            task_api: Interface for loading benchmark tasks.
            benchmark_flow_api: Interface for controlling benchmark execution.
            event_bus: Event bus for publishing UI and system events.
        """
        self.data_api = data_api
        self.llm_api = llm_api
        self.task_api = task_api
        self.benchmark_flow_api = benchmark_flow_api
        self.event_bus = event_bus

    def _get_available_models(self) -> list[str]:
        """
        Retrieve the list of models available from the LLM backend.

        Returns:
            List of available model names, or empty list if retrieval fails.
        """
        try:
            models = self.llm_api.get_models_list()
            logger.debug(f"Found {len(models)} models")
        except Exception as e:
            logger.warning(f"Failed to fetch models: {e}")
            models = set()
        return models

    @override
    def handle_refresh_click(self, _) -> None:
        """
        Handle user request to refresh the list of available models.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("Refresh button is clicked")
        models = self._get_available_models()
        self.event_bus.emit_models_test_changed(list(models))

    @override
    def handle_start_click(self, event: NewRunWidgetStartEvent) -> None:
        """
        Handle user request to start a new benchmark run.

        Args:
            event: Event containing judge model and test models to benchmark.
        """
        logger.debug("Start button is clicked")
        if self.benchmark_flow_api.is_running():
            logger.debug(f"Benchmark flow is already running")
            self.event_bus.emit_global_event_msg("Benchmark flow is already running")
            return

        selected_models = [event.judge_model]
        selected_models.extend(event.models)
        available_models = self._get_available_models()
        for model in selected_models:
            if model not in available_models:
                logger.debug(f"Benchmark model {model} is not available")
                self.event_bus.emit_global_event_msg(f"Benchmark model {model} is not available")
                return
        if len(event.models) == 0:
            logger.debug(f"No models selected")
            self.event_bus.emit_global_event_msg("No models selected")
            return

        timestamp = datetime.now().isoformat()
        run = BenchmarkRun(
            run_id=0,  # Will be set by data API
            timestamp=timestamp,
            judge_model=event.judge_model,
            status=BenchmarkRunStatus.NOT_COMPLETED,
        )
        try:
            run_id = self.data_api.create_benchmark_run(run)
            logger.info(f"Created new benchmark run with ID: {run_id}")
        except Exception as e:
            logger.warning(f"Failed to create new benchmark run: {e}")
            self.event_bus.emit_global_event_msg(f"Failed to create new benchmark run")
            return

        # Initialize benchmark results for all model/task combinations
        tasks = self.task_api.load_tasks()
        results = []
        for model_name in event.models:
            for task in tasks:
                result = BenchmarkResult(
                    result_id=0,  # Will be set by data API
                    run_id=run_id,
                    task_id=task.task_id,
                    model_name=model_name,
                )
                results.append(result)

        try:
            self.data_api.create_benchmark_results(results)
            logger.debug(f"Initialized {len(results)} benchmark results")
        except Exception as e:
            logger.warning(f"Failed to initialize benchmark results: {e}")
            self.event_bus.emit_global_event_msg(f"Failed to initialize benchmark results")
            return

        self.event_bus.emit_run_id_changed(run_id)
        self.event_bus.emit_log_clean()
        self.benchmark_flow_api.start_execution(run_id)

    @override
    def handle_stop_click(self, _) -> None:
        """
        Handle user request to stop the currently running benchmark.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("Stop button is clicked")
        if self.benchmark_flow_api.is_running():
            logger.debug(f"Benchmark flow is running, will stop execution")
            self.benchmark_flow_api.stop_execution()
        else:
            logger.debug(f"Benchmark flow is stopped")

    @override
    def subscribe_to_models_change(self, callback: Callable[[List[str]], None]) -> None:
        """
        Subscribe to changes in the list of available test models.

        Args:
            callback: Function to invoke with updated model list.
        """
        logger.debug("Subscribing to models change")
        self.event_bus.subscribe_to_models_test_changed(callback)

    @override
    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to changes in benchmark execution status.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """
        logger.debug("Subscribing to benchmark status change")
        self.event_bus.subscribe_to_background_thread_is_running(callback)
