import logging
from pathlib import Path
from typing import Final, override

import ollama
from PyQt6.QtCore import QMutex, QMutexLocker, QThreadPool

from ollama_llm_bench.core.interfaces import (
    AppContext, BenchmarkFlowApi,
    BenchmarkTaskApi, DataApi, EventBus, ITableSerializer, LLMApi, PromptBuilderApi, ResultApi,
)
from ollama_llm_bench.core.ui_controllers import (
    LogWidgetControllerApi,
    NewRunWidgetControllerApi, PreviousRunWidgetControllerApi, ResultWidgetControllerApi,
)
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
from ollama_llm_bench.ui.controllers.status_listener import StatusListener
from ollama_llm_bench.utils.run_utils import get_benchmark_runs

_DATA_SET_PATH: Final[str] = "dataset"
_DB_FILE_NAME: Final[str] = "db.sqlite"

logger = logging.getLogger(__name__)


class ApplicationContext(AppContext):
    """
    Immutable application context container that provides access to all core services and controllers.
    Serves as the central dependency injection point for the application.
    """

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
        '_status_listener',
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
                 status_listener: StatusListener,
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
        self._status_listener = status_listener

    @override
    def get_event_bus(self) -> EventBus:
        """
        Retrieve the global event bus for pub/sub communication.

        Returns:
            Configured EventBus instance.
        """
        return self._event_bus

    @override
    def get_previous_run_widget_controller_api(self) -> PreviousRunWidgetControllerApi:
        """
        Retrieve the controller for the 'Previous Runs' widget.

        Returns:
            Controller API for managing previous run interactions.
        """
        return self._previous_run_widget_controller_api

    @override
    def get_new_run_widget_controller_api(self) -> NewRunWidgetControllerApi:
        """
        Retrieve the controller for the 'New Run' widget.

        Returns:
            Controller API for managing new run interactions.
        """
        return self._new_run_widget_controller_api

    @override
    def get_log_widget_controller_api(self) -> LogWidgetControllerApi:
        """
        Retrieve the controller for the log display widget.

        Returns:
            Controller API for managing log output.
        """
        return self._log_widget_controller_api

    @override
    def get_result_widget_controller_api(self) -> ResultWidgetControllerApi:
        """
        Retrieve the controller for the results display widget.

        Returns:
            Controller API for managing results display.
        """
        return self._result_widget_controller_api

    @override
    def get_data_api(self) -> DataApi:
        """
        Retrieve the data persistence interface.

        Returns:
            DataApi instance for storage operations.
        """
        return self._data_api

    @override
    def get_llm_api(self) -> LLMApi:
        """
        Retrieve the LLM inference interface.

        Returns:
            LLMApi instance for model interaction.
        """
        return self._ollama_llm_api

    @override
    def get_result_api(self) -> ResultApi:
        """
        Retrieve the result computation interface.

        Returns:
            ResultApi instance for generating summaries.
        """
        return self._result_api

    @override
    def send_initialization_events(self) -> None:
        """
        Send initial state events to synchronize all UI components.
        Publishes initial run list, model list, and selection state.
        """
        logger.debug("send_initial_state")
        data_api = self.get_data_api()
        llm_api = self.get_llm_api()
        event_bus = self.get_event_bus()

        try:
            runs = data_api.retrieve_benchmark_runs()
            if runs and len(runs) > 0:
                latest_run_id = runs[0].run_id
                runs_list = get_benchmark_runs(self._data_api)
                logger.debug("received runs {}".format(runs))

                event_bus.emit_run_id_changed(latest_run_id)
                event_bus.emit_run_ids_changed(runs_list)
            else:
                logger.debug("no runs found")
                event_bus.emit_run_id_changed(None)
                event_bus.emit_run_ids_changed([])
        except Exception as e:
            logger.warning("exception {}".format(e))
            event_bus.emit_run_id_changed(None)
            event_bus.emit_run_ids_changed([])

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


class ContextProvider:
    """
    Thread-safe singleton provider for the application context.
    Ensures proper initialization and access to the ApplicationContext from any thread.
    """

    _context: ApplicationContext | None = None
    _initialized = False
    _mutex = QMutex()  # Using Qt's mutex for compatibility with PyQt threading model

    @classmethod
    def initialize(cls, app_root: Path, dataset_path: Path = None) -> None:
        """
        Initialize the application context during startup.

        Args:
            app_root: Root directory for application data and outputs.
            dataset_path: Optional path to benchmark task definitions. If not provided,
                         defaults to app_root/dataset.

        Raises:
            RuntimeError: If context has already been initialized.
            FileNotFoundError: If the dataset path does not exist.
            NotADirectoryError: If the dataset path is not a directory.
        """
        if cls._initialized:
            raise RuntimeError("Context already initialized. Cannot reinitialize.")

        with QMutexLocker(cls._mutex):
            if cls._initialized:
                return

            # If dataset_path is not provided, use the default within app_root
            if dataset_path is None:
                dataset_path = app_root / _DATA_SET_PATH

            # Create context (should happen in main thread)
            context = _create_app_context(app_root, dataset_path)

            # Atomically set context
            cls._context = context
            cls._initialized = True

    @classmethod
    def get_context(cls) -> ApplicationContext:
        """
        Retrieve the initialized application context.

        Returns:
            The singleton ApplicationContext instance.

        Raises:
            RuntimeError: If context has not been initialized.
        """
        if not cls._initialized:
            raise RuntimeError(
                "Context not initialized. Call ContextProvider.initialize() "
                "during application startup.",
            )
        return cls._context


def _create_app_context(app_root: Path, dataset_path: Path) -> ApplicationContext:
    """
    Create the application context with all required services and controllers.

    Args:
        app_root: Root directory for application data.
        dataset_path: Path to benchmark task definition files.

    Returns:
        Fully configured ApplicationContext instance.

    Raises:
        FileNotFoundError: If dataset path does not exist.
        NotADirectoryError: If dataset path is not a directory.
    """
    db_path = app_root / _DB_FILE_NAME
    event_bus = QtEventBus()

    # Verify dataset path exists
    if not dataset_path.exists():
        logger.error(f"Dataset path does not exist: {dataset_path}")
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_path}")
    if not dataset_path.is_dir():
        logger.error(f"Dataset path is not a directory: {dataset_path}")
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_path}")

    table_serializer = TableSerializer(app_root)
    # Ollama client should be created in main thread per Ollama's requirements
    ollama_client = ollama.Client(timeout=300)
    ollama_llm_api = OllamaApi(ollama_client)

    task_api = YamlBenchmarkTaskApi(task_folder_path=dataset_path)
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
        data_api=data_api,
        table_serializer=table_serializer,
    )
    status_listener = StatusListener(data_api=data_api,
                                     event_bus=event_bus,
                                     benchmark_flow_api=benchmark_flow_api,
                                     result_api=result_api,
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
        status_listener=status_listener,
    )
