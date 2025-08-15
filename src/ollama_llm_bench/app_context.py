import logging
from pathlib import Path
from typing import override

import ollama
from PyQt6.QtCore import QMutex, QMutexLocker, QThreadPool

from ollama_llm_bench.core.controllers import (
    LogWidgetControllerApi,
    NewRunWidgetControllerApi, PreviousRunWidgetControllerApi, ResultWidgetControllerApi,
)
from ollama_llm_bench.core.interfaces import (
    AppContext, BenchmarkFlowApi,
    BenchmarkTaskApi, DataApi, EventBus, ITableSerializer, LLMApi, PromptBuilderApi, ResultApi,
)
from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem
from ollama_llm_bench.qt_classes.qt_benchmark_flow import QtBenchmarkFlowApi
from ollama_llm_bench.qt_classes.qt_event_bus import QtEventBus
from ollama_llm_bench.services.app_result_api import AppResultApi
from ollama_llm_bench.services.ollama_llm_api import OllamaApi
from ollama_llm_bench.services.simple_prompt_builder_api import SimplePromptBuilderApi
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.services.table_serializer import TableSerializer
from ollama_llm_bench.services.yaml_benchmark_task_api import YamlBenchmarkTaskApi
from ollama_llm_bench.ui.controllers.log_widget_controller import LogWidgetController
from ollama_llm_bench.ui.controllers.new_run_widget_controller import NewRunWidgetController
from ollama_llm_bench.ui.controllers.previous_run_widget_controller import PreviousRunWidgetController
from ollama_llm_bench.ui.controllers.result_widget_controller import ResultWidgetController

DATA_SET_PATH = "dataset"
DB_FILE_NAME = "db.sqlite"

logger = logging.getLogger(__name__)


class ApplicationContext(AppContext):
    """Immutable application context container"""

    __slots__ = (
        '_ollama_llm_api',
        '_task_api',
        '_prompt_builder_api',
        '_data_api',
        '_result_api',
        '_benchmark_flow_api',
        '_event_bus',
        '_previous_run_widget_controller_api',
        '_new_run_widget_controller_api',
        '_log_widget_controller_api',
        '_result_widget_controller_api',
        '_table_serializer',
    )

    def __init__(self, *,
                 ollama_llm_api: LLMApi,
                 task_api: BenchmarkTaskApi,
                 prompt_builder_api: PromptBuilderApi,
                 data_api: DataApi,
                 result_api: ResultApi,
                 benchmark_flow_api: BenchmarkFlowApi,
                 event_bus: EventBus,
                 previous_run_widget_controller_api: PreviousRunWidgetControllerApi,
                 new_run_widget_controller_api: NewRunWidgetControllerApi,
                 log_widget_controller_api: LogWidgetControllerApi,
                 result_widget_controller_api: ResultWidgetControllerApi,
                 table_serializer: ITableSerializer,
                 ):
        self._ollama_llm_api = ollama_llm_api
        self._task_api = task_api
        self._prompt_builder_api = prompt_builder_api
        self._data_api = data_api
        self._result_api = result_api
        self._benchmark_flow_api = benchmark_flow_api
        self._event_bus = event_bus
        self._previous_run_widget_controller_api = previous_run_widget_controller_api
        self._new_run_widget_controller_api = new_run_widget_controller_api
        self._log_widget_controller_api = log_widget_controller_api
        self._result_widget_controller_api = result_widget_controller_api
        self._table_serializer = table_serializer

    @override
    def get_event_bus(self) -> EventBus:
        return self._event_bus

    @override
    def get_previous_run_widget_controller_api(self) -> PreviousRunWidgetControllerApi:
        return self._previous_run_widget_controller_api

    @override
    def get_new_run_widget_controller_api(self) -> NewRunWidgetControllerApi:
        return self._new_run_widget_controller_api

    @override
    def get_log_widget_controller_api(self) -> LogWidgetControllerApi:
        return self._log_widget_controller_api

    @override
    def get_result_widget_controller_api(self) -> ResultWidgetControllerApi:
        return self._result_widget_controller_api

    @override
    def get_data_api(self) -> DataApi:
        return self._data_api

    @override
    def get_llm_api(self) -> LLMApi:
        return self._ollama_llm_api

    @override
    def get_result_api(self) -> ResultApi:
        return self._result_api

    @override
    def send_initialization_events(self) -> None:
        logger.debug("send_initial_state")
        data_api = self.get_data_api()
        llm_api = self.get_llm_api()
        event_bus = self.get_event_bus()

        try:
            runs = data_api.retrieve_benchmark_runs()
            if runs and len(runs) > 0:
                latest_run_id = runs[-1].run_id
                runs_list = [(r.run_id, r.timestamp) for r in runs]

                logger.debug("received runs {}".format(runs))
                summary = self._get_summary_data(latest_run_id)
                detailed = self._get_detailed_data(latest_run_id)
                event_bus.emit_run_id_changed(latest_run_id)
                event_bus.emit_run_ids_changed(runs_list)
                event_bus.emit_table_summary_data_changed(summary)
                event_bus.emit_table_detailed_data_change(detailed)
            else:
                logger.debug("no runs found")
                event_bus.emit_run_id_changed(None)
                event_bus.emit_run_ids_changed([])
                event_bus.emit_table_summary_data_changed([])
                event_bus.emit_table_detailed_data_change([])
        except Exception as e:
            logger.warning("exception {}".format(e))
            event_bus.emit_run_id_changed(None)
            event_bus.emit_run_ids_changed([])
            event_bus.emit_table_summary_data_changed([])
            event_bus.emit_table_detailed_data_change([])

        try:
            models = llm_api.get_models_list()
            event_bus.emit_models_test_changed(models)
            if models and len(models) > 0:
                event_bus.emit_models_judge_changed(models[0])
            else:
                event_bus.emit_models_judge_changed('')
        except Exception as e:
            logger.warning("exception {}".format(e))
            event_bus.emit_models_test_changed([])
            event_bus.emit_models_judge_changed('')

    def _get_summary_data(self, run_id: int) -> list[AvgSummaryTableItem]:
        try:
            summary = self.get_result_api().retrieve_avg_benchmark_results_for_run(run_id)
            return summary
        except Exception as e:
            logger.error(f"Failed to retrieve summary data for run {run_id}: {str(e)}")
            return []

    def _get_detailed_data(self, run_id: int) -> list[SummaryTableItem]:
        try:
            detailed = self.get_result_api().retrieve_detailed_benchmark_results_for_run(run_id)
            return detailed
        except Exception as e:
            logger.error(f"Failed to retrieve detailed data for run {run_id}: {str(e)}")
            return []


