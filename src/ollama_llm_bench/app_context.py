from pathlib import Path

import ollama
from PyQt6.QtCore import QMutex, QMutexLocker, QThreadPool

from ollama_llm_bench.core.interfaces import (
    BenchmarkApplicationControllerApi, BenchmarkFlowApi,
    BenchmarkTaskApi, DataApi, LLMApi, PromptBuilderApi, ResultApi,
)
from ollama_llm_bench.qt_classes.qt_benchmark_controller_api import QtBenchmarkControllerAPI
from ollama_llm_bench.qt_classes.qt_benchmark_flow import QtBenchmarkFlowApi
from ollama_llm_bench.qt_classes.qt_event_bus import QtEventBus
from ollama_llm_bench.services.app_result_api import AppResultApi
from ollama_llm_bench.services.ollama_llm_api import OllamaApi
from ollama_llm_bench.services.simple_prompt_builder_api import SimplePromptBuilderApi
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.services.yaml_benchmark_task_api import YamlBenchmarkTaskApi

DATA_SET_PATH = "dataset"
DB_FILE_NAME = "db.sqlite"


class AppContext:
    """Immutable application context container"""
    __slots__ = (
        '_ollama_llm_api', '_task_api', '_prompt_builder_api',
        '_data_api', '_result_api', '_benchmark_flow_api',
        '_benchmark_controller_api', '_event_bus'
    )

    def __init__(self, *,
                 ollama_llm_api: LLMApi,
                 task_api: BenchmarkTaskApi,
                 prompt_builder_api: PromptBuilderApi,
                 data_api: DataApi,
                 result_api: ResultApi,
                 benchmark_flow_api: BenchmarkFlowApi,
                 benchmark_controller_api: BenchmarkApplicationControllerApi,
                 event_bus: QtEventBus,
                 ):
        self._ollama_llm_api = ollama_llm_api
        self._task_api = task_api
        self._prompt_builder_api = prompt_builder_api
        self._data_api = data_api
        self._result_api = result_api
        self._benchmark_flow_api = benchmark_flow_api
        self._benchmark_controller_api = benchmark_controller_api
        self._event_bus = event_bus

    def get_benchmark_controller_api(self) -> BenchmarkApplicationControllerApi:
        return self._benchmark_controller_api

    def get_event_bus(self) -> QtEventBus:
        return self._event_bus


class ContextProvider:
    """PyQt6-safe singleton context provider with static access"""
    _context: AppContext | None = None
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
    def get_context(cls) -> AppContext:
        """Thread-safe context access from any thread"""
        if not cls._initialized:
            raise RuntimeError(
                "Context not initialized. Call ContextProvider.initialize() "
                "during application startup.",
            )
        return cls._context


def _create_app_context(root_folder: Path) -> AppContext:
    """Create context (MUST be called from main thread)"""
    data_set_path = root_folder / DATA_SET_PATH
    db_path = root_folder / DB_FILE_NAME

    # Ollama client should be created in main thread per Ollama's requirements
    ollama_client = ollama.Client()
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

    benchmark_controller_api = QtBenchmarkControllerAPI(
        data_api=data_api,
        llm_api=ollama_llm_api,
        task_api=task_api,
        benchmark_flow_api=benchmark_flow_api,
        result_api=result_api,
    )

    event_bus = QtEventBus()

    return AppContext(
        ollama_llm_api=ollama_llm_api,
        task_api=task_api,
        prompt_builder_api=prompt_builder_api,
        data_api=data_api,
        result_api=result_api,
        benchmark_flow_api=benchmark_flow_api,
        benchmark_controller_api=benchmark_controller_api,
        event_bus=event_bus,
    )
