import logging
from typing import Callable, List, Optional

from ollama_llm_bench.core.controllers import ResultWidgetControllerApi
from ollama_llm_bench.core.interfaces import (
    BenchmarkFlowApi,
    BenchmarkTaskApi,
    DataApi,
    EventBus,
    ITableSerializer,
    LLMApi,
    ResultApi,
)
from ollama_llm_bench.core.models import AvgSummaryTableItem, SummaryTableItem

logger = logging.getLogger(__name__)


class ResultWidgetController(ResultWidgetControllerApi):

    def __init__(self,
                 *,
                 data_api: DataApi,
                 llm_api: LLMApi,
                 task_api: BenchmarkTaskApi,
                 benchmark_flow_api: BenchmarkFlowApi,
                 event_bus: EventBus,
                 result_api: ResultApi,
                 table_serializer: ITableSerializer,
                 ):
        super().__init__()
        self.data_api = data_api
        self.llm_api = llm_api
        self.task_api = task_api
        self.benchmark_flow_api = benchmark_flow_api
        self.event_bus = event_bus
        self.result_api = result_api
        self.table_serializer = table_serializer

        self._selected_run_id: Optional[int] = None
        self._avg_summary: list[AvgSummaryTableItem] = []
        self._detailed_summary: list[SummaryTableItem] = []

        self.event_bus.subscribe_to_run_id_changed(self._set_run_id)
        self.event_bus.subscribe_to_table_summary_data_changed(self._set_avg_summary)
        self.event_bus.subscribe_to_table_detailed_data_change(self._set_detailed_summary)
        self.event_bus.subscribe_to_background_thread_is_running(self._on_background_task_status_changed)

    def _on_background_task_status_changed(self, is_running: bool) -> None:
        if not is_running:
            try:
                runs = self.data_api.retrieve_benchmark_runs()
                if runs and len(runs) > 0:

                    self.event_bus.emit_run_ids_changed(runs_list)
            except Exception as e:
                logger.warning("failed to retrieve runs {}".format(e))
                self.event_bus.emit_run_ids_changed([])
            avg_summary = self._get_summary_data()
            detailed_summary = self._get_detailed_data()
            self.event_bus.emit_table_summary_data_changed(avg_summary)
            self.event_bus.emit_table_detailed_data_change(detailed_summary)

    def _set_run_id(self, run_id: Optional[int]) -> None:
        self._selected_run_id = run_id
        if run_id is None or run_id <= 0:
            logger.debug(f"No Run ID")
            self.event_bus.emit_table_summary_data_changed([])
            self.event_bus.emit_table_detailed_data_change([])
            self.event_bus.emit_global_event_msg("No Run ID")
            return

        try:
            run = self.data_api.retrieve_benchmark_run(run_id)
        except Exception as e:
            logger.warning(f"Failed to retrieve run {run_id}: {e}")
            self.event_bus.emit_table_summary_data_changed([])
            self.event_bus.emit_table_detailed_data_change([])
            self.event_bus.emit_global_event_msg("Failed to retrieve run {run_id}")
            return

        avg_summary = self._get_summary_data()
        detailed_summary = self._get_detailed_data()

        self.event_bus.emit_table_summary_data_changed(avg_summary)
        self.event_bus.emit_table_detailed_data_change(detailed_summary)

    def _set_avg_summary(self, summary: list[AvgSummaryTableItem]) -> None:
        value = summary or []
        self._avg_summary = value

    def _set_detailed_summary(self, detailed_summary: list[SummaryTableItem]) -> None:
        value = detailed_summary or []
        self._detailed_summary = value

    def handle_run_selection_change(self, run_id: Optional[int]) -> None:
        logger.debug('handle_run_selection_change')
        if run_id is None or run_id <= 0:
            logger.debug(f"No Run ID")
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_table_summary_data_changed([])
            self.event_bus.emit_table_detailed_data_change([])
            self.event_bus.emit_global_event_msg("No Run ID")
            return

        try:
            run = self.data_api.retrieve_benchmark_run(run_id)
        except Exception as e:
            logger.warning(f"Failed to retrieve run {run_id}: {e}")
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_table_summary_data_changed([])
            self.event_bus.emit_table_detailed_data_change([])
            self.event_bus.emit_global_event_msg("Failed to retrieve run {run_id}")
            return

        avg_summary = self._get_summary_data()
        detailed_summary = self._get_detailed_data()

        self.event_bus.emit_run_id_changed(run.run_id)
        self.event_bus.emit_table_summary_data_changed(avg_summary)
        self.event_bus.emit_table_detailed_data_change(detailed_summary)

    def handle_delete_click(self) -> None:
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
            runs = self.data_api.retrieve_benchmark_runs()
            if runs and len(runs) > 0:
                run = runs[-1]
                runs_list = [(r.run_id, r.timestamp) for r in runs]
                self.event_bus.emit_run_id_changed(run.run_id)
                self.event_bus.emit_run_ids_changed(runs_list)
            else:
                self.event_bus.emit_run_id_changed(None)
                self.event_bus.emit_run_ids_changed([])
        except Exception as e:
            logger.warning(f"Failed to retrieve runs: {e}")
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_run_ids_changed([])
            self.event_bus.emit_global_event_msg("Failed to retrieve runs")

    def _get_summary_data(self) -> list[AvgSummaryTableItem]:
        if self._selected_run_id is None or self._selected_run_id <= 0:
            logger.warning("Attempted to get summary data when no run is selected")
            return []

        try:
            summary = self.result_api.retrieve_avg_benchmark_results_for_run(self._selected_run_id)
            logger.info(
                f"Retrieved summary data for run ID {self._selected_run_id} "
                f"with {len(summary)} model summaries",
            )
            return summary
        except Exception as e:
            logger.error(f"Failed to retrieve summary data for run {self._selected_run_id}: {str(e)}")
            return []

    def _get_detailed_data(self) -> list[SummaryTableItem]:
        if self._selected_run_id is None or self._selected_run_id <= 0:
            logger.warning("Attempted to get detailed data when no run is selected")
            return []

        try:
            detailed = self.result_api.retrieve_detailed_benchmark_results_for_run(self._selected_run_id)
            logger.info(
                f"Retrieved detailed data for run ID {self._selected_run_id} "
                f"with {len(detailed)} task results",
            )
            return detailed
        except Exception as e:
            logger.error(f"Failed to retrieve detailed data for run {self._selected_run_id}: {str(e)}")
            return []

    def handle_summary_export_csv_click(self) -> None:
        logger.debug('handle_summary_export_csv_click')
        try:
            self.table_serializer.save_summary_as_csv(self._avg_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_summary_export_md_click(self) -> None:
        logger.debug('handle_summary_export_md_click')
        try:
            self.table_serializer.save_summary_as_md(self._avg_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_detailed_export_csv_click(self) -> None:
        logger.debug('handle_detailed_export_csv_click')
        try:
            self.table_serializer.save_details_as_csv(self._detailed_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_detailed_export_md_click(self) -> None:
        logger.debug('handle_detailed_export_md_click')
        try:
            self.table_serializer.save_details_as_md(self._detailed_summary)
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {str(e)}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def subscribe_to_runs_change(self, callback: Callable[[List[tuple[int, str]]], None]) -> None:
        logger.debug('subscribe_to_runs_change')
        self.event_bus.subscribe_to_run_ids_changed(callback)

    def subscribe_to_summary_data_change(self, callback: Callable[[List[AvgSummaryTableItem]], None]) -> None:
        logger.debug('subscribe_to_summary_data_change')
        self.event_bus.subscribe_to_table_summary_data_changed(callback)

    def subscribe_to_detailed_data_change(self, callback: Callable[[List[SummaryTableItem]], None]) -> None:
        logger.debug('subscribe_to_detailed_data_change')
        self.event_bus.subscribe_to_table_detailed_data_change(callback)

    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        logger.debug('subscribe_to_benchmark_status_change')
        self.event_bus.subscribe_to_background_thread_is_running(callback)
