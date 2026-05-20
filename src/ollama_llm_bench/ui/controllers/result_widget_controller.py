from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EventBus,
    TableSerializerApi,
)
from ollama_llm_bench.backend.core.models import (
    AvgSummaryTableItem,
    BenchmarkResult,
    BenchmarkRun,
    JudgeSummaryEvent,
    PerfAnalysisEvent,
    RunRenamedEvent,
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
        table_serializer: TableSerializerApi,
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
                    self._full_results_cache[f"{r.model_name}|{r.task_id}|{r.prompt_version}"] = r
            except Exception as e:
                logger.warning("Failed to cache full results for run %s: %s", run_id, e)
        self._emit_chart_data()

    def _set_avg_summary(self, summary: list[AvgSummaryTableItem]) -> None:
        """
        Update the cached average summary data.

        Args:
            summary: New average summary items, or None to clear.
        """
        value = summary or []
        self._avg_summary = value
        self._emit_chart_data()

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
        if self._selected_run_id is None or self._selected_run_id <= 0:
            return
        incoming_keys = {f"{item.model_name}|{item.task_id}|{item.prompt_version}" for item in value}
        new_keys = incoming_keys - self._full_results_cache.keys()
        if not new_keys:
            return
        try:
            results = self.data_api.retrieve_benchmark_results_for_run(self._selected_run_id)
            for r in results:
                key = f"{r.model_name}|{r.task_id}|{r.prompt_version}"
                if key in new_keys:
                    self._full_results_cache[key] = r
        except Exception as e:
            logger.warning("Failed to update live cache for run %s: %s", self._selected_run_id, e)
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
            logger.warning("Failed to save summary data for run %s: %s", self._selected_run_id, e)
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
            logger.warning("Failed to save summary data for run %s: %s", self._selected_run_id, e)
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
            logger.warning("Failed to save summary data for run %s: %s", self._selected_run_id, e)
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
            logger.warning("Failed to save summary data for run %s: %s", self._selected_run_id, e)
            self.event_bus.emit_global_event_msg("Failed to save summary data")

    @override
    def handle_task_selected(self, model_name: str, task_id: str, prompt_version: str = "v1") -> BenchmarkResult | None:
        """Return the full BenchmarkResult for a selected task row, or None if not found.

        Args:
            model_name: Model name from the selected table row.
            task_id: Task ID from the selected table row.
            prompt_version: Prompt variant version string.
        """
        return self._full_results_cache.get(f"{model_name}|{task_id}|{prompt_version}")

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
            logger.warning("Failed to export summary CSV: %s", e)
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
            logger.warning("Failed to export summary Markdown: %s", e)
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
            logger.warning("Failed to export details CSV: %s", e)
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
            logger.warning("Failed to export details Markdown: %s", e)
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

    def subscribe_to_runs_change(
        self,
        callback: Callable[[list[tuple[int, str]]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """
        Subscribe to changes in the list of available benchmark runs.

        Args:
            callback: Function to invoke with updated list of (run_id, run_name) tuples.
        """
        logger.debug("subscribe_to_runs_change")
        self.event_bus.subscribe_to_run_ids_changed(callback, parent=parent)

    def subscribe_to_run_id_changed(
        self,
        callback: Callable[[int | None], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """
        Subscribe to changes in the currently selected run ID.

        Args:
            callback: Function to invoke with the new run ID (or None).
        """
        logger.debug("subscribe_to_run_id_changed")
        self.event_bus.subscribe_to_run_id_changed(callback, parent=parent)

    def subscribe_to_summary_data_change(
        self,
        callback: Callable[[list[AvgSummaryTableItem]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """
        Subscribe to changes in the summary results data.

        Args:
            callback: Function to invoke with updated average summary items.
        """
        logger.debug("subscribe_to_summary_data_change")
        self.event_bus.subscribe_to_table_summary_data_changed(callback, parent=parent)

    def subscribe_to_detailed_data_change(
        self,
        callback: Callable[[list[SummaryTableItem]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """
        Subscribe to changes in the detailed results data.

        Args:
            callback: Function to invoke with updated detailed summary items.
        """
        logger.debug("subscribe_to_detailed_data_change")
        self.event_bus.subscribe_to_table_detailed_data_change(callback, parent=parent)

    def subscribe_to_benchmark_status_change(
        self,
        callback: Callable[[bool], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """
        Subscribe to changes in benchmark execution status.

        Args:
            callback: Function to invoke with True (running) or False (idle).
        """
        logger.debug("subscribe_to_benchmark_status_change")
        self.event_bus.subscribe_to_background_thread_is_running(callback, parent=parent)

    def subscribe_to_judge_summary(
        self,
        callback: Callable[[JudgeSummaryEvent], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to judge summary events emitted after a full-grading run.

        Args:
            callback: Function to invoke with JudgeSummaryEvent (run_id, summary_text).
        """
        logger.debug("subscribe_to_judge_summary")
        self.event_bus.subscribe_to_judge_summary(callback, parent=parent)

    @override
    def subscribe_to_perf_analysis(
        self,
        callback: Callable[[PerfAnalysisEvent], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to performance analysis events emitted after Performance or Speed runs.

        Args:
            callback: Function to invoke with PerfAnalysisEvent (run_id, analysis_text).
        """
        logger.debug("subscribe_to_perf_analysis")
        self.event_bus.subscribe_to_perf_analysis(callback, parent=parent)

    def _emit_chart_data(self) -> None:
        """Notify all chart data subscribers with the current run and results cache."""
        if not self._chart_data_callbacks:
            return
        results = list(self._full_results_cache.values())
        run: BenchmarkRun | None = None
        if self._selected_run_id is not None and self._selected_run_id > 0:
            try:
                run = self.data_api.retrieve_benchmark_run(self._selected_run_id)
            except Exception as e:
                logger.warning("Failed to retrieve run %s for chart data: %s", self._selected_run_id, e)
        for callback in self._chart_data_callbacks:
            callback(run, results)

    @override
    def subscribe_to_chart_data_change(
        self,
        callback: Callable[[BenchmarkRun | None, list[BenchmarkResult]], None],
        *,
        parent: QObject | None = None,
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

    @override
    def get_run_names(self, *, exclude_run_id: int | None = None) -> frozenset[str]:
        """Return the case-folded set of existing run names, optionally excluding one run.

        Args:
            exclude_run_id: Optional run ID whose name should be excluded from the result.

        Returns:
            Frozenset of case-folded run name strings.
        """
        try:
            runs = self.data_api.retrieve_benchmark_runs()
            return frozenset(
                r.run_name.casefold() for r in runs if r.run_name is not None and r.run_id != exclude_run_id
            )
        except Exception as e:
            logger.warning("Failed to retrieve run names: %s", e)
            return frozenset()

    @override
    def rename_run(self, *, run_id: int, new_name: str) -> None:
        """Rename a benchmark run and broadcast the change via the event bus.

        Args:
            run_id: Unique ID of the run to rename.
            new_name: The new display name to assign.
        """
        self.data_api.update_run_name(run_id=run_id, run_name=new_name)
        self.event_bus.emit_run_renamed(RunRenamedEvent(run_id=run_id, new_name=new_name))
        self.event_bus.emit_run_ids_changed(get_benchmark_runs(self.data_api))

    @override
    def get_run(self, run_id: int) -> BenchmarkRun | None:
        """Return the BenchmarkRun for the given ID, or None if not found.

        Args:
            run_id: Unique identifier of the benchmark run.
        """
        try:
            return self.data_api.retrieve_benchmark_run(run_id)
        except Exception as e:
            logger.warning("Failed to retrieve run %d: %s", run_id, e)
            return None

    @override
    def subscribe_to_run_renamed(
        self,
        callback: Callable[[RunRenamedEvent], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to run renamed events.

        Args:
            callback: Function to invoke with the RunRenamedEvent when a run is renamed.
        """
        self.event_bus.subscribe_to_run_renamed(callback, parent=parent)
