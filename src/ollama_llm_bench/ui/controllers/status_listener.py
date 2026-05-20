import logging
import time
from typing import Final, Protocol

from ollama_llm_bench.backend.core.interfaces import (
    BenchmarkFlowApi,
    DataApi,
    EventBus,
    ResultApi,
)
from ollama_llm_bench.backend.core.models import (
    AvgSummaryTableItem,
    JudgeSummaryEvent,
    PerfAnalysisEvent,
    PipelineStage,
    ReporterStatusMsg,
    SummaryTableItem,
)
from ollama_llm_bench.backend.utils.run_utils import get_benchmark_runs

logger = logging.getLogger(__name__)

_LIVE_UPDATE_DEBOUNCE_S: Final[float] = 0.5


class _HasRunId(Protocol):
    """Structural protocol for events that carry a run identifier."""

    @property
    def run_id(self) -> int: ...


class StatusListener:
    """
    Listener component that monitors benchmark execution progress and run selection changes.
    Automatically updates result tables and synchronizes UI components when data changes.
    """

    def __init__(
        self,
        *,
        data_api: DataApi,
        benchmark_flow_api: BenchmarkFlowApi,
        event_bus: EventBus,
        result_api: ResultApi,
    ):
        """
        Initialize the status listener.

        Args:
            data_api: Interface for retrieving benchmark runs.
            benchmark_flow_api: Interface for subscribing to execution progress.
            event_bus: Event bus for emitting table data updates.
            result_api: Interface for computing benchmark summaries.
        """
        super().__init__()
        self.data_api = data_api
        self.benchmark_flow_api = benchmark_flow_api
        self.event_bus = event_bus
        self.result_api = result_api

        self._last_live_update: float = 0.0

        self.event_bus.subscribe_to_run_id_changed(self._run_id_changed)
        self.benchmark_flow_api.subscribe_to_benchmark_progress_events(self._progress_changed)
        self.event_bus.subscribe_to_task_completed(self._on_task_or_judge_completed)
        self.event_bus.subscribe_to_judge_completed(self._on_task_or_judge_completed)

    def _run_id_changed(self, run_id: int | None) -> None:
        """
        Handle changes in the active benchmark run selection.

        Args:
            run_id: Newly selected run ID, or None.
        """
        logger.debug("_run_id_changed")
        if run_id is None or run_id <= 0:
            self._post_tables_update(run_id)
            return

        try:
            run = self.data_api.retrieve_benchmark_run(run_id)
        except Exception as e:
            logger.warning("Failed to retrieve run %s: %s", run_id, e)
            self._post_tables_update(run_id)
            return

        if run.judge_summary:
            self.event_bus.emit_judge_summary(JudgeSummaryEvent(run_id=run.run_id, summary_text=run.judge_summary))
        if run.perf_analysis_result:
            self.event_bus.emit_perf_analysis(
                PerfAnalysisEvent(run_id=run.run_id, analysis_text=run.perf_analysis_result)
            )

        self._post_tables_update(run.run_id)

    def _progress_changed(self, status: ReporterStatusMsg) -> None:
        """
        Handle progress updates from ongoing benchmark execution.

        Args:
            status: Current execution status including stage and run ID.
        """
        if status is not None:
            stage = status.current_stage
            run_id = status.current_run_id
            if stage in (PipelineStage.FINISHED, PipelineStage.FAILED):
                self.event_bus.emit_run_id_changed(run_id)
                try:
                    runs_list = get_benchmark_runs(self.data_api)
                    self.event_bus.emit_run_ids_changed(runs_list)
                except Exception as e:
                    logger.warning("failed to retrieve runs %s", e)
                    self.event_bus.emit_run_ids_changed([])
                self._post_tables_update(run_id)

    def _on_task_or_judge_completed(self, event: _HasRunId) -> None:
        """Refresh result tables after each task or judge event, debounced.

        Args:
            event: Any event carrying a run_id field.
        """
        now = time.monotonic()
        if now - self._last_live_update >= _LIVE_UPDATE_DEBOUNCE_S:
            self._last_live_update = now
            self._post_tables_update(event.run_id)

    def _post_tables_update(self, run_id: int | None) -> None:
        """
        Retrieve and broadcast updated summary and detailed result tables.

        Args:
            run_id: Benchmark run ID to fetch results for.
        """
        avg_summary = self._get_summary_data(run_id)
        detailed_summary = self._get_detailed_data(run_id)
        self.event_bus.emit_table_summary_data_changed(avg_summary)
        self.event_bus.emit_table_detailed_data_change(detailed_summary)

    def _get_summary_data(self, run_id: int | None) -> list[AvgSummaryTableItem]:
        """
        Retrieve averaged performance metrics for all models in a run.

        Args:
            run_id: Identifier of the benchmark run.

        Returns:
            List of averaged summary items, or empty list on failure.
        """
        if run_id is None or run_id <= 0:
            logger.debug("Attempted to get summary data when no run is selected")
            return []

        try:
            summary = self.result_api.retrieve_avg_benchmark_results_for_run(run_id)
            logger.info(
                "Retrieved summary data for run ID %s with %d model summaries",
                run_id,
                len(summary),
            )
            return summary
        except Exception as e:
            logger.error("Failed to retrieve summary data for run %s: %s", run_id, e)
            return []

    def _get_detailed_data(self, run_id: int | None) -> list[SummaryTableItem]:
        """
        Retrieve detailed per-task performance metrics for a run.

        Args:
            run_id: Identifier of the benchmark run.

        Returns:
            List of detailed summary items, or empty list on failure.
        """
        if run_id is None or run_id <= 0:
            logger.debug("Attempted to get detailed data when no run is selected")
            return []

        try:
            detailed = self.result_api.retrieve_detailed_benchmark_results_for_run(run_id)
            logger.info(
                "Retrieved detailed data for run ID %s with %d task results",
                run_id,
                len(detailed),
            )
            return detailed
        except Exception as e:
            logger.error("Failed to retrieve detailed data for run %s: %s", run_id, e)
            return []
