from pathlib import Path

import ollama
from PyQt6.QtCore import QThreadPool

from ollama_llm_bench.core.interfaces import (
    BenchmarkApplicationControllerApi, BenchmarkFlowApi,
    BenchmarkTaskApi,
    DataApi,
    LLMApi,
    PromptBuilderApi,
    ResultApi,
)
from ollama_llm_bench.qt_classes.qt_benchmark_controller_api import QtBenchmarkControllerAPI
from ollama_llm_bench.qt_classes.qt_benchmark_flow import QtBenchmarkFlowApi
from ollama_llm_bench.services.app_result_api import AppResultApi
from ollama_llm_bench.services.ollama_llm_api import OllamaApi
from ollama_llm_bench.services.simple_prompt_builder_api import SimplePromptBuilderApi
from ollama_llm_bench.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.services.yaml_benchmark_task_api import YamlBenchmarkTaskApi

DATA_SET_PATH = "dataset"
DB_FILE_NAME = "db.sqlite"


class AppContext:
    def __init__(self, *,
                 ollama_llm_api: LLMApi,
                 task_api: BenchmarkTaskApi,
                 prompt_builder_api: PromptBuilderApi,
                 data_api: DataApi,
                 result_api: ResultApi,
                 benchmark_flow_api: BenchmarkFlowApi,
                 benchmark_controller_api: BenchmarkApplicationControllerApi,
                 ):
        self._ollama_llm_api: LLMApi = ollama_llm_api
        self._task_api: BenchmarkTaskApi = task_api
        self._prompt_builder_api: PromptBuilderApi = prompt_builder_api
        self._data_api: DataApi = data_api
        self._result_api: ResultApi = result_api
        self._benchmark_flow_api: BenchmarkFlowApi = benchmark_flow_api
        self._benchmark_controller_api: BenchmarkApplicationControllerApi = benchmark_controller_api

    def get_benchmark_controller_api(self) -> BenchmarkApplicationControllerApi:
        return self._benchmark_controller_api


def create_app_context(root_folder: Path) -> AppContext:
    data_set_path = root_folder / DATA_SET_PATH
    db_path = root_folder / DB_FILE_NAME

    ollama_client = ollama.Client()
    ollama_llm_api: LLMApi = OllamaApi(ollama_client)

    task_api: BenchmarkTaskApi = YamlBenchmarkTaskApi(task_folder_path=data_set_path)
    prompt_builder_api: PromptBuilderApi = SimplePromptBuilderApi(task_api=task_api)

    data_api: DataApi = SqLiteDataApi(db_path)
    result_api: ResultApi = AppResultApi(data_api=data_api)

    thread_pool = QThreadPool()
    thread_pool.setMaxThreadCount(1)
    benchmark_flow_api: BenchmarkFlowApi = QtBenchmarkFlowApi(
        data_api=data_api,
        task_api=task_api,
        prompt_builder_api=prompt_builder_api,
        llm_api=ollama_llm_api,
        thread_pool=thread_pool,
    )

    benchmark_controller_api: BenchmarkApplicationControllerApi = QtBenchmarkControllerAPI(
        data_api=data_api,
        llm_api=ollama_llm_api,
        task_api=task_api,
        benchmark_flow_api=benchmark_flow_api,
        result_api=result_api,
    )

    return AppContext(
        ollama_llm_api=ollama_llm_api,
        task_api=task_api,
        prompt_builder_api=prompt_builder_api,
        data_api=data_api,
        result_api=result_api,
        benchmark_flow_api=benchmark_flow_api,
        benchmark_controller_api=benchmark_controller_api,
    )
