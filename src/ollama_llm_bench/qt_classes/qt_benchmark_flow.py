from typing import Callable, Optional, override

from PyQt6.QtCore import QObject, QThreadPool, pyqtSignal

from ollama_llm_bench.core.interfaces import BenchmarkFlowApi, BenchmarkTaskApi, DataApi, LLMApi, PromptBuilderApi
from ollama_llm_bench.core.models import BenchmarkRunStatus, ReporterStatusMsg
from ollama_llm_bench.qt_classes.meta_class import MetaQObjectABC
from ollama_llm_bench.qt_classes.qt_benchmark_execution_task import BenchmarkExecutionTask


class QtBenchmarkFlowApi(QObject, BenchmarkFlowApi, metaclass=MetaQObjectABC):
    benchmark_status_events = pyqtSignal(bool)  # running/stopped
    benchmark_output_events = pyqtSignal(str)  # log messages
    benchmark_progress_events = pyqtSignal(ReporterStatusMsg)  # progress updates

    def __init__(
        self,
        *,
        data_api: DataApi,
        task_api: BenchmarkTaskApi,
        prompt_builder_api: PromptBuilderApi,
        llm_api: LLMApi,
        thread_pool: QThreadPool,
    ):
        super().__init__(
            data_api=data_api,
            task_api=task_api,
            prompt_builder_api=prompt_builder_api,
            llm_api=llm_api,
        )
        self._thread_pool = thread_pool

        # Execution state
        self._current_task: Optional[BenchmarkExecutionTask] = None
        self._current_run_id: Optional[int] = None

    @override
    def start_execution(self, run_id: int) -> None:
        """Start a new benchmark execution (non-blocking)"""
        if self.is_running():
            raise RuntimeError("A benchmark is already running")

        # Validate run exists
        try:
            run = self._data_api.retrieve_benchmark_run(run_id)
            if run.status != BenchmarkRunStatus.NOT_COMPLETED:
                raise ValueError(f"Benchmark run #{run_id} is not in NOT_COMPLETED state")
        except Exception as e:
            raise ValueError(f"Invalid run_id: {run_id}") from e

        # Create execution task
        task = BenchmarkExecutionTask(
            run_id=run_id,
            data_api=self._data_api,
            task_api=self._task_api,
            prompt_builder_api=self._prompt_builder_api,
            llm_api=self._llm_api,
        )

        # Disconnect any previous task signals (shouldn't happen, but safe)
        self._disconnect_current_task()

        # Connect task signals to our class signals
        self._connect_task_signals(task)

        # Store reference and start in thread pool
        self._current_task = task
        self._current_run_id = run_id
        self._thread_pool.start(task)

        # Notify status change (should be True)
        self.benchmark_status_events.emit(self.is_running())

    @override
    def stop_execution(self) -> None:
        """Request graceful termination of current execution"""
        if not self.is_running():
            raise RuntimeError("No benchmark is currently running")

        self._current_task.stop()

    @override
    def is_running(self) -> bool:
        """Check if any benchmark is currently executing"""
        return self._current_task is not None and not self._current_task.is_stopped()

    @override
    def get_current_run_id(self) -> Optional[int]:
        """Get ID of currently executing run, if any"""
        return self._current_run_id

    @override
    def subscribe_to_benchmark_status_events(self, callback: Callable[[bool], None]) -> None:
        """Subscribe to execution status changes (running vs not running)"""
        self.benchmark_status_events.connect(callback)
        # Immediately notify of current status
        callback(self.is_running())

    @override
    def subscribe_to_benchmark_output_events(self, callback: Callable[[str], None]) -> None:
        """Subscribe to log/output messages from benchmark execution"""
        self.benchmark_output_events.connect(callback)

    @override
    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """Subscribe to progress updates"""
        self.benchmark_progress_events.connect(callback)


    def _connect_task_signals(self, task: BenchmarkExecutionTask) -> None:
        """Connect a task's signals to our class signals"""
        task.signals.status_changed.connect(self.benchmark_status_events)
        task.signals.log_message.connect(self.benchmark_output_events)
        task.signals.progress.connect(self.benchmark_progress_events)

    def _disconnect_current_task(self) -> None:
        """Disconnect signals from current task (if any)"""
        if self._current_task is None:
            return

        try:
            self._current_task.signals.status_changed.disconnect(self.benchmark_status_events)
            self._current_task.signals.log_message.disconnect(self.benchmark_output_events)
            self._current_task.signals.progress.disconnect(self.benchmark_progress_events)
        except TypeError:
            # Signals might not be connected, ignore
            pass
        finally:
            self._current_task = None
            self._current_run_id = None
