"""RunConfigController — unified run configuration controller for the V2 RunConfigPanel."""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ollama_llm_bench.backend.core.interfaces import (
    AppReadinessServiceApi,
    AppSettingsServiceApi,
    BenchmarkFlowApi,
    DataApi,
    EventBus,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    AppReadinessChangedEvent,
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkRun,
    BenchmarkRunStatus,
    ModelDescriptor,
    PromptVariant,
    ProviderHealthCheckEvent,
    ReadinessVerdict,
    RunMode,
    RunRenamedEvent,
    RunStartEvent,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_EMBEDDING_FILTER_ENABLED,
    SETTING_REASONING_EFFORT_DEFAULT,
    SETTING_STREAMING_ENABLED,
    SETTING_WARMUP_ENABLED,
)
from ollama_llm_bench.backend.services.embedding_model_classifier import EmbeddingModelClassifier
from ollama_llm_bench.backend.services.model_name_parser import ModelNameParser
from ollama_llm_bench.backend.utils.run_utils import get_benchmark_runs

_logger = logging.getLogger(__name__)

_RESUMABLE_STATUSES: frozenset[BenchmarkRunStatus] = frozenset(
    {BenchmarkRunStatus.NOT_COMPLETED, BenchmarkRunStatus.STOPPED, BenchmarkRunStatus.FAILED}
)

_TERMINAL_RESULT_STATUSES: frozenset[BenchmarkResultStatus] = frozenset(
    {BenchmarkResultStatus.COMPLETED, BenchmarkResultStatus.FAILED}
)

_RETRYABLE_RESULT_STATUSES: frozenset[BenchmarkResultStatus] = frozenset(
    {
        BenchmarkResultStatus.NOT_COMPLETED,
        BenchmarkResultStatus.WAITING_FOR_JUDGE,
        BenchmarkResultStatus.FAILED,
    }
)


