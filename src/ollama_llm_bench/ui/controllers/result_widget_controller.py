import logging
from collections.abc import Callable
from pathlib import Path
from typing import override

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EventBus,
    ITableSerializer,
)
from ollama_llm_bench.backend.core.models import (
    AvgSummaryTableItem,
    BenchmarkResult,
    BenchmarkRun,
    JudgeSummaryEvent,
    PerfAnalysisEvent,
    SummaryTableItem,
)
from ollama_llm_bench.backend.core.ui_controllers import ResultWidgetControllerApi
from ollama_llm_bench.backend.utils.run_utils import get_benchmark_runs

logger = logging.getLogger(__name__)


class ResultWidgetController(ResultWidgetControllerApi):
    """
    Controller implementation for managing the 'Results' widget.
    Handles user interactions for viewing, exporting, and deleting benchmark results.
    """

    def __init__(
        self,
        *,
        data_api: DataApi,
        event_bus: EventBus,
        table_serializer: ITableSerializer,
        app_settings_service: AppSettingsServiceApi,
    ):
        """
        Initialize the result widget controller.

        Args:
            data_api: Interface for accessing and deleting benchmark data.
            event_bus: Event bus for subscribing to and emitting UI events.
            table_serializer: Service for exporting results to CSV and Markdown formats.
            app_settings_service: KV-store service for persisting user preferences.
        """
        super().__init__()
        self.data_api = data_api
        self.event_bus = event_bus
        self.table_serializer = table_serializer
        self._app_settings_service = app_settings_service

        self._selected_run_id: int | None = None
        self._avg_summary: list[AvgSummaryTableItem] = []
        self._detailed_summary: list[SummaryTableItem] = []
        self._full_results_cache: dict[str, BenchmarkResult] = {}
        self._chart_data_callbacks: list[Callable[[BenchmarkRun | None, list[BenchmarkResult]], None]] = []

        self.event_bus.subscribe_to_run_id_changed(self._set_run_id)
        self.event_bus.subscribe_to_table_summary_data_changed(self._set_avg_summary)
        self.event_bus.subscribe_to_table_detailed_data_change(self._set_detailed_summary)

    def _set_run_id(self, run_id: int | None) -> None:
        """
        Update the currently selected run ID and refresh the full results cache.

        Args:
            run_id: Newly selected run ID, or None.
        """
        self._selected_run_id = run_id
        self._full_results_cache = {}
        if run_id is not None:
            try:
                results = self.data_api.retrieve_benchmark_results_for_run(run_id)
                for r in results:
                    self._full_results_cache[f"{r.model_name}|{r.task_id}"] = r
            except Exception as e:
                logger.warning(f"Failed to cache full results for run {run_id}: {e}")
        self._emit_chart_data()

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
        Update the cached detailed summary data and incrementally populate the full results cache.

        When a run is active and new table rows arrive via EventBus, this method fetches
        the corresponding BenchmarkResult records from the DB and adds them to the cache
        so that live row selections can return full detail immediately.

        Args:
            detailed_summary: New detailed summary items, or None to clear.
        """
        value = detailed_summary or []
        self._detailed_summary = value
        if self._selected_run_id is None:
            return
        incoming_keys = {f"{item.model_name}|{item.task_id}" for item in value}
        new_keys = incoming_keys - self._full_results_cache.keys()
        if not new_keys:
            return
        try:
            results = self.data_api.retrieve_benchmark_results_for_run(self._selected_run_id)
            for r in results:
                key = f"{r.model_name}|{r.task_id}"
                if key in new_keys:
                    self._full_results_cache[key] = r
        except Exception as e:
            logger.warning(f"Failed to update live cache for run {self._selected_run_id}: {e}")
        self._emit_chart_data()

    def handle_run_selection_change(self, run_id: int | None) -> None:
        """
        Handle user selection of a different benchmark run.

        Args:
            run_id: Newly selected run ID, or None.
        """
        logger.debug("handle_run_selection_change")
        self.event_bus.emit_run_id_changed(run_id)

    def handle_delete_click(self, _: object) -> None:
        """
        Handle user request to delete the currently selected benchmark run.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("handle_delete_click")
        if self._selected_run_id is None or self._selected_run_id <= 0:
            logger.debug("No Run ID")
            self.event_bus.emit_global_event_msg("No Run ID selected to Delete")
            return
        deleted_run_id = self._selected_run_id
        try:
            self.data_api.delete_benchmark_run(deleted_run_id)
            logger.debug("Deleted run %d", deleted_run_id)
        except Exception as e:
            logger.warning("Failed to delete run %d: %s", deleted_run_id, e)
            self.event_bus.emit_global_event_msg(f"Failed to delete run {deleted_run_id}")
            return
        self._set_avg_summary([])
        self._set_detailed_summary([])
        try:
            runs_list = get_benchmark_runs(self.data_api)
            if runs_list:
                run_ids = [r[0] for r in runs_list]
                next_id = next((rid for rid in run_ids if rid > deleted_run_id), run_ids[0])
                self.event_bus.emit_run_id_changed(next_id)
                self.event_bus.emit_run_ids_changed(runs_list)
            else:
                self.event_bus.emit_run_id_changed(None)
                self.event_bus.emit_run_ids_changed([])
        except Exception as e:
            logger.warning("Failed to retrieve runs after deletion: %s", e)
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_run_ids_changed([])

    def handle_summary_export_csv_click(self, _: object) -> None:
        """
        Handle user request to export summary results to CSV.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("handle_summary_export_csv_click")
        try:
            self.table_serializer.save_summary_as_csv(self._avg_summary)
            self.event_bus.emit_global_event_msg("Summary exported as CSV")
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_summary_export_md_click(self, _: object) -> None:
        """
        Handle user request to export summary results to Markdown.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("handle_summary_export_md_click")
        try:
            self.table_serializer.save_summary_as_md(self._avg_summary)
            self.event_bus.emit_global_event_msg("Summary exported as Markdown")
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_detailed_export_csv_click(self, _: object) -> None:
        """
        Handle user request to export detailed results to CSV.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("handle_detailed_export_csv_click")
        try:
            self.table_serializer.save_details_as_csv(self._detailed_summary)
            self.event_bus.emit_global_event_msg("Details exported as CSV")
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    def handle_detailed_export_md_click(self, _: object) -> None:
        """
        Handle user request to export detailed results to Markdown.

        Args:
            _: Ignored event parameter.
        """
        logger.debug("handle_detailed_export_md_click")
        try:
            self.table_serializer.save_details_as_md(self._detailed_summary)
            self.event_bus.emit_global_event_msg("Details exported as Markdown")
        except Exception as e:
            logger.warning(f"Failed to save summary data for run {self._selected_run_id}: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    @override
    def handle_task_selected(self, model_name: str, task_id: str) -> BenchmarkResult | None:
        """Return the full BenchmarkResult for a selected task row, or None if not found.

        Args:
            model_name: Model name from the selected table row.
            task_id: Task ID from the selected table row.
        """
        return self._full_results_cache.get(f"{model_name}|{task_id}")

    @override
    def export_summary_csv(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export summary as CSV to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """
        logger.debug("export_summary_csv")
        try:
            self.table_serializer.save_summary_as_csv_to_path(save_path, self._avg_summary)
            if also_save_to_default:
                self.table_serializer.save_summary_as_csv(self._avg_summary)
            self.event_bus.emit_global_event_msg("Summary exported as CSV")
        except Exception as e:
            logger.warning(f"Failed to export summary CSV: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to export summary as CSV")

    @override
    def export_summary_md(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export summary as Markdown to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """
        logger.debug("export_summary_md")
        try:
            self.table_serializer.save_summary_as_md_to_path(save_path, self._avg_summary)
            if also_save_to_default:
                self.table_serializer.save_summary_as_md(self._avg_summary)
            self.event_bus.emit_global_event_msg("Summary exported as Markdown")
        except Exception as e:
            logger.warning(f"Failed to export summary Markdown: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to export summary as Markdown")

    @override
    def export_details_csv(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export details as CSV to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """
        logger.debug("export_details_csv")
        try:
            self.table_serializer.save_details_as_csv_to_path(save_path, self._detailed_summary)
            if also_save_to_default:
                self.table_serializer.save_details_as_csv(self._detailed_summary)
            self.event_bus.emit_global_event_msg("Details exported as CSV")
        except Exception as e:
            logger.warning(f"Failed to export details CSV: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to export details as CSV")

    @override
    def export_details_md(self, save_path: Path, *, also_save_to_default: bool) -> None:
        """Export details as Markdown to a user-chosen path, optionally also to the default folder.

        Args:
            save_path: Full file path for the primary export.
            also_save_to_default: Whether to additionally save to the program's default folder.
        """
        logger.debug("export_details_md")
        try:
            self.table_serializer.save_details_as_md_to_path(save_path, self._detailed_summary)
            if also_save_to_default:
                self.table_serializer.save_details_as_md(self._detailed_summary)
            self.event_bus.emit_global_event_msg("Details exported as Markdown")
        except Exception as e:
            logger.warning(f"Failed to export details Markdown: {e!s}")
            self.event_bus.emit_global_event_msg("Failed to export details as Markdown")

    @override
    def get_also_save_to_default(self) -> bool:
        """Return the persisted 'also save to default folder' preference."""
        return self._app_settings_service.get_bool("export_also_save_to_default", default=True)

    @override
    def set_also_save_to_default(self, value: bool) -> None:
        """Persist the 'also save to default folder' preference.

        Args:
            value: True to also save to the program folder on each export.
        """
        self._app_settings_service.set("export_also_save_to_default", str(value).lower())

    def subscribe_to_runs_change(self, callback: Callable[[list[tuple[int, str]]], None]) -> None:
        """
        Subscribe to changes in the list of available benchmark runs.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """
        logger.debug("subscribe_to_runs_change")
        self.event_bus.subscribe_to_run_ids_changed(callback)

    def subscribe_to_run_id_changed(self, callback: Callable[[int | None], None]) -> None:
        """
        Subscribe to changes in the currently selected run ID.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """
        logger.debug("subscribe_to_run_id_changed")
        self.event_bus.subscribe_to_run_id_changed(callback)

    def subscribe_to_summary_data_change(self, callback: Callable[[list[AvgSummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the summary results data.

        Args:
            callback: Function to invoke with updated average summary items.
        """
        logger.debug("subscribe_to_summary_data_change")
        self.event_bus.subscribe_to_table_summary_data_changed(callback)

    def subscribe_to_detailed_data_change(self, callback: Callable[[list[SummaryTableItem]], None]) -> None:
        """
        Subscribe to changes in the detailed results data.

        Args:
            callback: Function to invoke with updated detailed summary items.
        """
        logger.debug("subscribe_to_detailed_data_change")
        self.event_bus.subscribe_to_table_detailed_data_change(callback)

    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """
        Subscribe to changes in benchmark execution status.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """
        logger.debug("subscribe_to_benchmark_status_change")
        self.event_bus.subscribe_to_background_thread_is_running(callback)

    def subscribe_to_judge_summary(self, callback: Callable[[JudgeSummaryEvent], None]) -> None:
        """Subscribe to judge summary events emitted after a full-grading run.

        Args:
            callback: Function to invoke with JudgeSummaryEvent (run_id, summary_text).
        """
        logger.debug("subscribe_to_judge_summary")
        self.event_bus.subscribe_to_judge_summary(callback)

    @override
    def subscribe_to_perf_analysis(self, callback: Callable[[PerfAnalysisEvent], None]) -> None:
        """Subscribe to performance analysis events emitted after Performance or Speed runs.

        Args:
            callback: Function to invoke with PerfAnalysisEvent (run_id, analysis_text).
        """
        logger.debug("subscribe_to_perf_analysis")
        self.event_bus.subscribe_to_perf_analysis(callback)

    def _emit_chart_data(self) -> None:
        """Notify all chart data subscribers with the current run and results cache."""
        if not self._chart_data_callbacks:
            return
        results = list(self._full_results_cache.values())
        run: BenchmarkRun | None = None
        if self._selected_run_id is not None:
            try:
                run = self.data_api.retrieve_benchmark_run(self._selected_run_id)
            except Exception as e:
                logger.warning(f"Failed to retrieve run {self._selected_run_id} for chart data: {e}")
        for callback in self._chart_data_callbacks:
            callback(run, results)

    @override
    def subscribe_to_chart_data_change(
        self, callback: Callable[[BenchmarkRun | None, list[BenchmarkResult]], None]
    ) -> None:
        """Register a callback to receive chart data updates.

        Args:
            callback: Function to invoke with the current BenchmarkRun (or None) and
                list of BenchmarkResult objects for the selected run.
        """
        self._chart_data_callbacks.append(callback)

    @override
    def get_app_settings_service(self) -> AppSettingsServiceApi:
        """Return the app settings service for persistent KV storage."""
        return self._app_settings_service
