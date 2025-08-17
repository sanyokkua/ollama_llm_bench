import logging
from typing import Callable, List, Optional

from ollama_llm_bench.core.interfaces import (
    DataApi,
    EventBus,
    ITableSerializer,
)
from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem
from ollama_llm_bench.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.utils.run_utils import get_benchmark_runs

logger = logging.getLogger(__name__)


class ResultWidgetController(ResultWidgetControllerApi):
    """
    Controller implementation for managing the 'Results' widget.
    Handles user interactions for viewing, exporting, and deleting benchmark results.
    """

    def __init__(self,
                 *,
                 data_api: DataApi,
                 event_bus: EventBus,
                 table_serializer: ITableSerializer,
                 ):
        """
        Initialize the result widget controller.

        Args:
            data_api: Interface for accessing and deleting benchmark data.
            event_bus: Event bus for subscribing to and emitting UI events.
            table_serializer: Service for exporting results to CSV and Markdown formats.
        """
        super().__init__()
        self.data_api = data_api
        self.event_bus = event_bus
        self.table_serializer = table_serializer

        self._selected_run_id: Optional[int] = None
        self._avg_summary: list[AvgSummaryTableItem] = []
        self._detailed_summary: list[SummaryTableItem] = []

        self.event_bus.subscribe_to_run_id_changed(self._set_run_id)
        self.event_bus.subscribe_to_table_summary_data_changed(self._set_avg_summary)
        self.event_bus.subscribe_to_table_detailed_data_change(self._set_detailed_summary)

    def _set_run_id(self, run_id: Optional[int]) -> None:
        """
        Update the currently selected run ID.

        Args:
            run_id: Newly selected run ID, or None.
        """
        self._selected_run_id = run_id

    def _set_avg_summary(self, summary: list[AvgSummaryTableItem]) -> None:
        """
        Update the cached average summary data.

        Args:
            summary: New average summary items, or None to clear.
        """
        value = summary or []
        self._avg_summary = value

    def _set_detailed_summary(self, detailed_summary: list[SummaryTableItem]) -> None:
        """
        Update the cached detailed summary data.

        Args:
            detailed_summary: New detailed summary items, or None to clear.
        """
        value = detailed_summary or []
        self._detailed_summary = value

    def handle_run_selection_change(self, run_id: Optional[int]) -> None:
        """
        Handle user selection of a different benchmark run.

        Args:
            run_id: Newly selected run ID, or None.
        """
        logger.debug('handle_run_selection_change')
        self.event_bus.emit_run_id_changed(run_id)

    def handle_delete_click(self, _) -> None:
        """
        Handle user request to delete the currently selected benchmark run.

        Args:
            _: Ignored event parameter.
        """
        logger.debug('handle_delete_click')
        if self._selected_run_id is None or self._selected_run_id <= 0:
            logger.debug(f"No Run ID")
            self.event_bus.emit_global_event_msg("No Run ID selected to Delete")
            return
        try:
            self.data_api.delete_benchmark_run(self._selected_run_id)
            logger.debug(f"Deleted run {self._selected_run_id}")
        except Exception as e:
            logger.warning(f"Failed to delete run {self._selected_run_id}: {e}")
            self.event_bus.emit_global_event_msg("Failed to delete run {self._selected_run_id}")
        self._set_avg_summary([])
        self._set_detailed_summary([])
        try:
            runs_list = get_benchmark_runs(self.data_api)
            if runs_list and len(runs_list) > 0:
                run = runs_list[0]
                self.event_bus.emit_run_id_changed(run[0])
                self.event_bus.emit_run_ids_changed(runs_list)
            else:
                self.event_bus.emit_run_id_changed(None)
                self.event_bus.emit_run_ids_changed([])
        except Exception as e:
            logger.warning(f"Failed to retrieve runs: {e}")
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_run_ids_changed([])
            self.event_bus.emit_global_event_msg("Failed to retrieve runs")

    def handle_summary_export_csv_click(self, _) -> None:
        """
        Handle user request to export summary results to CSV.

        Args:
            _: Ignored event parameter.
        """
        logger.debug('handle_summary_export_csv_click')
        try:
            self.table_serializer.save_summary_as_csv(self._avg_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_summary_export_md_click(self, _) -> None:
        """
        Handle user request to export summary results to Markdown.

        Args:
            _: Ignored event parameter.
        """
        logger.debug('handle_summary_export_md_click')
        try:
            self.table_serializer.save_summary_as_md(self._avg_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_detailed_export_csv_click(self, _) -> None:
        """
        Handle user request to export detailed results to CSV.

        Args:
            _: Ignored event parameter.
        """
        logger.debug('handle_detailed_export_csv_click')
        try:
            self.table_serializer.save_details_as_csv(self._detailed_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_detailed_export_md_click(self, _) -> None:
        """
        Handle user request to export detailed results to Markdown.

        Args:
            _: Ignored event parameter.
        """
        logger.debug('handle_detailed_export_md_click')
        try:
            self.table_serializer.save_details_as_md(self._detailed_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def subscribe_to_runs_change(self, callback: Callable[[List[tuple[int, str]]], None]) -> None:
        """
        Subscribe to changes in the list of available benchmark runs.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """
        logger.debug('subscribe_to_runs_change')
        self.event_bus.subscribe_to_run_ids_changed(callback)

    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        """
        Subscribe to changes in the currently selected run ID.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """
        logger.debug('subscribe_to_run_id_changed')
        self.event_bus.subscribe_to_run_id_changed(callback)

    def subscribe_to_summary_data_change(self, callback: Callable[[List[AvgSummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the summary results data.

        Args:
            callback: Function to invoke with updated average summary items.
        """
        logger.debug('subscribe_to_summary_data_change')
        self.event_bus.subscribe_to_table_summary_data_changed(callback)

    def subscribe_to_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the detailed results data.

        Args:
            callback: Function to invoke with updated detailed summary items.
        """
        logger.debug('subscribe_to_detailed_data_change')
        self.event_bus.subscribe_to_table_detailed_data_change(callback)

    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to changes in benchmark execution status.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """
        logger.debug('subscribe_to_benchmark_status_change')
        self.event_bus.subscribe_to_background_thread_is_running(callback)
