"""RunConfigController — unified run configuration controller for the V2 RunConfigPanel."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    BenchmarkFlowApi,
    DataApi,
    EventBus,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunStatus,
    ProviderHealthCheckEvent,
    RunMode,
    RunStartEvent,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_EMBEDDING_FILTER_ENABLED,
    SETTING_REASONING_EFFORT_DEFAULT,
    SETTING_STREAMING_ENABLED,
    SETTING_WARMUP_ENABLED,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier

_logger = logging.getLogger(__name__)


class RunConfigController:
    """Unified run configuration controller.

    Merges provider/model discovery, previous-run management, and benchmark
    lifecycle control (start, pause, resume, stop) into one class.
    """

    def __init__(
        self,
        *,
        data_api: DataApi,
        provider_registry: ProviderRegistryApi,
        benchmark_flow_api: BenchmarkFlowApi,
        event_bus: EventBus,
        task_file_loader: TaskFileLoaderApi,
        app_settings_service: AppSettingsServiceApi,
        embedding_classifier: EmbeddingModelClassifier,
    ) -> None:
        self._data_api = data_api
        self._provider_registry = provider_registry
        self._benchmark_flow_api = benchmark_flow_api
        self._event_bus = event_bus
        self._task_file_loader = task_file_loader
        self._app_settings_service = app_settings_service
        self._embedding_classifier = embedding_classifier
        self._provider_health: dict[str, bool] = {}

        # When a benchmark finishes, auto-refresh the previous-runs list in the UI.
        event_bus.subscribe_to_background_thread_is_running(self._on_background_changed)
        event_bus.subscribe_to_provider_health_check(self._on_provider_health_check)

    # ------------------------------------------------------------------
    # Provider / model discovery
    # ------------------------------------------------------------------

    def get_provider_names(self) -> list[str]:
        """Return the list of enabled provider IDs.

        Returns:
            List of provider ID strings; empty if retrieval fails.
        """
        try:
            return [p.provider_id for p in self._provider_registry.get_enabled_providers()]
        except Exception:
            _logger.warning("Failed to list enabled providers", exc_info=True)
            return []

    def get_healthy_provider_ids(self) -> list[str]:
        """Return enabled provider IDs whose last health check passed (or were never checked).

        A provider that has never been health-checked is considered healthy (optimistic default).

        Returns:
            List of provider ID strings; empty if retrieval fails.
        """
        try:
            enabled = self._provider_registry.get_enabled_providers()
            return [p.provider_id for p in enabled if self._provider_health.get(p.provider_id, True)]
        except Exception:
            _logger.warning("Failed to list healthy providers", exc_info=True)
            return []

    def show_status_message(self, text: str, msecs: int = 5000) -> None:
        """Display a transient message in the application status bar.

        Args:
            text: The message text to display.
            msecs: Duration hint in milliseconds (routed via event bus; default 5000).
        """
        self._event_bus.emit_global_event_msg(text)

    def subscribe_to_provider_registry_reloaded(self, callback: Callable[[], None]) -> None:
        """Subscribe to provider registry reload events.

        Args:
            callback: Invoked (with no arguments) whenever the provider registry is reloaded.
        """
        self._event_bus.subscribe_to_provider_registry_reloaded(lambda _event: callback())

    def get_run(self, run_id: int) -> BenchmarkRun:
        """Load a single BenchmarkRun from the database.

        Args:
            run_id: Unique ID of the run to load.

        Returns:
            The requested BenchmarkRun.

        Raises:
            ValueError: If no run with the given ID exists.
        """
        return self._data_api.retrieve_benchmark_run(run_id)

    def get_results_for_run(self, run_id: int) -> list[BenchmarkResult]:
        """Load all BenchmarkResult rows for the given run.

        Args:
            run_id: Unique ID of the parent run.

        Returns:
            List of BenchmarkResult records; empty if none exist.
        """
        return self._data_api.retrieve_benchmark_results_for_run(run_id)

    def get_enabled_provider_ids(self) -> set[str]:
        """Return the set of currently enabled provider IDs.

        Returns:
            Set of provider ID strings; empty set if retrieval fails.
        """
        try:
            return {p.provider_id for p in self._provider_registry.get_enabled_providers()}
        except Exception:
            _logger.warning("Failed to list enabled providers for drift check", exc_info=True)
            return set()

    def get_models_for_provider(self, provider_name: str) -> list[str]:
        """Return available model names for the given provider.

        Args:
            provider_name: Provider ID to query.

        Returns:
            List of model name strings; empty if the provider is unknown or unavailable.
        """
        try:
            provider = self._provider_registry.get_provider(provider_name)
            return [m.model_name for m in provider.get_available_models()]
        except Exception:
            _logger.warning("Failed to get models for provider %s", provider_name, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Embedding model classification
    # ------------------------------------------------------------------

    def is_embedding_model(self, model_name: str) -> bool:
        """Return True if model_name matches known embedding-only model patterns.

        Args:
            model_name: Raw model name string as returned by the provider.

        Returns:
            True when the model appears to be an embedding-only model.
        """
        return self._embedding_classifier.is_embedding_model(model_name)

    def is_embedding_filter_enabled(self) -> bool:
        """Return True when embedding models should be hidden from model lists.

        Returns:
            True when the embedding filter setting is enabled.
        """
        return self._app_settings_service.get_bool(SETTING_EMBEDDING_FILTER_ENABLED)

    # ------------------------------------------------------------------
    # Previous-run management
    # ------------------------------------------------------------------

    def get_unfinished_runs(self) -> list[tuple[int, str]]:
        """Return all unfinished benchmark runs sorted newest-first.

        Returns:
            List of (run_id, timestamp) tuples for NOT_COMPLETED runs; empty on error.
        """
        try:
            runs = self._data_api.retrieve_benchmark_runs()
            return [
                (r.run_id, r.timestamp)
                for r in sorted(runs, key=lambda r: r.timestamp, reverse=True)
                if r.status == BenchmarkRunStatus.NOT_COMPLETED
            ]
        except Exception:
            _logger.warning("Failed to retrieve unfinished runs", exc_info=True)
            return []

    def get_recent_runs(self, *, limit: int = 100) -> list[BenchmarkRun]:
        """Return the N most-recent runs across all statuses, ordered by timestamp DESC.

        Args:
            limit: Maximum number of runs to return (default 100).

        Returns:
            List of BenchmarkRun records; empty on error.
        """
        try:
            runs = self._data_api.retrieve_benchmark_runs()
            runs.sort(key=lambda r: r.timestamp, reverse=True)
            return runs[:limit]
        except Exception:
            _logger.warning("Failed to retrieve recent runs", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Benchmark lifecycle
    # ------------------------------------------------------------------

    def handle_start_click(self, event: RunStartEvent) -> None:
        """Handle a start-benchmark request from the RunConfigPanel.

        Creates a new BenchmarkRun and pre-populated BenchmarkResult rows in the
        database, then delegates execution to BenchmarkFlowApi.

        Args:
            event: RunStartEvent carrying run mode, provider, model, and task selections.
        """
        if self._benchmark_flow_api.is_running():
            self._event_bus.emit_global_event_msg("Benchmark already running.")
            return
        if not event.test_models:
            self._event_bus.emit_global_event_msg("No test models selected.")
            return
        try:
            self._app_settings_service.set(SETTING_STREAMING_ENABLED, str(event.streaming_enabled).lower())
            self._app_settings_service.set(SETTING_WARMUP_ENABLED, str(event.warmup_enabled).lower())
            self._app_settings_service.set(SETTING_REASONING_EFFORT_DEFAULT, event.reasoning_effort)

            perf_config_json: str | None = None
            if event.run_mode == RunMode.PERFORMANCE and event.performance_config is not None:
                cfg = event.performance_config
                perf_config_json = json.dumps(
                    {
                        "input_sizes": list(cfg.input_sizes),
                        "output_sizes": list(cfg.output_sizes),
                        "repeat_count": cfg.repeat_count,
                        "analysis_enabled": event.performance_analysis_enabled,
                    }
                )
            elif event.performance_analysis_enabled:
                perf_config_json = json.dumps({"analysis_enabled": True})

            run = BenchmarkRun(
                run_id=0,
                timestamp=datetime.now().isoformat(),
                judge_model=event.judge_model,
                status=BenchmarkRunStatus.NOT_COMPLETED,
                run_mode=event.run_mode,
                judge_provider_id=event.judge_provider,
                task_file_paths=tuple(str(p) for p in event.task_paths),
                models_json=json.dumps(
                    [{"provider_id": event.test_provider, "model_name": model} for model in event.test_models]
                ),
                performance_config=perf_config_json,
            )
            run_id = self._data_api.create_benchmark_run(run)

            # Performance mode: pipeline generates tasks; no pre-creation needed here.
            # Speed/analysis flag is embedded in performance_config JSON on the run.
            if event.run_mode != RunMode.PERFORMANCE:
                file_paths = list(event.task_paths) if event.task_paths else []
                tasks = self._task_file_loader.load_tasks(file_paths)
                results = [
                    BenchmarkResult(
                        run_id=run_id,
                        task_id=task.task_id,
                        model_name=model,
                        provider_id=event.test_provider,
                    )
                    for model in event.test_models
                    for task in tasks
                ]
                self._data_api.create_benchmark_results(results)

            self._event_bus.emit_run_id_changed(run_id)
            self._event_bus.emit_log_clean()
            self._benchmark_flow_api.start_execution(run_id)
        except Exception:
            _logger.warning("Failed to start benchmark run", exc_info=True)
            self._event_bus.emit_global_event_msg("Failed to start benchmark run.")

    def handle_pause_click(self) -> None:
        """Request a pause of the currently running benchmark."""
        if not self._benchmark_flow_api.is_running():
            return
        self._benchmark_flow_api.pause_execution()

    def handle_resume_click(self) -> None:
        """Request resumption of a paused benchmark run."""
        self._benchmark_flow_api.resume_execution()

    def handle_stop_click(self) -> None:
        """Request cancellation of the currently running benchmark."""
        if self._benchmark_flow_api.is_running():
            self._benchmark_flow_api.stop_execution()

    def handle_resume_run_click(self, run_id: int) -> None:
        """Resume a previously unfinished benchmark run.

        Args:
            run_id: ID of the NOT_COMPLETED run to resume.
        """
        if self._benchmark_flow_api.is_running():
            self._event_bus.emit_global_event_msg("Benchmark already running.")
            return
        try:
            runs = self._data_api.retrieve_benchmark_runs()
            matching = [r for r in runs if r.run_id == run_id]
            if not matching:
                self._event_bus.emit_global_event_msg(f"Run {run_id} not found.")
                return
            run = matching[0]
            if run.status != BenchmarkRunStatus.NOT_COMPLETED:
                self._event_bus.emit_global_event_msg(f"Run {run_id} is already completed.")
                return
            self._event_bus.emit_run_id_changed(run_id)
            self._benchmark_flow_api.start_execution(run_id)
        except Exception:
            _logger.warning("Failed to resume run %d", run_id, exc_info=True)
            self._event_bus.emit_global_event_msg("Failed to resume run.")

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe_to_benchmark_status_change(self, callback: Callable[[bool], None]) -> None:
        """Subscribe to benchmark execution start/stop events.

        Args:
            callback: Invoked with True when execution starts, False when it stops.
        """
        self._event_bus.subscribe_to_background_thread_is_running(callback)

    def subscribe_to_runs_change(self, callback: Callable[[list[tuple[int, str]]], None]) -> None:
        """Subscribe to changes in the list of available run IDs.

        Args:
            callback: Invoked with updated list of (run_id, timestamp) tuples.
        """
        self._event_bus.subscribe_to_run_ids_changed(callback)

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _on_background_changed(self, is_running: bool) -> None:
        if not is_running:
            self._event_bus.emit_run_ids_changed(self.get_unfinished_runs())

    def _on_provider_health_check(self, event: ProviderHealthCheckEvent) -> None:
        self._provider_health[event.provider_id] = event.is_healthy
