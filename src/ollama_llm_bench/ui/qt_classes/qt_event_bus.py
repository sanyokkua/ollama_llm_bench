import logging
from collections.abc import Callable
from typing import override

from PySide6.QtCore import QObject, Signal

from ollama_llm_bench.backend.core.interfaces import EventBus
from ollama_llm_bench.backend.core.models import (
    AppSettingsChangedEvent,
    AvgSummaryTableItem,
    BenchmarkFinishedEvent,
    BenchmarkPausedEvent,
    BenchmarkResumedEvent,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeEvalRetryEvent,
    JudgeEvalStartedEvent,
    JudgeStartedEvent,
    JudgeSummaryEvent,
    ModelSwitchEvent,
    ModeSwitchEvent,
    PerfAnalysisEvent,
    PreviousRunsRefreshedEvent,
    ProgressUpdateEvent,
    ProviderHealthCheckEvent,
    ProviderRegistryReloadedEvent,
    ProviderSwitchEvent,
    ReporterStatusMsg,
    StreamingChunkEvent,
    SummaryTableItem,
    TaskCompletedEvent,
    TaskRetryEvent,
    TaskSwitchEvent,
)
from ollama_llm_bench.ui.qt_classes.meta_class import MetaQObjectABC

logger = logging.getLogger(__name__)