def _is_run_resumable(run: BenchmarkRun, results: list[BenchmarkResult]) -> bool:
    """Return True when the run has at least one non-terminal task remaining."""
    if run.status in _RESUMABLE_STATUSES:
        return True
    if run.status == BenchmarkRunStatus.COMPLETED:
        return any(r.status not in _TERMINAL_RESULT_STATUSES for r in results)
    return False


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
        app_readiness_service: AppReadinessServiceApi,
        name_parser: ModelNameParser,
    ) -> None:
        self._data_api = data_api
        self._provider_registry = provider_registry
        self._benchmark_flow_api = benchmark_flow_api
        self._event_bus = event_bus
        self._task_file_loader = task_file_loader
        self._app_settings_service = app_settings_service
        self._embedding_classifier = embedding_classifier
        self._readiness_service = app_readiness_service
        self._name_parser = name_parser
        self._last_snapshot: AppReadinessChangedEvent | None = None
        self._pending_readiness_signals: list[QObject] = []
        self._provider_health: dict[str, bool] = {}

        # When a benchmark finishes, auto-refresh the previous-runs list in the UI.
        event_bus.subscribe_to_background_thread_is_running(self._on_background_changed)
        event_bus.subscribe_to_provider_health_check(self._on_provider_health_check)
        event_bus.subscribe_to_provider_registry_reloaded(lambda _evt: self.trigger_readiness_probe())

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

    def subscribe_to_provider_registry_reloaded(
        self,
        callback: Callable[[], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to provider registry reload events.

        Args:
            callback: Invoked (with no arguments) whenever the provider registry is reloaded.
        """
        self._event_bus.subscribe_to_provider_registry_reloaded(lambda _event: callback(), parent=parent)

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

    def get_descriptors_for_provider(self, provider_name: str) -> list[ModelDescriptor]:
        """Return full ModelDescriptor list for the given provider.

        Args:
            provider_name: Provider ID to query.

        Returns:
            List of ModelDescriptor objects; empty if the provider is unknown or unavailable.
        """
        try:
            provider = self._provider_registry.get_provider(provider_name)
            return provider.get_available_models()
        except Exception:
            _logger.warning("Failed to get descriptors for provider %s", provider_name, exc_info=True)
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
        if not event.test_models and event.run_mode != RunMode.PERFORMANCE:
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

            models_list = [
                {
                    "provider_id": desc.provider_id,
                    "provider_type": desc.provider_type,
                    "model_name": desc.model_name,
                    "display_label": desc.display_label,
                    "model_family": desc.model_family,
                    "model_size_b": desc.model_size_b,
                    "quantization_label": desc.quantization_label,
                }
                for desc in event.test_models
            ]

            run = BenchmarkRun(
                run_id=0,
                timestamp=datetime.now().isoformat(),
                judge_model=event.judge_model,
                status=BenchmarkRunStatus.NOT_COMPLETED,
                run_mode=event.run_mode,
                judge_provider_id=event.judge_provider,
                task_file_paths=tuple(str(p) for p in event.task_paths),
                models_json=json.dumps(models_list),
                performance_config=perf_config_json,
            )
            run_id = self._data_api.create_benchmark_run(run)

            for spec in event.prompt_variants:
                variant = PromptVariant(
                    variant_id=spec.variant_id,
                    run_id=run_id,
                    variant_label=spec.variant_label,
                    user_prompt_template=spec.user_prompt_template,
                    system_prompt=spec.system_prompt,
                    created_at=datetime.now(UTC).isoformat(),
                )
                self._data_api.create_prompt_variant(variant)

            # Performance and PROMPT_EVAL modes: pipeline generates result rows.
            # Speed/analysis flag is embedded in performance_config JSON on the run.
            if event.run_mode not in (RunMode.PERFORMANCE, RunMode.PROMPT_EVAL):
                file_paths = list(event.task_paths) if event.task_paths else []
                tasks = self._task_file_loader.load_tasks(file_paths)
                results = [
                    BenchmarkResult(
                        run_id=run_id,
                        task_id=task.task_id,
                        model_name=desc.model_name,
                        provider_id=desc.provider_id,
                        provider_type=desc.provider_type,
                        model_family=desc.model_family,
                        model_size_b=desc.model_size_b,
                        quantization_label=desc.quantization_label,
                    )
                    for desc in event.test_models
                    for task in tasks
                ]
                self._data_api.create_benchmark_results(results)

            self._event_bus.emit_run_ids_changed(get_benchmark_runs(self._data_api))
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
            run_id: ID of the resumable run to resume.
        """
        if self._benchmark_flow_api.is_running():
            self._event_bus.emit_global_event_msg("Benchmark already running.")
            return
        try:
            run = self._data_api.retrieve_benchmark_run(run_id)
            results = self._data_api.retrieve_benchmark_results_for_run(run_id)
            if not _is_run_resumable(run, results):
                self._event_bus.emit_global_event_msg(f"Run {run_id} is not resumable.")
                return
            if run.status != BenchmarkRunStatus.NOT_COMPLETED:
                self._data_api.update_benchmark_run(dataclasses.replace(run, status=BenchmarkRunStatus.NOT_COMPLETED))
            self._event_bus.emit_run_ids_changed(get_benchmark_runs(self._data_api))
            self._event_bus.emit_run_id_changed(run_id)
            self._benchmark_flow_api.start_execution(run_id)
        except Exception:
            _logger.warning("Failed to resume run %d", run_id, exc_info=True)
            self._event_bus.emit_global_event_msg("Failed to resume run.")

    def is_run_resumable(self, run_id: int) -> bool:
        """Return True when the given run has at least one non-terminal task.

        Args:
            run_id: ID of the benchmark run to check.

        Returns:
            True if the run can be resumed, False otherwise.
        """
        try:
            run = self.get_run(run_id)
            results = self.get_results_for_run(run_id)
            return _is_run_resumable(run, results)
        except Exception:
            _logger.warning("is_run_resumable check failed for run_id=%d", run_id, exc_info=True)
            return False

    def clone_run_for_retry(
        self,
        run_id: int,
        *,
        result_ids_to_retry: list[int] | None = None,
    ) -> int:
        """Create a copy of a run containing only the results selected for retry.

        Args:
            run_id: ID of the original run to copy.
            result_ids_to_retry: Specific result IDs to include.  When None,
                all non-terminal results are selected automatically.

        Returns:
            The run_id of the newly created run.
        """
        original_run = self._data_api.retrieve_benchmark_run(run_id)
        original_results = self._data_api.retrieve_benchmark_results_for_run(run_id)

        if result_ids_to_retry is None:
            retry_ids = {r.result_id for r in original_results if r.status in _RETRYABLE_RESULT_STATUSES}
        else:
            retry_ids = set(result_ids_to_retry)

        now_ts = datetime.now(UTC).isoformat()
        original_label = original_run.run_name or original_run.timestamp
        new_run = dataclasses.replace(
            original_run,
            run_id=0,
            status=BenchmarkRunStatus.NOT_COMPLETED,
            timestamp=now_ts,
            total_tasks=0,
            completed_tasks=0,
            judge_summary=None,
            perf_analysis_result=None,
            run_name=f"Retry of {original_label}",
        )
        new_run_id = self._data_api.create_benchmark_run(new_run)

        new_results: list[BenchmarkResult] = []
        for r in original_results:
            if r.result_id in retry_ids:
                new_results.append(
                    dataclasses.replace(
                        r,
                        result_id=0,
                        run_id=new_run_id,
                        status=BenchmarkResultStatus.NOT_COMPLETED,
                        created_at=now_ts,
                        completed_at=None,
                        raw_response=None,
                        sanitized_response=None,
                        response_char_length=None,
                        has_thinking_block=False,
                        total_time_ms=None,
                        ttft_ms=None,
                        prompt_tokens=None,
                        completion_tokens=None,
                        tokens_per_second=None,
                        rule_check_result=None,
                        rule_check_flag=None,
                        rule_check_resolved=False,
                        keyword_check_result=None,
                        missing_exact_terms=None,
                        found_forbidden_terms=None,
                        semantic_term_scores=None,
                        keyword_check_resolved=False,
                        cosine_similarity=None,
                        cosine_embedding_model=None,
                        cosine_strategy=None,
                        cosine_auto_pass=False,
                        cosine_resolved=False,
                        judge_result=None,
                        judge_score=None,
                        judge_reasoning=None,
                        judge_prompt_template=None,
                        judge_time_ms=None,
                        judge_completion_tokens=None,
                        final_verdict=None,
                        resolution_layer=None,
                        has_inference_error=False,
                        inference_error_message=None,
                        has_judge_error=False,
                        judge_error_message=None,
                    )
                )
            elif r.status == BenchmarkResultStatus.COMPLETED and not r.has_inference_error and not r.has_judge_error:
                new_results.append(dataclasses.replace(r, result_id=0, run_id=new_run_id))

        self._data_api.create_benchmark_results(new_results)

        if original_run.run_mode == RunMode.PROMPT_EVAL:
            original_variants = self._data_api.retrieve_prompt_variants_for_run(run_id)
            for variant in original_variants:
                self._data_api.create_prompt_variant(dataclasses.replace(variant, run_id=new_run_id))

        return new_run_id

    # ------------------------------------------------------------------
    # Readiness probe
    # ------------------------------------------------------------------

    def trigger_readiness_probe(self) -> None:
        """Trigger an async background probe of provider and embedding health.

        Runs on a QThreadPool background thread and emits an
        ``app_readiness_changed`` event once the probe completes.
        The cached snapshot is updated atomically before the event is emitted.
        """
        service = self._readiness_service
        event_bus = self._event_bus

        class _Signals(QObject):
            done: Signal = Signal(AppReadinessChangedEvent)

        class _Worker(QRunnable):
            def __init__(self, *, signals: _Signals) -> None:
                super().__init__()
                self._signals = signals
                self.setAutoDelete(True)

            @Slot()
            def run(self) -> None:
                try:
                    snapshot = service.compute_snapshot()
                    self._signals.done.emit(snapshot)
                except Exception:
                    _logger.warning("readiness_probe_failed", exc_info=True)
                    self._signals.done.emit(
                        AppReadinessChangedEvent(
                            has_any_models=False,
                            embedding_ok=False,
                            embedding_error="Readiness probe failed — check logs.",
                            unhealthy_providers=(),
                        )
                    )

        signals = _Signals()
        self._pending_readiness_signals.append(signals)

        def _on_done(snapshot: AppReadinessChangedEvent) -> None:
            self._last_snapshot = snapshot
            event_bus.emit_app_readiness_changed(snapshot)
            with contextlib.suppress(ValueError):
                self._pending_readiness_signals.remove(signals)

        signals.done.connect(_on_done)
        QThreadPool.globalInstance().start(_Worker(signals=signals))

    def readiness_verdict(self, mode: RunMode) -> ReadinessVerdict:
        """Return the cached readiness verdict for the given run mode.

        If no probe has completed yet, returns a warning verdict indicating
        that the readiness state has not been assessed.

        Args:
            mode: The run mode to evaluate readiness for.

        Returns:
            ReadinessVerdict with is_ready, issues, and severity fields.
        """
        snap = self._last_snapshot
        if snap is None:
            return ReadinessVerdict(
                mode=mode,
                is_ready=False,
                issues=("Readiness not yet checked.",),
                severity="warning",
            )
        return self._readiness_service.verdict_for(mode, snap)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe_to_benchmark_status_change(
        self,
        callback: Callable[[bool], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to benchmark execution start/stop events.

        Args:
            callback: Invoked with True when execution starts, False when it stops.
        """
        self._event_bus.subscribe_to_background_thread_is_running(callback, parent=parent)

    def subscribe_to_runs_change(
        self,
        callback: Callable[[list[tuple[int, str]]], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to changes in the list of available run IDs.

        Args:
            callback: Invoked with updated list of (run_id, timestamp) tuples.
        """
        self._event_bus.subscribe_to_run_ids_changed(callback, parent=parent)

    def subscribe_to_app_readiness_changed(
        self,
        callback: Callable[[AppReadinessChangedEvent], None],
        *,
        parent: QObject | None = None,
    ) -> None:
        """Subscribe to app readiness changed events.

        Args:
            callback: Invoked with the new AppReadinessChangedEvent snapshot each time
                the readiness state is re-evaluated.
        """
        self._event_bus.subscribe_to_app_readiness_changed(callback, parent=parent)

    def get_run_names(self, *, exclude_run_id: int | None = None) -> frozenset[str]:
        """Return the case-folded set of existing run names, optionally excluding one run.

        Args:
            exclude_run_id: Optional run ID whose name should be excluded from the result.

        Returns:
            Frozenset of case-folded run name strings.
        """
        try:
            runs = self._data_api.retrieve_benchmark_runs()
            return frozenset(
                r.run_name.casefold() for r in runs if r.run_name is not None and r.run_id != exclude_run_id
            )
        except Exception:
            _logger.warning("Failed to retrieve run names", exc_info=True)
            return frozenset()

    def rename_run(self, *, run_id: int, new_name: str) -> None:
        """Rename a benchmark run and broadcast the change via the event bus.

        Args:
            run_id: Unique ID of the run to rename.
            new_name: The new display name to assign.
        """
        self._data_api.update_run_name(run_id=run_id, run_name=new_name)
        self._event_bus.emit_run_renamed(RunRenamedEvent(run_id=run_id, new_name=new_name))
        self._event_bus.emit_run_ids_changed(get_benchmark_runs(self._data_api))

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _on_background_changed(self, is_running: bool) -> None:
        if not is_running:
            self._event_bus.emit_run_ids_changed(get_benchmark_runs(self._data_api))

    def _on_provider_health_check(self, event: ProviderHealthCheckEvent) -> None:
        self._provider_health[event.provider_id] = event.is_healthy