class ContextProvider:
    """PyQt6-safe singleton context provider with static access"""
    _context: ApplicationContext | None = None
    _initialized = False
    _mutex = QMutex()  # Using Qt's mutex for compatibility with PyQt threading model

    @classmethod
    def initialize(cls, root_folder: Path) -> None:
        """Initialize context ONCE during application startup (main thread)"""
        if cls._initialized:
            raise RuntimeError("Context already initialized. Cannot reinitialize.")

        with QMutexLocker(cls._mutex):
            if cls._initialized:
                return

            # Create context (should happen in main thread)
            context = _create_app_context(root_folder)

            # Atomically set context
            cls._context = context
            cls._initialized = True

    @classmethod
    def get_context(cls) -> ApplicationContext:
        """Thread-safe context access from any thread"""
        if not cls._initialized:
            raise RuntimeError(
                "Context not initialized. Call ContextProvider.initialize() "
                "during application startup.",
            )
        return cls._context


def _create_app_context(root_folder: Path) -> ApplicationContext:
    """Create context (MUST be called from main thread)"""
    data_set_path = root_folder / DATA_SET_PATH
    db_path = root_folder / DB_FILE_NAME

    event_bus = QtEventBus()

    table_serializer = TableSerializer(root_folder)
    # Ollama client should be created in main thread per Ollama's requirements
    ollama_client = ollama.Client(timeout=300)
    ollama_llm_api = OllamaApi(ollama_client)

    task_api = YamlBenchmarkTaskApi(task_folder_path=data_set_path)
    prompt_builder_api = SimplePromptBuilderApi(task_api=task_api)

    data_api = SqLiteDataApi(db_path)
    result_api = AppResultApi(data_api=data_api)

    # Configure thread pool for benchmark operations
    thread_pool = QThreadPool()
    thread_pool.setMaxThreadCount(1)  # Serial execution for simplicity

    benchmark_flow_api = QtBenchmarkFlowApi(
        data_api=data_api,
        task_api=task_api,
        prompt_builder_api=prompt_builder_api,
        llm_api=ollama_llm_api,
        thread_pool=thread_pool,
    )
    benchmark_flow_api.subscribe_to_benchmark_status_events(
        lambda is_running: event_bus.emit_background_thread_is_running(
            is_running,
        ),
    )
    benchmark_flow_api.subscribe_to_benchmark_output_events(lambda msg: event_bus.emit_log_append(msg))
    benchmark_flow_api.subscribe_to_benchmark_progress_events(
        lambda progress: event_bus.emit_background_thread_progress(
            progress,
        ),
    )
    previous_run_widget_controller_api = PreviousRunWidgetController(
        data_api=data_api,
        task_api=task_api,
        benchmark_flow_api=benchmark_flow_api,
        event_bus=event_bus,
    )
    new_run_widget_controller_api = NewRunWidgetController(
        data_api=data_api,
        task_api=task_api,
        llm_api=ollama_llm_api,
        event_bus=event_bus,
        benchmark_flow_api=benchmark_flow_api,
    )
    log_widget_controller_api = LogWidgetController(
        event_bus=event_bus,
    )
    result_widget_controller_api = ResultWidgetController(
        event_bus=event_bus,
        result_api=result_api,
        benchmark_flow_api=benchmark_flow_api,
        data_api=data_api,
        llm_api=ollama_llm_api,
        task_api=task_api,
        table_serializer=table_serializer,
    )

    return ApplicationContext(
        ollama_llm_api=ollama_llm_api,
        task_api=task_api,
        prompt_builder_api=prompt_builder_api,
        data_api=data_api,
        result_api=result_api,
        benchmark_flow_api=benchmark_flow_api,
        event_bus=event_bus,
        previous_run_widget_controller_api=previous_run_widget_controller_api,
        new_run_widget_controller_api=new_run_widget_controller_api,
        log_widget_controller_api=log_widget_controller_api,
        result_widget_controller_api=result_widget_controller_api,
        table_serializer=table_serializer,
    )