class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC):
    """
    Qt-based event bus implementation using Signal for cross-component communication.
    Facilitates decoupled interaction between UI and backend components.
    """

    _run_id_changed = Signal(int)
    _run_ids_changed = Signal(list)
    _models_test_changed = Signal(list)
    _models_judge_changed = Signal(str)
    _log_clean = Signal()
    _log_append = Signal(str)
    _table_summary_data_changed = Signal(list)
    _table_detailed_data_change = Signal(list)
    _background_thread_is_running = Signal(bool)
    _background_thread_progress_changed = Signal(object)
    _global_event_msg = Signal(str)
    _benchmark_started = Signal(BenchmarkStartedEvent)
    _benchmark_paused = Signal(BenchmarkPausedEvent)
    _benchmark_resumed = Signal(BenchmarkResumedEvent)
    _benchmark_stopped = Signal(BenchmarkStoppedEvent)
    _benchmark_finished = Signal(BenchmarkFinishedEvent)
    _provider_switch = Signal(ProviderSwitchEvent)
    _provider_health_check = Signal(ProviderHealthCheckEvent)
    _model_switch = Signal(ModelSwitchEvent)
    _task_switch = Signal(TaskSwitchEvent)
    _task_retry = Signal(TaskRetryEvent)
    _mode_switch = Signal(ModeSwitchEvent)
    _task_completed = Signal(TaskCompletedEvent)
    _judge_started = Signal(JudgeStartedEvent)
    _judge_completed = Signal(JudgeCompletedEvent)
    _judge_eval_started = Signal(JudgeEvalStartedEvent)
    _judge_eval_retry = Signal(JudgeEvalRetryEvent)
    _streaming_chunk = Signal(StreamingChunkEvent)
    _inference_started = Signal(InferenceStartedEvent)
    _progress_update = Signal(ProgressUpdateEvent)
    _judge_summary = Signal(JudgeSummaryEvent)
    _perf_analysis = Signal(PerfAnalysisEvent)
    _app_settings_changed = Signal(AppSettingsChangedEvent)
    _provider_registry_reloaded = Signal(ProviderRegistryReloadedEvent)
    _previous_runs_refreshed = Signal(PreviousRunsRefreshedEvent)

    def __init__(self) -> None:
        """
        Initialize the event bus with all required signals for application-wide communication.
        """
        super().__init__()

    @override
    def subscribe_to_run_id_changed(self, callback: Callable[[int | None], None]) -> None:
        """
        Subscribe to changes in the currently active benchmark run ID.

        Args:
            callback: Function to call with the new run ID (or None).
        """
        logger.debug(f"subscribe_to_run_id_changed: {callback}")
        self._run_id_changed.connect(callback)

    @override
    def subscribe_to_run_ids_changed(self, callback: Callable[[list[tuple[int, str]]], None]) -> None:
        """
        Subscribe to changes in the list of available benchmark runs.

        Args:
            callback: Function to call with updated list of (run_id, run_name) tuples.
        """
        logger.debug(f"subscribe_to_run_ids_changed: {callback}")
        self._run_ids_changed.connect(callback)

    @override
    def subscribe_to_models_test_changed(self, callback: Callable[[list[str]], None]) -> None:
        """
        Subscribe to changes in the list of models selected for testing.

        Args:
            callback: Function to call with updated list of model names.
        """
        logger.debug(f"subscribe_to_models_test_changed: {callback}")
        self._models_test_changed.connect(callback)

    @override
    def subscribe_to_models_judge_changed(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to changes in the judge model selection.

        Args:
            callback: Function to call with the new judge model name.
        """
        logger.debug(f"subscribe_to_models_judge_changed: {callback}")
        self._models_judge_changed.connect(callback)

    @override
    def subscribe_to_log_clean(self, callback: Callable[[], None]) -> None:
        """
        Subscribe to log clear events.

        Args:
            callback: Function to invoke when logs should be cleared.
        """
        logger.debug(f"subscribe_to_log_clean: {callback}")
        self._log_clean.connect(callback)

    @override
    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to log append events.

        Args:
            callback: Function to invoke with new log messages.
        """
        logger.debug(f"subscribe_to_log_append: {callback}")
        self._log_append.connect(callback)

    @override
    def subscribe_to_table_summary_data_changed(self, callback: Callable[[list[AvgSummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the summary results table data.

        Args:
            callback: Function to call with updated list of summary items.
        """
        logger.debug(f"subscribe_to_table_summary_data_changed: {callback}")
        self._table_summary_data_changed.connect(callback)

    @override
    def subscribe_to_table_detailed_data_change(self, callback: Callable[[list[SummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the detailed results table data.

        Args:
            callback: Function to call with updated list of detailed items.
        """
        logger.debug(f"subscribe_to_table_detailed_data_changed: {callback}")
        self._table_detailed_data_change.connect(callback)

    @override
    def subscribe_to_background_thread_is_running(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to execution status changes of background tasks.

        Args:
            callback: Function to call with True (running) or False (idle).
        """
        logger.debug(f"subscribe_to_background_thread_is_running: {callback}")
        self._background_thread_is_running.connect(callback)

    @override
    def subscribe_to_background_thread_progress(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        """
        Subscribe to progress updates from background execution threads.

        Args:
            callback: Function to call with ReporterStatusMsg objects.
        """
        self._background_thread_progress_changed.connect(callback)

    @override
    def subscribe_to_global_event_msg(self, callback: Callable[[str], None]) -> None:
        """
        Subscribe to global application event messages.

        Args:
            callback: Function to call with event message strings.
        """
        logger.debug(f"subscribe_to_global_event_msg: {callback}")
        self._global_event_msg.connect(callback)

    @override
    def emit_run_id_changed(self, value: int | None) -> None:
        """
        Broadcast a change in the active benchmark run ID.

        Args:
            value: New run ID, or None to indicate no selection.
        """
        logger.debug(f"emit_run_id_changed: {value}")
        self._run_id_changed.emit(value or -1)

    @override
    def emit_run_ids_changed(self, value: list[tuple[int, str]]) -> None:
        """
        Broadcast a change in the list of available benchmark runs.

        Args:
            value: List of (run_id, run_name) tuples.
        """
        logger.debug(f"emit_run_ids_changed: {value}")
        self._run_ids_changed.emit(value)

    @override
    def emit_models_test_changed(self, value: list[str]) -> None:
        """
        Broadcast a change in the list of models selected for testing.

        Args:
            value: List of model names.
        """
        logger.debug(f"emit_models_test_changed: {value}")
        self._models_test_changed.emit(value)

    @override
    def emit_models_judge_changed(self, value: str) -> None:
        """
        Broadcast a change in the selected judge model.

        Args:
            value: Name of the judge model.
        """
        logger.debug(f"emit_models_judge_changed: {value}")
        self._models_judge_changed.emit(value)

    @override
    def emit_log_clean(self) -> None:
        """
        Broadcast a request to clear all log content.
        """
        logger.debug(f"emit_log_clean: {self}")
        self._log_clean.emit()

    @override
    def emit_log_append(self, value: str) -> None:
        """
        Broadcast a new log message to be displayed.

        Args:
            value: Log message to append.
        """
        logger.debug(f"emit_log_append: {value}")
        self._log_append.emit(value)

    @override
    def emit_table_summary_data_changed(self, value: list[AvgSummaryTableItem]) -> None:
        """
        Broadcast updated summary table data.

        Args:
            value: List of AvgSummaryTableItem objects.
        """
        logger.debug(f"emit_table_summary_data_changed: {value}")
        self._table_summary_data_changed.emit(value)

    @override
    def emit_table_detailed_data_change(self, value: list[SummaryTableItem]) -> None:
        """
        Broadcast updated detailed table data.

        Args:
            value: List of SummaryTableItem objects.
        """
        logger.debug(f"emit_table_detailed_data_changed: {value}")
        self._table_detailed_data_change.emit(value)

    @override
    def emit_background_thread_is_running(self, value: bool) -> None:
        """
        Broadcast the current execution state of background tasks.

        Args:
            value: True if background thread is running, False otherwise.
        """
        logger.debug(f"emit_background_thread_is_running: {value}")
        self._background_thread_is_running.emit(value)

    @override
    def emit_background_thread_progress(self, value: ReporterStatusMsg) -> None:
        """
        Broadcast a progress update from background execution.

        Args:
            value: ReporterStatusMsg containing progress details.
        """
        logger.debug(f"emit_background_thread_progress: {value}")
        self._background_thread_progress_changed.emit(value)

    @override
    def emit_global_event_msg(self, value: str) -> None:
        """
        Broadcast a general application event message.

        Args:
            value: Message string to broadcast.
        """
        logger.debug(f"emit_global_event_msg: {value}")
        self._global_event_msg.emit(value)

    @override
    def subscribe_to_benchmark_started(self, callback: Callable[[BenchmarkStartedEvent], None]) -> None:
        self._benchmark_started.connect(callback)

    @override
    def emit_benchmark_started(self, event: BenchmarkStartedEvent) -> None:
        self._benchmark_started.emit(event)

    @override
    def subscribe_to_benchmark_paused(self, callback: Callable[[BenchmarkPausedEvent], None]) -> None:
        self._benchmark_paused.connect(callback)

    @override
    def emit_benchmark_paused(self, event: BenchmarkPausedEvent) -> None:
        self._benchmark_paused.emit(event)

    @override
    def subscribe_to_benchmark_resumed(self, callback: Callable[[BenchmarkResumedEvent], None]) -> None:
        self._benchmark_resumed.connect(callback)

    @override
    def emit_benchmark_resumed(self, event: BenchmarkResumedEvent) -> None:
        self._benchmark_resumed.emit(event)

    @override
    def subscribe_to_benchmark_stopped(self, callback: Callable[[BenchmarkStoppedEvent], None]) -> None:
        self._benchmark_stopped.connect(callback)

    @override
    def emit_benchmark_stopped(self, event: BenchmarkStoppedEvent) -> None:
        self._benchmark_stopped.emit(event)

    @override
    def subscribe_to_benchmark_finished(self, callback: Callable[[BenchmarkFinishedEvent], None]) -> None:
        self._benchmark_finished.connect(callback)

    @override
    def emit_benchmark_finished(self, event: BenchmarkFinishedEvent) -> None:
        self._benchmark_finished.emit(event)

    @override
    def subscribe_to_provider_switch(self, callback: Callable[[ProviderSwitchEvent], None]) -> None:
        self._provider_switch.connect(callback)

    @override
    def emit_provider_switch(self, event: ProviderSwitchEvent) -> None:
        self._provider_switch.emit(event)

    @override
    def subscribe_to_provider_health_check(self, callback: Callable[[ProviderHealthCheckEvent], None]) -> None:
        self._provider_health_check.connect(callback)

    @override
    def emit_provider_health_check(self, event: ProviderHealthCheckEvent) -> None:
        self._provider_health_check.emit(event)

    @override
    def subscribe_to_model_switch(self, callback: Callable[[ModelSwitchEvent], None]) -> None:
        self._model_switch.connect(callback)

    @override
    def emit_model_switch(self, event: ModelSwitchEvent) -> None:
        self._model_switch.emit(event)

    @override
    def subscribe_to_task_switch(self, callback: Callable[[TaskSwitchEvent], None]) -> None:
        self._task_switch.connect(callback)

    @override
    def emit_task_switch(self, event: TaskSwitchEvent) -> None:
        self._task_switch.emit(event)

    @override
    def subscribe_to_task_retry(self, callback: Callable[[TaskRetryEvent], None]) -> None:
        self._task_retry.connect(callback)

    @override
    def emit_task_retry(self, event: TaskRetryEvent) -> None:
        self._task_retry.emit(event)

    @override
    def subscribe_to_mode_switch(self, callback: Callable[[ModeSwitchEvent], None]) -> None:
        self._mode_switch.connect(callback)

    @override
    def emit_mode_switch(self, event: ModeSwitchEvent) -> None:
        self._mode_switch.emit(event)

    @override
    def subscribe_to_task_completed(self, callback: Callable[[TaskCompletedEvent], None]) -> None:
        self._task_completed.connect(callback)

    @override
    def emit_task_completed(self, event: TaskCompletedEvent) -> None:
        self._task_completed.emit(event)

    @override
    def subscribe_to_judge_started(self, callback: Callable[[JudgeStartedEvent], None]) -> None:
        self._judge_started.connect(callback)

    @override
    def emit_judge_started(self, event: JudgeStartedEvent) -> None:
        self._judge_started.emit(event)

    @override
    def subscribe_to_judge_completed(self, callback: Callable[[JudgeCompletedEvent], None]) -> None:
        self._judge_completed.connect(callback)

    @override
    def emit_judge_completed(self, event: JudgeCompletedEvent) -> None:
        self._judge_completed.emit(event)

    @override
    def subscribe_to_judge_eval_started(self, callback: Callable[[JudgeEvalStartedEvent], None]) -> None:
        self._judge_eval_started.connect(callback)

    @override
    def emit_judge_eval_started(self, event: JudgeEvalStartedEvent) -> None:
        self._judge_eval_started.emit(event)

    @override
    def subscribe_to_judge_eval_retry(self, callback: Callable[[JudgeEvalRetryEvent], None]) -> None:
        self._judge_eval_retry.connect(callback)

    @override
    def emit_judge_eval_retry(self, event: JudgeEvalRetryEvent) -> None:
        self._judge_eval_retry.emit(event)

    @override
    def subscribe_to_streaming_chunk(self, callback: Callable[[StreamingChunkEvent], None]) -> None:
        self._streaming_chunk.connect(callback)

    @override
    def emit_streaming_chunk(self, event: StreamingChunkEvent) -> None:
        self._streaming_chunk.emit(event)

    @override
    def subscribe_to_inference_started(self, callback: Callable[[InferenceStartedEvent], None]) -> None:
        self._inference_started.connect(callback)

    @override
    def emit_inference_started(self, event: InferenceStartedEvent) -> None:
        self._inference_started.emit(event)

    @override
    def subscribe_to_progress_update(self, callback: Callable[[ProgressUpdateEvent], None]) -> None:
        self._progress_update.connect(callback)

    @override
    def emit_progress_update(self, event: ProgressUpdateEvent) -> None:
        self._progress_update.emit(event)

    @override
    def subscribe_to_judge_summary(self, callback: Callable[[JudgeSummaryEvent], None]) -> None:
        self._judge_summary.connect(callback)

    @override
    def emit_judge_summary(self, event: JudgeSummaryEvent) -> None:
        self._judge_summary.emit(event)

    @override
    def subscribe_to_perf_analysis(self, callback: Callable[[PerfAnalysisEvent], None]) -> None:
        self._perf_analysis.connect(callback)

    @override
    def emit_perf_analysis(self, event: PerfAnalysisEvent) -> None:
        self._perf_analysis.emit(event)

    @override
    def subscribe_to_app_settings_changed(self, callback: Callable[[AppSettingsChangedEvent], None]) -> None:
        self._app_settings_changed.connect(callback)

    @override
    def emit_app_settings_changed(self, event: AppSettingsChangedEvent) -> None:
        self._app_settings_changed.emit(event)

    @override
    def subscribe_to_provider_registry_reloaded(
        self, callback: Callable[[ProviderRegistryReloadedEvent], None]
    ) -> None:
        self._provider_registry_reloaded.connect(callback)

    @override
    def emit_provider_registry_reloaded(self, event: ProviderRegistryReloadedEvent) -> None:
        self._provider_registry_reloaded.emit(event)

    @override
    def subscribe_to_previous_runs_refreshed(self, callback: Callable[[PreviousRunsRefreshedEvent], None]) -> None:
        self._previous_runs_refreshed.connect(callback)

    @override
    def emit_previous_runs_refreshed(self, event: PreviousRunsRefreshedEvent) -> None:
        self._previous_runs_refreshed.emit(event)
