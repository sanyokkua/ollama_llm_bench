import logging
from collections.abc import Callable
from typing import override

from PySide6.QtCore import QObject, QThreadPool, Signal

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    BenchmarkFlowApi,
    BenchmarkTaskApi,
    DataApi,
    EvaluatorApi,
    EventBus,
    JudgePromptServiceApi,
    JudgeSummaryServiceApi,
    LLMApi,
    LLMJudgeEvaluatorApi,
    LogFileWriterApi,
    PromptBuilderApi,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import BenchmarkRunStatus, ReporterStatusMsg
from ollama_llm_bench.backend.services.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.ui.qt_classes.meta_class import MetaQObjectABC
from ollama_llm_bench.ui.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask

logger = logging.getLogger(__name__)


class QtBenchmarkFlowApi(BenchmarkFlowApi, QObject, metaclass=MetaQObjectABC):
    """
    Qt-based implementation of BenchmarkFlowApi for managing asynchronous benchmark execution.
    Uses QThreadPool for background execution and emits signals for status, output, and progress.
    """

    benchmark_status_events = Signal(bool)  # running/stopped
    benchmark_output_events = Signal(str)  # log messages
    benchmark_progress_events = Signal(ReporterStatusMsg)  # progress updates

    def __init__(
        self,
        *,
        data_api: DataApi,
        task_api: BenchmarkTaskApi,
        prompt_builder_api: PromptBuilderApi,
        llm_api: LLMApi,
        thread_pool: QThreadPool,
        event_bus: EventBus,
        provider_registry: ProviderRegistryApi,
        task_loader: TaskFileLoaderApi,
        judge_prompt_service: JudgePromptServiceApi,
        judge_summary_service: JudgeSummaryServiceApi,
        app_settings: AppSettingsServiceApi,
        rule_evaluator: EvaluatorApi,
        keyword_evaluator: EvaluatorApi,
        cosine_evaluator: EvaluatorApi,
        llm_judge_evaluator: LLMJudgeEvaluatorApi,
        log_file_writer: LogFileWriterApi,
        perf_task_generator: PerformanceTaskGenerator | None = None,
    ):
        """
        Initialize the benchmark flow controller.

        Args:
            data_api: Interface for data persistence operations.
            task_api: Interface for accessing benchmark tasks (V1 compat, passed to ABC).
            prompt_builder_api: Interface for constructing prompts (V1 compat, passed to ABC).
            llm_api: Interface for LLM inference (V1 compat, passed to ABC).
            thread_pool: Thread pool for executing benchmark tasks asynchronously.
            event_bus: Event bus for V2 pipeline event emission.
            provider_registry: Registry providing access to all LLM and embedding providers.
            task_loader: V2 benchmark task file loader.
            judge_prompt_service: Prompt builder for inference and judge calls.
            app_settings: Application settings KV-store.
            rule_evaluator: Layer 1 rule-based evaluator.
            keyword_evaluator: Layer 2 keyword evaluator.
            cosine_evaluator: Layer 3 cosine similarity evaluator.
            llm_judge_evaluator: Layer 4 LLM judge evaluator.
            log_file_writer: Log file writer service for writing structured benchmark entries to disk.
        """
        super().__init__(
            data_api=data_api,
            task_api=task_api,
            prompt_builder_api=prompt_builder_api,
            llm_api=llm_api,
        )
        self._thread_pool = thread_pool
        self._event_bus = event_bus
        self._provider_registry = provider_registry
        self._task_loader = task_loader
        self._judge_prompt_service = judge_prompt_service
        self._judge_summary_service = judge_summary_service
        self._app_settings = app_settings
        self._rule_evaluator = rule_evaluator
        self._keyword_evaluator = keyword_evaluator
        self._cosine_evaluator = cosine_evaluator
        self._llm_judge_evaluator = llm_judge_evaluator
        self._log_file_writer = log_file_writer
        self._perf_task_generator = perf_task_generator
        self._current_task: BenchmarkExecutionTask | None = None
        self._current_run_id: int | None = None
        logger.debug("QtBenchmarkFlowApi initialized")

    @override
    def start_execution(self, run_id: int) -> None:
        """
        Start a new benchmark execution asynchronously.

        Args:
            run_id: Identifier of the benchmark run to execute.

        Raises:
            ValueError: If the run ID is invalid or the run is not in NOT_COMPLETED state.
        """
        logger.info(f"Request to start benchmark execution for run_id={run_id}")

        # Prevent starting if already running
        if self.is_running():
            logger.warning("A benchmark is already running; start request ignored")
            return

        # Validate run
        try:
            run = self._data_api.retrieve_benchmark_run(run_id)
            logger.debug(f"Retrieved benchmark run: {run}")
            if run.status != BenchmarkRunStatus.NOT_COMPLETED:
                raise ValueError(
                    f"Benchmark run #{run_id} is not in NOT_COMPLETED state (current: {run.status})",
                )
        except Exception as e:
            logger.error(f"Invalid run_id={run_id}: {e}")
            raise ValueError(f"Invalid run_id: {run_id}") from e

        # Disconnect old signals (if any)
        self._disconnect_current_task()

        # Create execution task
        task = BenchmarkExecutionTask(
            run_id=run_id,
            data_api=self._data_api,
            task_loader=self._task_loader,
            judge_prompt_service=self._judge_prompt_service,
            judge_summary_service=self._judge_summary_service,
            provider_registry=self._provider_registry,
            event_bus=self._event_bus,
            app_settings=self._app_settings,
            rule_evaluator=self._rule_evaluator,
            keyword_evaluator=self._keyword_evaluator,
            cosine_evaluator=self._cosine_evaluator,
            llm_judge_evaluator=self._llm_judge_evaluator,
            log_file_writer=self._log_file_writer,
            perf_task_generator=self._perf_task_generator,
        )
        logger.debug(f"Created BenchmarkExecutionTask for run_id={run_id}")

        # Connect signals
        self._connect_task_signals(task)

        # Store state and start in thread pool
        self._current_task = task
        self._current_run_id = run_id
        self._thread_pool.start(task)
        logger.info(f"Benchmark execution task for run_id={run_id} started in thread pool")

        # Notify listeners
        self.benchmark_status_events.emit(self.is_running())

    @override
    def pause_execution(self) -> None:
        """Pause the running benchmark at the next task boundary."""
        if self._current_task is not None:
            self._current_task.pause()

    @override
    def resume_execution(self) -> None:
        """Resume a paused benchmark run."""
        if self._current_task is not None:
            self._current_task.resume()

    @override
    def stop_execution(self) -> None:
        """
        Request graceful termination of the currently running benchmark.
        """
        logger.info("Request to stop benchmark execution")
        if not self.is_running() or self._current_task is None:
            logger.warning("No benchmark is currently running; stop request ignored")
            return
        self._current_task.stop()
        logger.debug(f"Stop signal sent to run_id={self._current_run_id}")

    @override
    def shutdown(self, *, timeout_ms: int = 5000) -> None:
        """Stop any running benchmark and wait for the worker thread to finish."""
        logger.info(f"Benchmark shutdown requested (timeout={timeout_ms}ms)")
        if self._current_task is not None:
            self._current_task.stop()

        for provider in self._provider_registry.get_all_providers():
            if hasattr(provider, "abort"):
                try:
                    provider.abort()
                except Exception:
                    logger.debug("provider_abort_failed")
        try:
            emb = self._provider_registry.get_embedding_provider()
            if hasattr(emb, "abort"):
                emb.abort()
        except Exception:
            logger.debug("embedding_provider_abort_failed")

        self._thread_pool.clear()
        finished = self._thread_pool.waitForDone(timeout_ms)
        if not finished:
            logger.warning(f"Thread pool did not finish within {timeout_ms}ms — proceeding with close")
        logger.info("Benchmark shutdown complete")

    @override
    def is_running(self) -> bool:
        """
        Check if a benchmark execution is currently active.

        Returns:
            True if a benchmark is running, False otherwise.
        """
        return self._current_task is not None and not self._current_task.is_stopped()

    @override
    def get_current_run_id(self) -> int | None:
        """
        Retrieve the ID of the currently executing benchmark run.

        Returns:
            Run ID if a benchmark is running, None otherwise.
        """
        return self._current_run_id

    @override
    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to changes in benchmark execution status.

        Args:
            callback: Function to invoke with True (running) or False (stopped).
        """
        self.benchmark_status_events.connect(callback)
        logger.debug("Subscribed to benchmark_status_events")
        callback(self.is_running())  # immediate notification
        logger.debug(f"Immediate status callback sent: running={self.is_running()}")

    @override
    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to log output messages generated during benchmark execution.

        Args:
            callback: Function to invoke with log message strings.
        """
        self.benchmark_output_events.connect(callback)
        logger.debug("Subscribed to benchmark_output_events")

    @override
    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """
        Subscribe to progress updates during benchmark execution.

        Args:
            callback: Function to invoke with ReporterStatusMsg objects.
        """
        self.benchmark_progress_events.connect(callback)
        logger.debug("Subscribed to benchmark_progress_events")

    def _connect_task_signals(self, task: BenchmarkExecutionTask) -> None:
        """
        Connect internal task signals to public event signals.

        Args:
            task: The benchmark execution task to connect.
        """
        logger.debug("Connecting task signals")
        task.signals.status_changed.connect(self.benchmark_status_events)
        task.signals.log_message.connect(self.benchmark_output_events)
        task.signals.progress.connect(self.benchmark_progress_events)

    def _disconnect_current_task(self) -> None:
        """
        Disconnect all signals from the current task and reset internal state.
        """
        if self._current_task is None:
            logger.debug("No current task to disconnect")
            return

        logger.debug(f"Disconnecting signals for run_id={self._current_run_id}")
        try:
            self._current_task.signals.status_changed.disconnect(self.benchmark_status_events)
            self._current_task.signals.log_message.disconnect(self.benchmark_output_events)
            self._current_task.signals.progress.disconnect(self.benchmark_progress_events)
        except TypeError:
            logger.debug("Some task signals may have already been disconnected")
        finally:
            logger.debug(f"Clearing current task state for run_id={self._current_run_id}")
            self._current_task = None
            self._current_run_id = None
