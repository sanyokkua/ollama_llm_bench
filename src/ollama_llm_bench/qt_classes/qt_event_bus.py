import logging
from collections.abc import Callable
from typing import List, Optional, override

from PyQt6.QtCore import QObject, pyqtSignal

from ollama_llm_bench.core.interfaces import EventBus
from ollama_llm_bench.core.models import (
    AvgSummaryTableItem,
    ReporterStatusMsg, SummaryTableItem,
)
from ollama_llm_bench.qt_classes.meta_class import MetaQObjectABC

logger = logging.getLogger(__name__)


class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC):
    """
    Qt-based event bus implementation using pyqtSignal for cross-component communication.
    Facilitates decoupled interaction between UI and backend components.
    """

    _run_id_changed = pyqtSignal(int)
    _run_ids_changed = pyqtSignal(list)
    _models_test_changed = pyqtSignal(list)
    _models_judge_changed = pyqtSignal(str)
    _log_clean = pyqtSignal()
    _log_append = pyqtSignal(str)
    _table_summary_data_changed = pyqtSignal(list)
    _table_detailed_data_change = pyqtSignal(list)
    _background_thread_is_running = pyqtSignal(bool)
    _background_thread_progress_changed = pyqtSignal(object)
    _global_event_msg = pyqtSignal(str)

    def __init__(self) -> None:
        """
        Initialize the event bus with all required signals for application-wide communication.
        """
        super().__init__()

    @override
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        """
        Subscribe to changes in the currently active benchmark run ID.

        Args:
            callback: Function to call with the new run ID (or None).
        """
        logger.debug(f"subscribe_to_run_id_changed: {callback}")
        self._run_id_changed.connect(callback)

    @override
    def subscribe_to_run_ids_changed(self, callback: Callable[[list[tuple[int, str]]], None]):
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
    def subscribe_to_table_summary_data_changed(self, callback: Callable[[List[AvgSummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the summary results table data.

        Args:
            callback: Function to call with updated list of summary items.
        """
        logger.debug(f"subscribe_to_table_summary_data_changed: {callback}")
        self._table_summary_data_changed.connect(callback)

    @override
    def subscribe_to_table_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None:
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
    def emit_run_id_changed(self, value: Optional[int]) -> None:
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
    def emit_table_summary_data_changed(self, value: List[AvgSummaryTableItem]) -> None:
        """
        Broadcast updated summary table data.

        Args:
            value: List of AvgSummaryTableItem objects.
        """
        logger.debug(f"emit_table_summary_data_changed: {value}")
        self._table_summary_data_changed.emit(value)

    @override
    def emit_table_detailed_data_change(self, value: List[SummaryTableItem]) -> None:
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
