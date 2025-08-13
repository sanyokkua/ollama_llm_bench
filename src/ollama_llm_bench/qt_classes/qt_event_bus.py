from collections.abc import Callable
from typing import List

from PyQt6.QtCore import QObject, pyqtSignal

from ollama_llm_bench.core.interfaces import EventBus
from ollama_llm_bench.core.models import (
    AvgSummaryTableItem,
    NewRunWidgetStartEvent,
    ReporterStatusMsg,
    SummaryTableItem,
)
from ollama_llm_bench.qt_classes.meta_class import MetaQObjectABC


class QtEventBus(QObject, EventBus, metaclass=MetaQObjectABC):
    _benchmark_run_id_changed_events = pyqtSignal(int)
    _benchmark_is_running_events = pyqtSignal(bool)
    _benchmark_log_events = pyqtSignal(str)
    _benchmark_progress_events = pyqtSignal(ReporterStatusMsg)

    _new_run_btn_new_run_refresh_clicked = pyqtSignal()
    _new_run_btn_new_run_start_clicked = pyqtSignal(NewRunWidgetStartEvent)
    _new_run_btn_new_run_stop_clicked = pyqtSignal()

    _prev_run_btn_prev_run_refresh_clicked = pyqtSignal()
    _prev_run_btn_prev_run_start_clicked = pyqtSignal(int)
    _prev_run_btn_prev_run_stop_clicked = pyqtSignal()

    _result_run_id_changed = pyqtSignal(int)
    _result_btn_export_csv_summary_clicked = pyqtSignal()
    _result_btn_export_md_summary_clicked = pyqtSignal()
    _result_btn_export_csv_detailed_clicked = pyqtSignal()
    _result_btn_export_md_detailed_clicked = pyqtSignal()
    _result_btn_delete_run_clicked = pyqtSignal()

    _app_models_changed = pyqtSignal(list)
    _app_runs_changed = pyqtSignal(list)
    _app_current_run_summary_data_changed = pyqtSignal(list)
    _app_current_run_detailed_data_changed = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()

    def subscribe_to_benchmark_run_id_changed_events(self, callback: Callable[[int], None]) -> None:
        self._benchmark_run_id_changed_events.connect(callback)

    def subscribe_to_benchmark_is_running_events(self, callback: Callable[[bool], None]) -> None:
        self._benchmark_is_running_events.connect(callback)

    def subscribe_to_benchmark_log_events(self, callback: Callable[[str], None]) -> None:
        self._benchmark_log_events.connect(callback)

    def subscribe_to_benchmark_progress_events(self, callback: Callable[[ReporterStatusMsg], None]) -> None:
        self._benchmark_progress_events.connect(callback)

    def subscribe_to_new_run_btn_new_run_refresh_clicked(self, callback: Callable[[], None]) -> None:
        self._new_run_btn_new_run_refresh_clicked.connect(callback)

    def subscribe_to_new_run_btn_new_run_start_clicked(self,
                                                       callback: Callable[[NewRunWidgetStartEvent], None],
                                                       ) -> None:
        self._new_run_btn_new_run_start_clicked.connect(callback)

    def subscribe_to_new_run_btn_new_run_stop_clicked(self, callback: Callable[[], None]) -> None:
        self._new_run_btn_new_run_stop_clicked.connect(callback)

    def subscribe_to_prev_run_btn_prev_run_refresh_clicked(self, callback: Callable[[], None]) -> None:
        self._prev_run_btn_prev_run_refresh_clicked.connect(callback)

    def subscribe_to_prev_run_btn_prev_run_start_clicked(self, callback: Callable[[int], None]) -> None:
        self._prev_run_btn_prev_run_start_clicked.connect(callback)

    def subscribe_to_prev_run_btn_prev_run_stop_clicked(self, callback: Callable[[], None]) -> None:
        self._prev_run_btn_prev_run_stop_clicked.connect(callback)

    def subscribe_to_prev_run_run_id_changed(self, callback: Callable[[int], None]) -> None:
        self._benchmark_run_id_changed_events.connect(callback)

    def subscribe_to_result_run_id_changed(self, callback: Callable[[int], None]) -> None:
        self._benchmark_run_id_changed_events.connect(callback)

    def subscribe_to_result_btn_export_csv_summary_clicked(self, callback: Callable[[], None]) -> None:
        self._result_btn_export_csv_summary_clicked.connect(callback)

    def subscribe_to_result_btn_export_md_summary_clicked(self, callback: Callable[[], None]) -> None:
        self._result_btn_export_md_summary_clicked.connect(callback)

    def subscribe_to_result_btn_export_csv_detailed_clicked(self, callback: Callable[[], None]) -> None:
        self._result_btn_export_csv_detailed_clicked.connect(callback)

    def subscribe_to_result_btn_export_md_detailed_clicked(self, callback: Callable[[], None]) -> None:
        self._result_btn_export_md_detailed_clicked.connect(callback)

    def subscribe_to_result_btn_delete_run_clicked(self, callback: Callable[[], None]) -> None:
        self._result_btn_delete_run_clicked.connect(callback)

    def subscribe_app_runs_changed(self, callback: Callable[[list[tuple[int, str]]], None]):
        self._app_runs_changed.connect(callback)

    def subscribe_app_current_run_summary_data_changed(self, callback: Callable[[List[AvgSummaryTableItem]], None]):
        self._app_current_run_summary_data_changed.connect(callback)

    def subscribe_app_current_run_detailed_data_changed(self, callback: Callable[[List[SummaryTableItem]], None]):
        self._app_current_run_detailed_data_changed.connect(callback)

    def subscribe_to_app_models_changed(self, callback: Callable[[list], None]):
        self._app_models_changed.connect(callback)

    def emit_benchmark_run_id_changed_events(self, value: int) -> None:
        self._benchmark_run_id_changed_events.emit(value)

    def emit_benchmark_is_running_events(self, value: bool) -> None:
        self._benchmark_is_running_events.emit(value)

    def emit_benchmark_log_events(self, value: str) -> None:
        self._benchmark_log_events.emit(value)

    def emit_benchmark_progress_events(self, value: ReporterStatusMsg) -> None:
        self._benchmark_progress_events.emit(value)

    def emit_new_run_btn_new_run_refresh_clicked(self) -> None:
        self._new_run_btn_new_run_refresh_clicked.emit()

    def emit_new_run_btn_new_run_start_clicked(self, value: NewRunWidgetStartEvent) -> None:
        self._new_run_btn_new_run_start_clicked.emit(value)

    def emit_new_run_btn_new_run_stop_clicked(self) -> None:
        self._new_run_btn_new_run_stop_clicked.emit()

    def emit_prev_run_btn_prev_run_refresh_clicked(self) -> None:
        self._prev_run_btn_prev_run_refresh_clicked.emit()

    def emit_prev_run_btn_prev_run_start_clicked(self, value: int) -> None:
        self._prev_run_btn_prev_run_start_clicked.emit(value)

    def emit_prev_run_btn_prev_run_stop_clicked(self) -> None:
        self._prev_run_btn_prev_run_stop_clicked.emit()

    def emit_result_run_id_changed(self, value: int) -> None:
        self._result_run_id_changed.emit(value)

    def emit_result_btn_export_csv_summary_clicked(self) -> None:
        self._result_btn_export_csv_summary_clicked.emit()

    def emit_result_btn_export_md_summary_clicked(self) -> None:
        self._result_btn_export_md_summary_clicked.emit()

    def emit_result_btn_export_csv_detailed_clicked(self) -> None:
        self._result_btn_export_csv_detailed_clicked.emit()

    def emit_result_btn_export_md_detailed_clicked(self) -> None:
        self._result_btn_export_md_detailed_clicked.emit()

    def emit_result_btn_delete_run_clicked(self) -> None:
        self._result_btn_delete_run_clicked.emit()

    def emit_app_runs_changed(self, value: list[tuple[int, str]]):
        self._app_runs_changed.emit(value)

    def emit_app_current_run_summary_data_changed(self, value: List[AvgSummaryTableItem]):
        self._app_current_run_summary_data_changed.emit(value)

    def emit_app_current_run_detailed_data_changed(self, value: List[SummaryTableItem]):
        self._app_current_run_detailed_data_changed.emit(value)

    def emit_app_models_changed(self, value: list[str]):
        self._app_models_changed.emit(value)
