import importlib.resources
import logging
import shutil
from pathlib import Path
from typing import Final, override

from PySide6.QtCore import QMutex, QMutexLocker, QThreadPool

from ollama_llm_bench.backend.core.interfaces import (
    AppContext,
    AppSettingsServiceApi,
    BenchmarkFlowApi,
    DataApi,
    EmbeddingProviderApi,
    EvaluatorApi,
    EventBus,
    JudgePromptServiceApi,
    LLMJudgeEvaluatorApi,
    LogFileWriterApi,
    ProviderRegistryApi,
    ResultApi,
    TableSerializerApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.ui_controllers import (
    LogWidgetControllerApi,
    ResultWidgetControllerApi,
    RunConfigControllerApi,
    SettingsWidgetControllerApi,
)
from ollama_llm_bench.backend.services.app_readiness_service import AppReadinessService
from ollama_llm_bench.backend.services.app_result_api import AppResultApi
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_EMBEDDING_CUSTOM_PATTERNS,
    SETTING_PROVIDER_TRIP_PROBE_INTERVAL_S,
    SETTING_PROVIDER_TRIP_THRESHOLD,
    SETTING_PROVIDER_TRIP_WINDOW_S,
    AppSettingsService,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.embedding_service import EmbeddingService
from ollama_llm_bench.backend.services.evaluators.cosine_evaluator import CosineSimilarityEvaluator
from ollama_llm_bench.backend.services.evaluators.keyword_evaluator import KeywordEvaluator
from ollama_llm_bench.backend.services.evaluators.llm_judge_evaluator import LLMJudgeEvaluator
from ollama_llm_bench.backend.services.evaluators.rule_based_evaluator import RuleBasedEvaluator
from ollama_llm_bench.backend.services.judge_prompt_service import JudgePromptService
from ollama_llm_bench.backend.services.judge_summary_service import JudgeSummaryService
from ollama_llm_bench.backend.services.llm_error_classifier import LlmErrorClassifier
from ollama_llm_bench.backend.services.log_file_writer import LogFileWriter
from ollama_llm_bench.backend.services.model_capability_service import ModelCapabilityService
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.services.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.backend.services.provider_circuit_breaker import ProviderCircuitBreaker
from ollama_llm_bench.backend.services.provider_config_loader import ProviderConfigLoader
from ollama_llm_bench.backend.services.provider_health_checker import ProviderHealthChecker
from ollama_llm_bench.backend.services.provider_registry import ProviderRegistry
from ollama_llm_bench.backend.services.sq_lite_data_api import SqLiteDataApi
from ollama_llm_bench.backend.services.sqlite_provider_config_repository import SqliteProviderConfigRepository
from ollama_llm_bench.backend.services.table_serializer import TableSerializer
from ollama_llm_bench.backend.services.task_file_loader import TaskFileLoader
from ollama_llm_bench.backend.utils.run_utils import get_benchmark_runs
from ollama_llm_bench.ui.controllers.log_widget_controller import LogWidgetController
from ollama_llm_bench.ui.controllers.result_widget_controller import ResultWidgetController
from ollama_llm_bench.ui.controllers.run_config_controller import RunConfigController
from ollama_llm_bench.ui.controllers.settings_widget_controller import SettingsWidgetController
from ollama_llm_bench.ui.controllers.status_listener import StatusListener
from ollama_llm_bench.ui.qt_classes.qt_benchmark_flow import QtBenchmarkFlowApi
from ollama_llm_bench.ui.qt_classes.qt_event_bus import QtEventBus

_DATA_SET_PATH: Final[str] = "dataset"
_DB_FILE_NAME: Final[str] = "db.sqlite"

logger = logging.getLogger(__name__)


class _NullEmbeddingProvider:
    """Fallback embedding provider used when no embedding backend is configured."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("No embedding provider configured")


class ApplicationContext(AppContext):
    """
    Immutable application context container that provides access to all core services and controllers.
    Serves as the central dependency injection point for the application.
    """

    __slots__ = (
        "_app_settings_service",
        "_benchmark_flow_api",
        "_data_api",
        "_event_bus",
        "_judge_prompt_service",
        "_log_file_writer",
        "_log_widget_controller_api",
        "_provider_registry",
        "_result_api",
        "_result_widget_controller_api",
        "_run_config_controller",
        "_settings_widget_controller",
        "_status_listener",
        "_table_serializer",
        "_task_file_loader",
    )

    def __init__(
        self,
        *,
        data_api: DataApi,
        result_api: ResultApi,
        benchmark_flow_api: BenchmarkFlowApi,
        event_bus: EventBus,
        log_widget_controller_api: LogWidgetControllerApi,
        result_widget_controller_api: ResultWidgetControllerApi,
        table_serializer: TableSerializerApi,
        status_listener: StatusListener,
        provider_registry: ProviderRegistryApi,
        app_settings_service: AppSettingsServiceApi,
        task_file_loader: TaskFileLoaderApi,
        judge_prompt_service: JudgePromptServiceApi,
        log_file_writer: LogFileWriterApi,
        settings_widget_controller: SettingsWidgetControllerApi,
        run_config_controller: RunConfigControllerApi,
    ):
        self._data_api = data_api
        self._result_api = result_api
        self._benchmark_flow_api = benchmark_flow_api
        self._event_bus = event_bus
        self._log_widget_controller_api = log_widget_controller_api
        self._result_widget_controller_api = result_widget_controller_api
        self._table_serializer = table_serializer
        self._status_listener = status_listener
        self._provider_registry = provider_registry
        self._app_settings_service = app_settings_service
        self._task_file_loader = task_file_loader
        self._judge_prompt_service = judge_prompt_service
        self._log_file_writer = log_file_writer
        self._settings_widget_controller = settings_widget_controller
        self._run_config_controller = run_config_controller

    @override
    def get_event_bus(self) -> EventBus:
        """
        Retrieve the global event bus for pub/sub communication.

        Returns:
            Configured EventBus instance.
        """
        return self._event_bus

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
        event_bus = self.get_event_bus()

        try:
            runs = data_api.retrieve_benchmark_runs()
            if runs and len(runs) > 0:
                latest_run_id = runs[0].run_id
                runs_list = get_benchmark_runs(self._data_api)
                logger.debug("received runs %s", runs)

                event_bus.emit_run_id_changed(latest_run_id)
                event_bus.emit_run_ids_changed(runs_list)
            else:
                logger.debug("no runs found")
                event_bus.emit_run_id_changed(None)
                event_bus.emit_run_ids_changed([])
        except Exception as e:
            logger.warning("exception %s", e)
            event_bus.emit_run_id_changed(None)
            event_bus.emit_run_ids_changed([])

    @override
    def get_provider_registry(self) -> ProviderRegistryApi:
        """
        Return the provider registry for multi-provider LLM access.

        Returns:
            Configured ProviderRegistryApi instance.
        """
        return self._provider_registry

    @override
    def get_app_settings_service(self) -> AppSettingsServiceApi:
        """Retrieve the application settings KV-store service.

        Returns:
            AppSettingsServiceApi instance.
        """
        return self._app_settings_service

    @override
    def get_task_file_loader(self) -> TaskFileLoaderApi:
        """Retrieve the V2 benchmark task file loader.

        Returns:
            TaskFileLoaderApi instance.
        """
        return self._task_file_loader

    @override
    def get_judge_prompt_service(self) -> JudgePromptServiceApi:
        """Retrieve the judge prompt builder service.

        Returns:
            JudgePromptServiceApi instance.
        """
        return self._judge_prompt_service

    @override
    def get_log_file_writer(self) -> LogFileWriterApi:
        """Retrieve the log file writer service.

        Returns:
            LogFileWriterApi instance for writing benchmark log entries to disk.
        """
        return self._log_file_writer

    @override
    def get_settings_widget_controller(self) -> SettingsWidgetControllerApi:
        """Retrieve the settings dialog controller.

        Returns:
            Configured SettingsWidgetControllerApi instance.
        """
        return self._settings_widget_controller

    @override
    def get_run_config_controller(self) -> RunConfigControllerApi:
        """Retrieve the unified run configuration controller.

        Returns:
            RunConfigControllerApi for provider/model discovery and benchmark lifecycle.
        """
        return self._run_config_controller

    @override
    def get_benchmark_flow_api(self) -> BenchmarkFlowApi:
        """Retrieve the benchmark execution flow controller."""
        return self._benchmark_flow_api


class ContextProvider:
    """
    Thread-safe singleton provider for the application context.
    Ensures proper initialization and access to the ApplicationContext from any thread.
    """

    _context: ApplicationContext | None = None
    _initialized = False
    _mutex: QMutex | None = None  # Created lazily after QApplication exists

    @classmethod
    def initialize(cls, app_root: Path, dataset_path: Path | None = None) -> None:
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

        if cls._mutex is None:
            cls._mutex = QMutex()

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
                "Context not initialized. Call ContextProvider.initialize() during application startup.",
            )
        if cls._context is None:
            raise RuntimeError("Context is None despite _initialized being True — invariant violated.")
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
        logger.error("Dataset path does not exist: %s", dataset_path)
        raise FileNotFoundError(f"Dataset path does not exist: {dataset_path}")
    if not dataset_path.is_dir():
        logger.error("Dataset path is not a directory: %s", dataset_path)
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_path}")

    table_serializer = TableSerializer(app_root)

    data_api = SqLiteDataApi(db_path)
    result_api = AppResultApi(data_api=data_api)

    classifier = LlmErrorClassifier()
    capability_service = ModelCapabilityService(data_api=data_api)

    providers_yaml_path = app_root / "providers.yaml"

    if not providers_yaml_path.exists():
        bundled = importlib.resources.files("ollama_llm_bench").joinpath("providers.yaml")
        with importlib.resources.as_file(bundled) as bundled_path:
            shutil.copy(bundled_path, providers_yaml_path)

    config_loader = ProviderConfigLoader()
    config_repository = SqliteProviderConfigRepository(data_api=data_api)
    registry = ProviderRegistry(
        config_loader=config_loader,
        providers_yaml_path=providers_yaml_path,
        capability_service=capability_service,
        classifier=classifier,
        config_repository=config_repository,
    )
    try:
        registry.load()
    except Exception:
        logger.exception("provider_registry_load_failed")

    # V2 services — instantiate after registry so embedding provider is available
    task_loader = TaskFileLoader()
    perf_task_generator = PerformanceTaskGenerator()
    app_settings = AppSettingsService(data_api=data_api)
    judge_prompt_svc = JudgePromptService()
    judge_summary_svc = JudgeSummaryService(provider_registry=registry)
    log_file_writer = LogFileWriter(app_root=app_root)

    embedding_provider: EmbeddingProviderApi
    try:
        embedding_provider = registry.get_embedding_provider()
    except RuntimeError:
        logger.warning("embedding_provider_unavailable_using_null_fallback")
        embedding_provider = _NullEmbeddingProvider()

    embedding_service = EmbeddingService(provider=embedding_provider)

    health_checker = ProviderHealthChecker()
    readiness_service = AppReadinessService(
        provider_registry=registry,
        embedding_provider=embedding_provider,
        app_settings=app_settings,
        health_checker=health_checker,
    )

    rule_evaluator: EvaluatorApi = RuleBasedEvaluator()
    keyword_evaluator: EvaluatorApi = KeywordEvaluator(embedding_service=embedding_provider)
    cosine_evaluator: EvaluatorApi = CosineSimilarityEvaluator(embedding_service=embedding_provider)
    llm_judge_evaluator: LLMJudgeEvaluatorApi = LLMJudgeEvaluator(
        provider_registry=registry,
        judge_prompt_service=judge_prompt_svc,
    )

    # Configure thread pool for benchmark operations
    thread_pool = QThreadPool()
    thread_pool.setMaxThreadCount(1)  # Serial execution for simplicity

    circuit_breaker = ProviderCircuitBreaker(
        failure_threshold=app_settings.get_int(SETTING_PROVIDER_TRIP_THRESHOLD, default=3),
        window_s=float(app_settings.get_int(SETTING_PROVIDER_TRIP_WINDOW_S, default=600)),
        probe_interval_s=float(app_settings.get_int(SETTING_PROVIDER_TRIP_PROBE_INTERVAL_S, default=60)),
    )

    benchmark_flow_api = QtBenchmarkFlowApi(
        data_api=data_api,
        thread_pool=thread_pool,
        event_bus=event_bus,
        provider_registry=registry,
        task_loader=task_loader,
        judge_prompt_service=judge_prompt_svc,
        judge_summary_service=judge_summary_svc,
        app_settings=app_settings,
        rule_evaluator=rule_evaluator,
        keyword_evaluator=keyword_evaluator,
        cosine_evaluator=cosine_evaluator,
        llm_judge_evaluator=llm_judge_evaluator,
        log_file_writer=log_file_writer,
        perf_task_generator=perf_task_generator,
        capability_service=capability_service,
        circuit_breaker=circuit_breaker,
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
    log_widget_controller_api = LogWidgetController(
        event_bus=event_bus,
    )
    result_widget_controller_api = ResultWidgetController(
        event_bus=event_bus,
        data_api=data_api,
        table_serializer=table_serializer,
        app_settings_service=app_settings,
    )
    status_listener = StatusListener(
        data_api=data_api,
        event_bus=event_bus,
        benchmark_flow_api=benchmark_flow_api,
        result_api=result_api,
    )

    custom_patterns_raw = app_settings.get(SETTING_EMBEDDING_CUSTOM_PATTERNS) or ""
    custom_patterns = tuple(p.strip() for p in custom_patterns_raw.split(",") if p.strip())
    embedding_classifier = EmbeddingModelClassifier(extra_patterns=custom_patterns)

    settings_widget_controller = SettingsWidgetController(
        provider_registry=registry,
        provider_config_loader=config_loader,
        app_settings=app_settings,
        providers_yaml_path=providers_yaml_path,
        embedding_service=embedding_service,
        event_bus=event_bus,
        embedding_classifier=embedding_classifier,
        config_repository=config_repository,
    )

    run_config_controller = RunConfigController(
        data_api=data_api,
        provider_registry=registry,
        benchmark_flow_api=benchmark_flow_api,
        event_bus=event_bus,
        task_file_loader=task_loader,
        app_settings_service=app_settings,
        embedding_classifier=embedding_classifier,
        app_readiness_service=readiness_service,
        name_parser=ModelNameParser(),
    )

    return ApplicationContext(
        data_api=data_api,
        result_api=result_api,
        benchmark_flow_api=benchmark_flow_api,
        event_bus=event_bus,
        log_widget_controller_api=log_widget_controller_api,
        result_widget_controller_api=result_widget_controller_api,
        table_serializer=table_serializer,
        status_listener=status_listener,
        provider_registry=registry,
        app_settings_service=app_settings,
        task_file_loader=task_loader,
        judge_prompt_service=judge_prompt_svc,
        log_file_writer=log_file_writer,
        settings_widget_controller=settings_widget_controller,
        run_config_controller=run_config_controller,
    )
