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
    _run_id_changed = pyqtSignal(int)
    _run_ids_changed = pyqtSignal(list)
    _models_test_changed = pyqtSignal(list)
    _models_judge_changed = pyqtSignal(str)
    _log_clean = pyqtSignal()  # (
    _log_append = pyqtSignal(str)
    _table_summary_data_changed = pyqtSignal(list)
    _table_detailed_data_change = pyqtSignal(list)
    _background_thread_is_running = pyqtSignal(bool)
    _background_thread_progress_changed = pyqtSignal(object)
    _global_event_msg = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()

    @override
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        logger.debug(f"subscribe_to_run_id_changed: {callback}")
        self._run_id_changed.connect(callback)

    @override
    def subscribe_to_run_ids_changed(self, callback: Callable[[list[tuple[int, str]]], None]):
        logger.debug(f"subscribe_to_run_ids_changed: {callback}")
        self._run_ids_changed.connect(callback)

    @override
    def subscribe_to_models_test_changed(self, callback: Callable[[list[str]], None]) -> None:
        logger.debug(f"subscribe_to_models_test_changed: {callback}")
        self._models_test_changed.connect(callback)

    @override
    def subscribe_to_models_judge_changed(self, callback: Callable[[str], None]) -> None:
        logger.debug(f"subscribe_to_models_judge_changed: {callback}")
        self._models_judge_changed.connect(callback)

    @override
    def subscribe_to_log_clean(self, callback: Callable[[], None]) -> None:
        logger.debug(f"subscribe_to_log_clean: {callback}")
        self._log_clean.connect(callback)

    @override
    def subscribe_to_log_append(self, callback: Callable[[str], None]) -> None:
        logger.debug(f"subscribe_to_log_append: {callback}")
        self._log_append.connect(callback)

    @override
    def subscribe_to_table_summary_data_changed(self, callback: Callable[[List[AvgSummaryTableItem]], None]) -> None:
        logger.debug(f"subscribe_to_table_summary_data_changed: {callback}")
        self._table_summary_data_changed.connect(callback)

    @override
    def subscribe_to_table_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None:
        logger.debug(f"subscribe_to_table_detailed_data_changed: {callback}")
        self._table_detailed_data_change.connect(callback)

    @override
    def subscribe_to_background_thread_is_running(self, callback: Callable[[bool], None]) -> None:
        logger.debug(f"subscribe_to_background_thread_is_running: {callback}")
        self._background_thread_is_running.connect(callback)

    @override
    def subscribe_to_background_thread_progress(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        self._background_thread_progress_changed.connect(callback)

    @override
    def subscribe_to_global_event_msg(self, callback: Callable[[str], None]) -> None:
        logger.debug(f"subscribe_to_global_event_msg: {callback}")
        self._global_event_msg.connect(callback)

    @override
    def emit_run_id_changed(self, value: Optional[int]) -> None:
        logger.debug(f"emit_run_id_changed: {value}")
        self._run_id_changed.emit(value)

    @override
    def emit_run_ids_changed(self, value: list[tuple[int]]) -> None:
        logger.debug(f"emit_run_ids_changed: {value}")
        self._run_ids_changed.emit(value)

    @override
    def emit_models_test_changed(self, value: list[str]) -> None:
        logger.debug(f"emit_models_test_changed: {value}")
        self._models_test_changed.emit(value)

    @override
    def emit_models_judge_changed(self, value: str) -> None:
        logger.debug(f"emit_models_judge_changed: {value}")
        self._models_judge_changed.emit(value)

    @override
    def emit_log_clean(self) -> None:
        logger.debug(f"emit_log_clean: {self}")
        self._log_clean.emit()

    @override
    def emit_log_append(self, value: str) -> None:
        logger.debug(f"emit_log_append: {value}")
        self._log_append.emit(value)

    @override
    def emit_table_summary_data_changed(self, value: List[AvgSummaryTableItem]) -> None:
        logger.debug(f"emit_table_summary_data_changed: {value}")
        self._table_summary_data_changed.emit(value)

    @override
    def emit_table_detailed_data_change(self, value: List[SummaryTableItem]) -> None:
        logger.debug(f"emit_table_detailed_data_changed: {value}")
        self._table_detailed_data_change.emit(value)

    @override
    def emit_background_thread_is_running(self, value: bool) -> None:
        logger.debug(f"emit_background_thread_is_running: {value}")
        self._background_thread_is_running.emit(value)

    @override
    def emit_background_thread_progress(self, value: ReporterStatusMsg) -> None:
        logger.debug(f"emit_background_thread_progress: {value}")
        self._background_thread_progress_changed.emit(value)

    @override
    def emit_global_event_msg(self, value: str) -> None:
        logger.debug(f"emit_global_event_msg: {value}")
        self._global_event_msg.emit(value)
