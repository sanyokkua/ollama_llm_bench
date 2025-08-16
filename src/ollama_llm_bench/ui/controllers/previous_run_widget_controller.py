import logging
from typing import Callable, List, Optional, override

from ollama_llm_bench.core.controllers import PreviousRunWidgetControllerApi
from ollama_llm_bench.core.interfaces import BenchmarkFlowApi, BenchmarkTaskApi, DataApi, EventBus
from ollama_llm_bench.core.models import BenchmarkRun, BenchmarkRunStatus
from ollama_llm_bench.utils.run_utils import get_tasks_tuple

logger = logging.getLogger(__name__)


class PreviousRunWidgetController(PreviousRunWidgetControllerApi):
    def __init__(self, *,
                 data_api: DataApi,
                 task_api: BenchmarkTaskApi,
                 benchmark_flow_api: BenchmarkFlowApi,
                 event_bus: EventBus,
                 ):
        self.data_api = data_api
        self.task_api = task_api
        self.benchmark_flow_api = benchmark_flow_api
        self.event_bus = event_bus
        self._last_selected_run_id: Optional[int] = None
        self.event_bus.subscribe_to_run_id_changed(self._on_run_id_changed)
        self.event_bus.subscribe_to_background_thread_is_running(self._on_background_is_running_changed)

    def _on_run_id_changed(self, run_id: Optional[int]) -> None:
        self._last_selected_run_id = run_id

    def _get_current_run(self) -> Optional[BenchmarkRun]:
        try:
            current_run = self.data_api.retrieve_benchmark_run(self._last_selected_run_id)
        except Exception as e:
            logger.warning(f"Failed to retrieve run {self._last_selected_run_id}: {e}")
            current_run = None
        return current_run

    def _on_background_is_running_changed(self, is_running: bool):
        if not is_running:
            self.handle_refresh_click(False)

    @override
    def handle_refresh_click(self, _) -> None:
        logger.debug("PreviousRunWidgetController.handle_refresh_click")
        runs_list = get_tasks_tuple(self.data_api)
        logger.debug(f"Retrieved {len(runs_list)} benchmark runs")
        self.event_bus.emit_run_ids_changed(runs_list)

        if len(runs_list) > 0:
            self.event_bus.emit_run_id_changed(runs_list[0][0])
        else:
            self.event_bus.emit_run_id_changed(None)

    @override
    def handle_start_click(self, _):
        logger.debug("PreviousRunWidgetController.handle_start_click")
        if self.benchmark_flow_api.is_running():
            logger.debug(f"Benchmark flow is already running")
            self.event_bus.emit_global_event_msg(f"Benchmark flow is already running")
            return

        if self._last_selected_run_id is None or self._last_selected_run_id <= 0:
            logger.debug(f"No Selected RUN IDs")
            self.event_bus.emit_global_event_msg(f"No Selected RUN IDs")
            return

        current_run = self._get_current_run()
        if current_run is None:
            logger.debug(f"No Run for ID: {self._last_selected_run_id}")
            self.event_bus.emit_global_event_msg(f"No Run for ID: {self._last_selected_run_id}")
            return

        if current_run.status != BenchmarkRunStatus.NOT_COMPLETED:
            logger.debug(f"Run {self._last_selected_run_id} is already completed")
            self.event_bus.emit_global_event_msg(f"Run already completed")
            return
        self.benchmark_flow_api.start_execution(current_run.run_id)

    @override
    def handle_stop_click(self, _) -> None:
        logger.debug("Stopping previous run")
        if self.benchmark_flow_api.is_running():
            logger.debug(f"Benchmark flow is running, will stop execution")
            self.benchmark_flow_api.stop_execution()
        else:
            logger.debug(f"Benchmark flow is stopped")

    @override
    def handle_item_change(self, run_id: Optional[int]) -> None:
        logger.debug(f"Item change for run {run_id}")
        if run_id is None or run_id <= 0:
            logger.debug(f"No Run ID")
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_global_event_msg("No Run ID")
            return

        try:
            run = self.data_api.retrieve_benchmark_run(run_id)
        except Exception as e:
            logger.warning(f"Failed to retrieve run {run_id}: {e}")
            self.event_bus.emit_run_id_changed(None)
            self.event_bus.emit_global_event_msg("Failed to retrieve run {run_id}")
            return

        self.event_bus.emit_run_id_changed(run.run_id)

    @override
    def subscribe_to_runs_change(self, callback: Callable[[List[tuple[int, str]]], None]) -> None:
        logger.debug("Subscribing to runs change")
        self.event_bus.subscribe_to_run_ids_changed(callback)

    @override
    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        logger.debug("Subscribing to benchmark status change")
        self.event_bus.subscribe_to_background_thread_is_running(callback)

    @override
    def subscribe_to_run_id_changed(self, callback: Callable[[Optional[int]], None]) -> None:
        self.event_bus.subscribe_to_run_id_changed(callback)
