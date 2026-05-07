"""V2 BenchmarkExecutionTask — multi-provider, 4-stage pipeline with pause/resume."""

import dataclasses
import hashlib
import json
import logging
import statistics
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ollama_llm_bench.backend.core.interfaces import (
    AppSettingsServiceApi,
    DataApi,
    EvaluatorApi,
    EventBus,
    JudgePromptServiceApi,
    JudgeSummaryServiceApi,
    LLMJudgeEvaluatorApi,
    LLMProviderApi,
    LogFileWriterApi,
    ProviderRegistryApi,
    TaskFileLoaderApi,
)
from ollama_llm_bench.backend.core.models import (
    BenchmarkFinishedEvent,
    BenchmarkPausedEvent,
    BenchmarkResult,
    BenchmarkResultStatus,
    BenchmarkResumedEvent,
    BenchmarkRun,
    BenchmarkRunStatus,
    BenchmarkStartedEvent,
    BenchmarkStoppedEvent,
    BenchmarkTask,
    EvalLayer,
    EvaluationResult,
    EvalVerdict,
    InferenceResponse,
    InferenceStartedEvent,
    JudgeCompletedEvent,
    JudgeEvalRetryEvent,
    JudgeEvalStartedEvent,
    JudgeStartedEvent,
    JudgeSummaryEvent,
    LogEntryType,
    ModelDescriptor,
    ModelSwitchEvent,
    ModeSwitchEvent,
    PauseReason,
    PerfAnalysisEvent,
    PerformanceConfig,
    PipelineStage,
    ProgressUpdateEvent,
    PromptInputSize,
    PromptOutputSize,
    PromptVariant,
    ProviderHealthCheckEvent,
    ProviderSwitchEvent,
    ReporterStatusMsg,
    RunMode,
    StopReason,
    StreamingChunkEvent,
    TaskCompletedEvent,
    TaskRetryEvent,
    TaskSwitchEvent,
)
from ollama_llm_bench.backend.services.app_settings_service import (
    SETTING_COSINE_ENABLED,
    SETTING_JUDGE_OVERRIDE_COSINE_LOW,
    SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL,
    SETTING_JUDGE_RUN_ANALYSIS_ENABLED,
    SETTING_LOG_TO_FILE,
    SETTING_PAUSE_ON_MODEL_SWITCH,
    SETTING_PAUSE_ON_PROVIDER_SWITCH,
    SETTING_PAUSE_ON_STAGE_SWITCH,
    SETTING_REASONING_EFFORT_DEFAULT,
    SETTING_RETRY_COUNT,
    SETTING_RETRY_TIMEOUT_MAX_S,
    SETTING_RETRY_TIMEOUT_MIN_S,
    SETTING_STOP_ON_PROVIDER_ERROR,
    SETTING_STREAMING_ENABLED,
    SETTING_WARMUP_ENABLED,
)
from ollama_llm_bench.backend.services.performance_task_generator import PerformanceTaskGenerator
from ollama_llm_bench.backend.utils.text_utils import sanitize_text
from ollama_llm_bench.backend.utils.time_utils import format_elapsed_time

logger = logging.getLogger(__name__)

_STREAM_EMIT_INTERVAL_S: float = 0.05  # 20 Hz cap
_ETA_WINDOW_SIZE: int = 10  # rolling average window for ETA computation
_DEFAULT_RETRY_COUNT: int = 3
_DEFAULT_RETRY_TIMEOUT_MIN_S: int = 300  # 5 minutes
_DEFAULT_RETRY_TIMEOUT_MAX_S: int = 900  # 15 minutes


class BenchmarkExecutionTask(QRunnable):
    """V2 benchmark execution task.

    Runs the full 4-stage pipeline (INITIALIZING → BENCHMARKING → JUDGING →
    FINISHED/FAILED) in a background QThreadPool thread.  Emits all V2 EventBus
    events and maintains V1 ``Signals`` for backward-compatibility with
    ``QtBenchmarkFlowApi``.
    """

    class Signals(QObject):
        """Signals emitted for progress and status updates.

        Kept for V1 compatibility — consumed by QtBenchmarkFlowApi.
        """

        status_changed = Signal(bool)  # True = running, False = done
        log_message = Signal(str)  # raw log text for the log widget
        progress = Signal(ReporterStatusMsg)  # legacy progress updates

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        run_id: int,
        data_api: DataApi,
        task_loader: TaskFileLoaderApi,
        judge_prompt_service: JudgePromptServiceApi,
        judge_summary_service: JudgeSummaryServiceApi,
        provider_registry: ProviderRegistryApi,
        event_bus: EventBus,
        app_settings: AppSettingsServiceApi,
        rule_evaluator: EvaluatorApi,
        keyword_evaluator: EvaluatorApi,
        cosine_evaluator: EvaluatorApi,
        llm_judge_evaluator: LLMJudgeEvaluatorApi,
        log_file_writer: LogFileWriterApi,
        perf_task_generator: PerformanceTaskGenerator | None = None,
    ) -> None:
        super().__init__()
        self._run_id = run_id
        self._data_api = data_api
        self._task_loader = task_loader
        self._judge_prompt_service = judge_prompt_service
        self._judge_summary_service = judge_summary_service
        self._provider_registry = provider_registry
        self._event_bus = event_bus
        self._app_settings = app_settings
        self._rule_evaluator = rule_evaluator
        self._keyword_evaluator = keyword_evaluator
        self._cosine_evaluator = cosine_evaluator
        self._llm_judge_evaluator = llm_judge_evaluator
        self._log_file_writer = log_file_writer
        self._perf_task_generator = perf_task_generator

        self.logger = logging.getLogger(f"{__name__}.BenchmarkExecutionTask[{run_id}]")
        self.signals = self.Signals()
        self.setAutoDelete(True)

        # Cancellation / pause
        self._stop_requested: bool = False
        self._pause_event: threading.Event = threading.Event()
        self._pause_event.set()  # set = not paused

        # Per-attempt timeout flag — set by timer, cleared before each retry
        self._attempt_timed_out: bool = False

        # Pipeline state
        self._stage: PipelineStage = PipelineStage.INITIALIZING
        self._current_provider_id: str = ""
        self._current_model: str = ""
        self._current_task_id: str = ""

        # Progress tracking
        self._total_tasks: int = 0
        self._completed_tasks: int = 0
        self._failed_tasks: int = 0
        self._start_time_ms: float = 0.0
        self._task_start_ms: float = 0.0
        self._task_durations: list[float] = []
        self._last_persisted_completed: int = -1
        self._last_persist_time_ms: float = 0.0

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Request graceful cancellation of the benchmark run."""
        if not self._stop_requested:
            self._stop_requested = True
            self._pause_event.set()  # unblock any waiting pause
            self._notify("Stopping benchmark execution...")

    def pause(self) -> None:
        """Pause execution at the next stage boundary."""
        self._pause_event.clear()
        self._event_bus.emit_benchmark_paused(
            BenchmarkPausedEvent(
                run_id=self._run_id,
                pause_reason=PauseReason.USER,
                paused_at_stage=self._stage,
            )
        )

    def resume(self) -> None:
        """Resume a paused benchmark run."""
        self._pause_event.set()
        self._event_bus.emit_benchmark_resumed(BenchmarkResumedEvent(run_id=self._run_id))

    def is_stopped(self) -> bool:
        """Return True if a stop has been requested."""
        return self._stop_requested

    def _on_task_timeout(self, task_id: str, model_name: str) -> None:
        """Called from a background threading.Timer when an inference attempt exceeds its deadline."""
        self.logger.warning(
            "task_timeout_fired",
            extra={"task_id": task_id, "model": model_name},
        )
        self._attempt_timed_out = True

    # ------------------------------------------------------------------
    # QRunnable entry point
    # ------------------------------------------------------------------

    @Slot()
    def run(self) -> None:
        """Execute the benchmark pipeline on the background thread."""
        self._start_time_ms = time.monotonic() * 1000.0
        self.signals.status_changed.emit(True)
        self._emit_legacy_progress()

        try:
            run = self._data_api.retrieve_benchmark_run(self._run_id)

            # --- INITIALIZING ---
            tasks_map = self._stage_initializing(run)
            if not self._check_pause_or_stop():
                return

            # --- BENCHMARKING ---
            self._emit_mode_switch(PipelineStage.INITIALIZING, PipelineStage.BENCHMARKING)
            self._stage = PipelineStage.BENCHMARKING
            if not self._stage_benchmarking(run, tasks_map):
                return

            # --- JUDGING ---
            _judge_override_keyword = self._app_settings.get_bool(SETTING_JUDGE_OVERRIDE_KEYWORD_FAIL)
            _judge_override_cosine = self._app_settings.get_bool(SETTING_JUDGE_OVERRIDE_COSINE_LOW)
            _judge_run_analysis = self._app_settings.get_bool(SETTING_JUDGE_RUN_ANALYSIS_ENABLED)
            _should_judge = (
                run.run_mode not in (RunMode.SPEED, RunMode.PERFORMANCE)
                or _judge_override_keyword
                or _judge_override_cosine
            )
            if _should_judge:
                self._emit_mode_switch(PipelineStage.BENCHMARKING, PipelineStage.JUDGING)
                self._stage = PipelineStage.JUDGING
                if self._app_settings.get_bool(SETTING_PAUSE_ON_STAGE_SWITCH):
                    self._event_bus.emit_benchmark_paused(
                        BenchmarkPausedEvent(
                            run_id=self._run_id,
                            pause_reason=PauseReason.EVENT_POLICY,
                            paused_at_stage=self._stage,
                        )
                    )
                    if not self._check_pause_or_stop():
                        return
                self._check_embedding_provider_health()
                self._stage_judging(
                    run,
                    judge_override_keyword_fail=_judge_override_keyword,
                    judge_override_cosine_low=_judge_override_cosine,
                )

            if _judge_run_analysis and run.run_mode in (RunMode.SPEED, RunMode.PERFORMANCE):
                if run.judge_provider_id and run.judge_model:
                    self._stage_performance_analysis(run)
                else:
                    self._notify_warn(
                        "Run-level analysis skipped: no judge model configured. "
                        "Pick a judge in the Run Configuration panel."
                    )
            elif run.run_mode == RunMode.FULL_GRADING:
                self._generate_and_emit_judge_summary(run)

            self._stage = PipelineStage.FINISHED
            self._notify(f"Benchmark run #{self._run_id} finished.")
            self._write_log_entry(
                LogEntryType.SYSTEM,
                f"Benchmark run #{self._run_id} finished — {self._completed_tasks} completed, {self._failed_tasks} failed",
            )

        except Exception as exc:
            self.logger.exception("benchmark_run_fatal_error")
            self._notify_warn(f"Fatal error: {exc}")
            self._stage = PipelineStage.FAILED
        finally:
            end_time_ms = time.monotonic() * 1000.0
            total_ms = end_time_ms - self._start_time_ms

            if self._stage == PipelineStage.FINISHED:
                self._persist_run_terminal(BenchmarkRunStatus.COMPLETED, self._completed_tasks)
            elif self._stage == PipelineStage.FAILED:
                self._persist_run_terminal(BenchmarkRunStatus.FAILED, self._completed_tasks)

            if self._stop_requested and self._stage not in (PipelineStage.FINISHED, PipelineStage.FAILED):
                self._event_bus.emit_benchmark_stopped(
                    BenchmarkStoppedEvent(
                        run_id=self._run_id,
                        stop_reason=StopReason.USER,
                    )
                )
            else:
                self._event_bus.emit_benchmark_finished(
                    BenchmarkFinishedEvent(
                        run_id=self._run_id,
                        total_time_ms=total_ms,
                        completed_count=self._completed_tasks,
                        failed_count=self._failed_tasks,
                    )
                )

            if self._app_settings.get_bool(SETTING_LOG_TO_FILE):
                try:
                    self._log_file_writer.close(self._run_id)
                except Exception:
                    self.logger.warning("log_file_close_failed")

            self._stop_requested = True
            self.signals.status_changed.emit(False)
            self._emit_legacy_progress()
            self._notify(format_elapsed_time(self._start_time_ms / 1000.0, end_time_ms / 1000.0))

    # ------------------------------------------------------------------
    # Judge summary
    # ------------------------------------------------------------------

    def _generate_and_emit_judge_summary(self, run: BenchmarkRun) -> None:
        """Call the judge summary service, persist the result to the DB, then emit the event."""
        try:
            all_results = self._data_api.retrieve_benchmark_results_for_run(run.run_id)
            summary_text = self._judge_summary_service.generate_summary(run=run, results=all_results)
            updated_run = dataclasses.replace(run, judge_summary=summary_text)
            self._data_api.update_benchmark_run(updated_run)
            self._event_bus.emit_judge_summary(JudgeSummaryEvent(run_id=self._run_id, summary_text=summary_text))
        except Exception as exc:
            self.logger.warning("judge_summary_failed", extra={"error": str(exc)})

    # ------------------------------------------------------------------
    # Run-state persistence helpers
    # ------------------------------------------------------------------

    def _persist_run_total(self, total: int) -> None:
        try:
            run = self._data_api.retrieve_benchmark_run(self._run_id)
            self._data_api.update_benchmark_run(dataclasses.replace(run, total_tasks=total))
        except Exception:
            self.logger.warning("persist_run_total_failed", extra={"run_id": self._run_id})

    def _persist_run_completed(self, completed: int) -> None:
        try:
            run = self._data_api.retrieve_benchmark_run(self._run_id)
            self._data_api.update_benchmark_run(dataclasses.replace(run, completed_tasks=completed))
        except Exception:
            self.logger.warning("persist_run_completed_failed", extra={"run_id": self._run_id})

    def _persist_run_terminal(self, status: BenchmarkRunStatus, completed: int) -> None:
        try:
            run = self._data_api.retrieve_benchmark_run(self._run_id)
            self._data_api.update_benchmark_run(dataclasses.replace(run, status=status, completed_tasks=completed))
        except Exception:
            self.logger.warning("persist_run_terminal_failed", extra={"run_id": self._run_id})

    def _maybe_persist_progress(self) -> None:
        now_ms = time.monotonic() * 1000.0
        delta = self._completed_tasks - self._last_persisted_completed
        elapsed_ms = now_ms - self._last_persist_time_ms
        if delta >= 5 or elapsed_ms >= 5000.0:
            self._persist_run_completed(self._completed_tasks)
            self._last_persisted_completed = self._completed_tasks
            self._last_persist_time_ms = now_ms

    # ------------------------------------------------------------------
    # Stage: INITIALIZING
    # ------------------------------------------------------------------

    def _stage_initializing(self, run: BenchmarkRun) -> dict[str, BenchmarkTask]:
        """Load tasks, create missing result rows, emit BenchmarkStartedEvent.

        Returns:
            Mapping of task_id → BenchmarkTask for use in later stages.
        """
        self._notify("Initializing benchmark run...")

        # Load task definitions — use generator for PERFORMANCE mode, YAML otherwise
        if run.run_mode == RunMode.PERFORMANCE and self._perf_task_generator is not None:
            perf_config = self._parse_performance_config(run.performance_config)
            task_list = self._perf_task_generator.generate(perf_config) if perf_config else []
        else:
            file_paths = [Path(p) for p in run.task_file_paths]
            task_list = self._task_loader.load_tasks(file_paths)
        tasks_map: dict[str, BenchmarkTask] = {t.task_id: t for t in task_list}

        # Parse model descriptors stored in models_json
        descriptors = self._parse_model_descriptors(run.models_json)
        descriptors = self._enrich_descriptor_provider_types(descriptors)

        # Create result rows — strategy differs by run mode
        if run.run_mode == RunMode.PROMPT_EVAL:
            tasks_map = self._stage_initializing_prompt_eval(run, task_list, descriptors)
        else:
            # Resumability: only create rows that don't already exist
            if descriptors and task_list:
                existing = self._data_api.retrieve_benchmark_results_for_run(self._run_id)
                existing_keys = {(r.provider_id, r.model_name, r.task_id) for r in existing}
                new_rows = [
                    self._build_initial_result(run, desc, task)
                    for desc in descriptors
                    for task in task_list
                    if (desc.provider_id, desc.model_name, task.task_id) not in existing_keys
                ]
                if new_rows:
                    self._data_api.create_benchmark_results(new_rows)
                    self._notify(f"Created {len(new_rows)} result rows.")
            tasks_map = {t.task_id: t for t in task_list}

        # Refresh total task count after potential row creation.
        # In full_grading/prompt_eval modes each result row goes through two phases
        # (inference + judge), so the logical total is doubled.
        all_results = self._data_api.retrieve_benchmark_results_for_run(self._run_id)
        phases = 2 if run.run_mode in (RunMode.FULL_GRADING, RunMode.PROMPT_EVAL) else 1
        self._total_tasks = len(all_results) * phases
        self._persist_run_total(self._total_tasks)

        self._event_bus.emit_benchmark_started(
            BenchmarkStartedEvent(
                run_id=self._run_id,
                total_tasks=self._total_tasks,
                models=tuple(descriptors),
                run_mode=run.run_mode,
            )
        )
        self._emit_progress()
        return tasks_map

    def _stage_initializing_prompt_eval(
        self,
        run: BenchmarkRun,
        task_list: list[BenchmarkTask],
        descriptors: list[ModelDescriptor],
    ) -> dict[str, BenchmarkTask]:
        """Create variant x task result rows for prompt_eval mode.

        Returns:
            Mapping of task_id → BenchmarkTask for use in later stages.
        """
        variants = self._data_api.retrieve_prompt_variants_for_run(self._run_id)
        if not variants:
            self._notify_warn("Prompt eval mode: no variants found for this run.")
            return {t.task_id: t for t in task_list}

        desc = descriptors[0] if descriptors else None
        if desc is None:
            self._notify_warn("Prompt eval mode: no model descriptor found.")
            return {t.task_id: t for t in task_list}

        existing = self._data_api.retrieve_benchmark_results_for_run(self._run_id)
        existing_keys = {(r.provider_id, r.model_name, r.task_id, r.prompt_version) for r in existing}

        new_rows = [
            self._build_prompt_eval_result(run, desc, task, variant)
            for variant in variants
            for task in task_list
            if (desc.provider_id, desc.model_name, task.task_id, variant.variant_id) not in existing_keys
        ]
        if new_rows:
            self._data_api.create_benchmark_results(new_rows)
            self._notify(f"Created {len(new_rows)} prompt-eval result rows.")

        return {t.task_id: t for t in task_list}

    # ------------------------------------------------------------------
    # Stage: BENCHMARKING
    # ------------------------------------------------------------------

    def _stage_benchmarking(self, run: BenchmarkRun, tasks_map: dict[str, BenchmarkTask]) -> bool:
        """Run inference for all NOT_COMPLETED results.

        Returns:
            True if the stage completed (or had nothing to do); False if stopped.
        """
        pending = self._data_api.retrieve_benchmark_results_for_run_with_status(
            run_id=self._run_id, status=BenchmarkResultStatus.NOT_COMPLETED
        )
        all_results = self._data_api.retrieve_benchmark_results_for_run(self._run_id)
        bench_done = len(all_results) - len(pending)
        judge_done = sum(1 for r in all_results if r.status == BenchmarkResultStatus.COMPLETED)
        self._completed_tasks = bench_done + judge_done
        self._maybe_persist_progress()

        if not pending:
            self._notify(f"Resume: all {len(all_results)} benchmark tasks already complete — skipping inference phase.")
            return True

        self._notify(f"Benchmarking {len(pending)} tasks...")

        by_provider: dict[str, list[BenchmarkResult]] = defaultdict(list)
        for r in pending:
            by_provider[r.provider_id].append(r)

        prev_provider_id: str | None = None
        for provider_id, provider_results in by_provider.items():
            if not self._check_pause_or_stop():
                return False

            provider = self._provider_registry.get_provider(provider_id)
            self._current_provider_id = provider_id

            self._event_bus.emit_provider_switch(
                ProviderSwitchEvent(
                    run_id=self._run_id,
                    from_provider_id=prev_provider_id,
                    to_provider_id=provider_id,
                    provider_label=provider_id,
                )
            )
            if self._app_settings.get_bool(SETTING_PAUSE_ON_PROVIDER_SWITCH):
                self._event_bus.emit_benchmark_paused(
                    BenchmarkPausedEvent(
                        run_id=self._run_id,
                        pause_reason=PauseReason.EVENT_POLICY,
                        paused_at_stage=self._stage,
                    )
                )
                if not self._check_pause_or_stop():
                    return False

            # Health check
            if not self._run_health_check(provider, provider_id):
                return False

            # Group by model_name
            by_model: dict[str, list[BenchmarkResult]] = defaultdict(list)
            for r in provider_results:
                by_model[r.model_name].append(r)

            prev_model: str | None = None
            for model_name, model_results in by_model.items():
                if not self._check_pause_or_stop():
                    return False

                self._write_log_entry(LogEntryType.SYSTEM, f"Benchmarking model={model_name}")
                first = model_results[0]
                model_desc = ModelDescriptor(
                    provider_id=first.provider_id,
                    provider_type=first.provider_type,
                    model_name=model_name,
                    display_label=f"{first.provider_id} / {model_name}",
                )
                self._current_model = model_name

                self._event_bus.emit_model_switch(
                    ModelSwitchEvent(
                        run_id=self._run_id,
                        from_model=prev_model,
                        to_model=model_desc,
                    )
                )
                if self._app_settings.get_bool(SETTING_PAUSE_ON_MODEL_SWITCH):
                    self._event_bus.emit_benchmark_paused(
                        BenchmarkPausedEvent(
                            run_id=self._run_id,
                            pause_reason=PauseReason.EVENT_POLICY,
                            paused_at_stage=self._stage,
                        )
                    )
                    if not self._check_pause_or_stop():
                        return False

                # Warm-up
                if self._app_settings.get_bool(SETTING_WARMUP_ENABLED):
                    self._warm_up_model(provider, model_name)

                total_for_model = len(model_results)
                for task_number, result in enumerate(model_results, start=1):
                    if not self._check_pause_or_stop():
                        return False

                    self._current_task_id = result.task_id
                    self._task_start_ms = time.monotonic() * 1000.0
                    task = tasks_map.get(result.task_id)
                    if task is None:
                        self._notify_warn(f"Task {result.task_id} not in loader cache — skipping")
                        self._mark_failed(result, RuntimeError("Task definition not found"))
                        self._emit_progress()
                        continue

                    self._event_bus.emit_task_switch(
                        TaskSwitchEvent(
                            run_id=self._run_id,
                            model=model_desc,
                            task_id=task.task_id,
                            task_category=task.category or task.task_id.split("_")[0],
                            task_type=task.task_type,
                            task_number=task_number,
                            tasks_total=total_for_model,
                        )
                    )

                    self._write_log_entry(
                        LogEntryType.TASK_START,
                        f"task={result.task_id} model={model_name}",
                    )
                    task_start = time.monotonic()
                    try:
                        status_after = (
                            BenchmarkResultStatus.COMPLETED
                            if run.run_mode in (RunMode.SPEED, RunMode.PERFORMANCE)
                            else BenchmarkResultStatus.WAITING_FOR_JUDGE
                        )
                        updated = self._run_inference_with_retry(provider, model_name, result, task, status_after)
                        self._data_api.update_benchmark_result(updated)
                        self._completed_tasks += 1
                        self._maybe_persist_progress()
                        duration_ms = (time.monotonic() - task_start) * 1000.0
                        self._record_task_duration(duration_ms)
                        self._event_bus.emit_task_completed(
                            TaskCompletedEvent(
                                run_id=self._run_id,
                                result_id=updated.result_id,
                                model=model_desc,
                                task_id=task.task_id,
                                status=updated.status,
                                total_time_ms=float(updated.total_time_ms) if updated.total_time_ms else None,
                                ttft_ms=float(updated.ttft_ms) if updated.ttft_ms else None,
                                final_verdict=updated.final_verdict,
                            )
                        )
                        self._write_log_entry(
                            LogEntryType.INFERENCE_COMPLETE,
                            f"task={task.task_id} total_time_ms={updated.total_time_ms} verdict={updated.final_verdict}",
                        )
                    except StopIteration:
                        return False
                    except Exception as exc:
                        self._notify_warn(f"Inference failed for task {result.task_id}: {exc}")
                        self._mark_failed(result, exc)

                    self._emit_progress()

                prev_model = model_name
            prev_provider_id = provider_id

        self._write_log_entry(LogEntryType.SYSTEM, "Benchmarking phase complete")
        return True

    # ------------------------------------------------------------------
    # Stage: JUDGING
    # ------------------------------------------------------------------

    def _stage_judging(
        self,
        run: BenchmarkRun,
        *,
        judge_override_keyword_fail: bool = False,
        judge_override_cosine_low: bool = False,
    ) -> None:
        """Run the 4-layer evaluation pipeline for all WAITING_FOR_JUDGE results.

        Args:
            run: The benchmark run being evaluated.
            judge_override_keyword_fail: When True, also invoke the LLM judge for
                results where the keyword layer produced a terminal verdict.
            judge_override_cosine_low: When True, also invoke the LLM judge for
                results where the cosine layer produced a terminal verdict.
        """
        self._notify("=== JUDGING PHASE ===")
        self._write_log_entry(LogEntryType.SYSTEM, "Judging phase started")
        to_judge = self._data_api.retrieve_benchmark_results_for_run_with_status(
            run_id=self._run_id, status=BenchmarkResultStatus.WAITING_FOR_JUDGE
        )

        if not to_judge:
            all_results = self._data_api.retrieve_benchmark_results_for_run(self._run_id)
            self._notify(f"Resume: all {len(all_results)} judge evaluations already complete — skipping judge phase.")
            return

        self._notify(f"Judging {len(to_judge)} results...")
        results_total = len(to_judge)

        for result_number, result in enumerate(to_judge, start=1):
            if not self._check_pause_or_stop():
                return

            self._current_task_id = result.task_id
            self._current_model = run.judge_model or ""
            self._current_provider_id = run.judge_provider_id or ""
            self._task_start_ms = time.monotonic() * 1000.0

            try:
                task = self._task_loader.get_task(result.task_id)
            except KeyError:
                self._notify_warn(f"Task {result.task_id} not found in cache — skipping judge")
                self._mark_judge_failed(result, RuntimeError("Task definition not found"))
                self._emit_progress()
                continue

            self._event_bus.emit_judge_eval_started(
                JudgeEvalStartedEvent(
                    run_id=self._run_id,
                    result_id=result.result_id,
                    task_id=result.task_id,
                    task_type=task.task_type,
                    judge_provider_id=run.judge_provider_id or "",
                    judge_model=run.judge_model or "",
                    result_number=result_number,
                    results_total=results_total,
                )
            )
            self._emit_progress()

            try:
                updated = self._run_eval_pipeline(
                    task,
                    result,
                    run,
                    judge_override_keyword_fail=judge_override_keyword_fail,
                    judge_override_cosine_low=judge_override_cosine_low,
                )
                self._data_api.update_benchmark_result(updated)
                self._completed_tasks += 1
                self._maybe_persist_progress()
            except Exception as exc:
                self._notify_warn(f"Eval pipeline failed for {result.task_id}: {exc}")
                self._mark_judge_failed(result, exc)

            self._emit_progress()

    # ------------------------------------------------------------------
    # Inference helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_attempt_timeout(min_s: int, max_s: int, attempt: int, total_attempts: int) -> int:
        """Return the timeout in seconds for a given retry attempt using exponential growth.

        Args:
            min_s: Timeout for the first attempt (attempt=0).
            max_s: Timeout ceiling for the last attempt.
            attempt: Zero-indexed attempt number.
            total_attempts: Total number of attempts configured.

        Returns:
            Timeout in whole seconds, clamped between min_s and max_s.
        """
        if total_attempts <= 1:
            return min_s
        exponent = attempt / (total_attempts - 1)
        ratio: float = max_s / min_s
        scaled: float = min_s * ratio**exponent
        clamped: int = max(min_s, min(max_s, round(scaled)))
        return clamped

    def _run_inference_with_retry(
        self,
        provider: "LLMProviderApi",
        model_name: str,
        result: BenchmarkResult,
        task: BenchmarkTask,
        status_after: BenchmarkResultStatus,
    ) -> BenchmarkResult:
        """Run inference with exponential retry on timeout.

        Wraps _run_inference in a retry loop.  On each attempt a threading.Timer
        sets _attempt_timed_out; when the inference call returns the flag is
        inspected.  If timed out and retries remain, the attempt is logged and
        the next attempt starts with a larger timeout.  After all retries are
        exhausted a TimeoutError is raised so the caller can mark the task FAILED.

        Args:
            provider: LLM provider to call.
            model_name: Model identifier.
            result: Current BenchmarkResult being updated.
            task: BenchmarkTask providing the prompt.
            status_after: Status to set on a successful inference.

        Returns:
            Updated BenchmarkResult on success.

        Raises:
            TimeoutError: When every retry attempt times out.
        """
        retry_count = self._app_settings.get_int(SETTING_RETRY_COUNT)
        min_s = self._app_settings.get_int(SETTING_RETRY_TIMEOUT_MIN_S)
        max_s = self._app_settings.get_int(SETTING_RETRY_TIMEOUT_MAX_S)
        retry_count = max(1, retry_count)

        for attempt in range(retry_count):
            if not self._check_pause_or_stop():
                raise StopIteration

            if attempt > 0:
                self._event_bus.emit_task_retry(
                    TaskRetryEvent(
                        run_id=self._run_id,
                        task_id=result.task_id,
                        attempt=attempt + 1,
                        total_attempts=retry_count,
                    )
                )

            timeout_s = self._calc_attempt_timeout(min_s, max_s, attempt, retry_count)
            self.logger.info(
                "inference_attempt",
                extra={"task_id": result.task_id, "model": model_name, "attempt": attempt + 1, "timeout_s": timeout_s},
            )
            self._attempt_timed_out = False
            timer = threading.Timer(timeout_s, self._on_task_timeout, args=[result.task_id, model_name])
            timer.start()
            try:
                updated = self._run_inference(provider, model_name, result, task, status_after)
            finally:
                timer.cancel()

            if not self._attempt_timed_out:
                return updated

            self.logger.warning(
                "inference_attempt_timed_out",
                extra={"task_id": result.task_id, "model": model_name, "attempt": attempt + 1, "timeout_s": timeout_s},
            )
            self._notify_warn(
                f"Task '{result.task_id}' attempt {attempt + 1}/{retry_count} timed out ({timeout_s}s) for {model_name}."
            )

        raise TimeoutError(f"Task timed out after {retry_count} attempt(s) — last timeout was {max_s}s")

    def _run_judge_with_retry(
        self,
        judge_evaluator: LLMJudgeEvaluatorApi,
        task: BenchmarkTask,
        result: BenchmarkResult,
        run: BenchmarkRun,
    ) -> EvaluationResult:
        """Run the LLM judge call with exponential retry on timeout, mirroring _run_inference_with_retry.

        Args:
            judge_evaluator: LLM judge evaluator to call.
            task: Benchmark task definition.
            result: Current BenchmarkResult being evaluated.
            run: Parent BenchmarkRun providing judge provider and model.

        Returns:
            EvaluationResult from the judge, or a terminal UNKNOWN result after all retries.

        Raises:
            TimeoutError: When every retry attempt times out.
        """
        retry_count = max(1, self._app_settings.get_int(SETTING_RETRY_COUNT))
        min_s = self._app_settings.get_int(SETTING_RETRY_TIMEOUT_MIN_S)
        max_s = self._app_settings.get_int(SETTING_RETRY_TIMEOUT_MAX_S)
        judge_model = run.judge_model or ""

        for attempt in range(retry_count):
            if not self._check_pause_or_stop():
                raise StopIteration

            if attempt > 0:
                self._event_bus.emit_judge_eval_retry(
                    JudgeEvalRetryEvent(
                        run_id=self._run_id,
                        task_id=result.task_id,
                        judge_model=judge_model,
                        attempt=attempt + 1,
                        total_attempts=retry_count,
                    )
                )

            timeout_s = self._calc_attempt_timeout(min_s, max_s, attempt, retry_count)
            self._attempt_timed_out = False
            timer = threading.Timer(timeout_s, self._on_task_timeout, args=[result.task_id, judge_model])
            timer.start()
            try:
                eval_result = judge_evaluator.evaluate(
                    task,
                    result,
                    judge_provider_id=run.judge_provider_id,
                    judge_model=judge_model,
                )
            finally:
                timer.cancel()

            if not self._attempt_timed_out:
                return eval_result

            self.logger.warning(
                "judge_attempt_timed_out",
                extra={"task_id": result.task_id, "model": judge_model, "attempt": attempt + 1, "timeout_s": timeout_s},
            )
            self._notify_warn(
                f"Judge '{result.task_id}' attempt {attempt + 1}/{retry_count} timed out ({timeout_s}s) for {judge_model}."
            )

        raise TimeoutError(f"Judge timed out after {retry_count} attempt(s) — last timeout was {max_s}s")

    def _run_inference(
        self,
        provider: LLMProviderApi,
        model_name: str,
        result: BenchmarkResult,
        task: BenchmarkTask,
        status_after: BenchmarkResultStatus,
    ) -> BenchmarkResult:
        """Run inference (streaming or sync) and return an updated BenchmarkResult."""
        if result.user_prompt_sent:
            user_prompt = result.user_prompt_sent
            system_prompt = result.system_prompt_sent
        else:
            user_prompt, system_prompt = self._judge_prompt_service.build_inference_prompt(task)

        self._event_bus.emit_inference_started(
            InferenceStartedEvent(
                run_id=self._run_id,
                result_id=result.result_id,
                model=ModelDescriptor(
                    provider_id=result.provider_id,
                    provider_type=result.provider_type,
                    model_name=model_name,
                    display_label=f"{result.provider_id}/{model_name}",
                ),
                task_id=result.task_id,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                stage=self._stage,
            )
        )

        messages = self._build_messages(user_prompt, system_prompt or "")

        use_streaming = self._app_settings.get_bool(SETTING_STREAMING_ENABLED) and provider.supports_streaming()
        reasoning_effort = self._app_settings.get(SETTING_REASONING_EFFORT_DEFAULT) or "medium"

        if use_streaming:
            inference_resp = self._run_streaming_inference(provider, model_name, result, messages, reasoning_effort)
        else:
            inference_resp = provider.inference_sync(
                model=model_name, messages=messages, temperature=0.7, reasoning_effort=reasoning_effort
            )

        raw = inference_resp.llm_response or ""
        has_thinking = "<think>" in raw
        prompt_hash = "sha256:" + hashlib.sha256(user_prompt.encode()).hexdigest()
        sanitized = sanitize_text(raw)
        tps: float | None = None
        if inference_resp.total_time_ms and inference_resp.completion_tokens:
            tps = inference_resp.completion_tokens / (inference_resp.total_time_ms / 1000.0)

        return dataclasses.replace(
            result,
            status=status_after,
            user_prompt_sent=user_prompt,
            system_prompt_sent=system_prompt or None,
            raw_response=raw,
            sanitized_response=sanitized,
            response_char_length=len(sanitized),
            has_thinking_block=has_thinking,
            prompt_hash=prompt_hash,
            total_time_ms=inference_resp.total_time_ms or None,
            ttft_ms=inference_resp.ttft_ms,
            completion_tokens=inference_resp.completion_tokens or None,
            prompt_tokens=inference_resp.prompt_tokens,
            tokens_per_second=tps,
            has_inference_error=inference_resp.has_error,
            inference_error_message=inference_resp.error_message,
        )

    def _run_streaming_inference(
        self,
        provider: LLMProviderApi,
        model_name: str,
        result: BenchmarkResult,
        messages: list[dict[str, str]],
        reasoning_effort: str = "medium",
    ) -> InferenceResponse:
        """Stream inference with 20 Hz buffered chunk emission.

        Returns:
            Final InferenceResponse from the generator's return value.
        """
        gen = provider.inference_stream(
            model=model_name, messages=messages, temperature=0.7, reasoning_effort=reasoning_effort
        )
        buffer: list[str] = []
        last_emit = time.monotonic()
        final_response: InferenceResponse | None = None

        try:
            while True:
                if self._stop_requested or self._attempt_timed_out:
                    gen.close()
                    break
                chunk = next(gen)
                if chunk.delta_content:
                    buffer.append(chunk.delta_content)
                    now = time.monotonic()
                    if now - last_emit >= _STREAM_EMIT_INTERVAL_S:
                        self._flush_chunk_buffer(buffer, result.result_id, model_name, result.task_id)
                        buffer.clear()
                        last_emit = now
        except StopIteration as exc:
            final_response = exc.value

        if buffer:
            self._flush_chunk_buffer(buffer, result.result_id, model_name, result.task_id)

        return final_response or InferenceResponse(
            has_error=True,
            error_message="No response received from streaming inference",
        )

    def _flush_chunk_buffer(
        self,
        buffer: list[str],
        result_id: int,
        model_name: str,
        task_id: str,
    ) -> None:
        """Emit buffered stream chunks as a single StreamingChunkEvent."""
        if not buffer:
            return
        self._event_bus.emit_streaming_chunk(
            StreamingChunkEvent(
                run_id=self._run_id,
                result_id=result_id,
                model_name=model_name,
                task_id=task_id,
                chunk_text="".join(buffer),
                is_thinking_block=False,
            )
        )

    # ------------------------------------------------------------------
    # Evaluation pipeline
    # ------------------------------------------------------------------

    def _run_eval_pipeline(
        self,
        task: BenchmarkTask,
        result: BenchmarkResult,
        run: BenchmarkRun,
        *,
        judge_override_keyword_fail: bool = False,
        judge_override_cosine_low: bool = False,
    ) -> BenchmarkResult:
        """Run the 4-layer evaluation pipeline and return a fully annotated result.

        Args:
            task: The benchmark task definition.
            result: The current BenchmarkResult awaiting evaluation.
            run: The parent BenchmarkRun (provides judge provider/model).
            judge_override_keyword_fail: When True, invoke the LLM judge even if
                the keyword layer produced a terminal verdict.
            judge_override_cosine_low: When True, invoke the LLM judge even if
                the cosine layer produced a terminal verdict.
        """
        accumulated: dict[str, Any] = {}
        layers: list[tuple[EvaluatorApi | None, LLMJudgeEvaluatorApi | None]] = [
            (self._rule_evaluator, None),
            (self._keyword_evaluator, None),
            (self._cosine_evaluator, None),
            (None, self._llm_judge_evaluator),
        ]

        for evaluator, judge_evaluator in layers:
            layer = evaluator.layer if evaluator is not None else cast(LLMJudgeEvaluatorApi, judge_evaluator).layer

            self._event_bus.emit_judge_started(
                JudgeStartedEvent(
                    run_id=self._run_id,
                    result_id=result.result_id,
                    layer=layer,
                )
            )

            if judge_evaluator is not None:
                eval_result = self._run_judge_with_retry(judge_evaluator, task, result, run)
            else:
                eval_result = cast(EvaluatorApi, evaluator).evaluate(task, result)

            self._accumulate_layer_result(accumulated, layer, eval_result)

            if layer == EvalLayer.COSINE and eval_result.verdict != EvalVerdict.UNKNOWN:
                accumulated["cosine_embedding_model"] = run.embedding_model

            self._event_bus.emit_judge_completed(
                JudgeCompletedEvent(
                    run_id=self._run_id,
                    result_id=result.result_id,
                    layer=layer,
                    verdict=eval_result.verdict,
                    resolved=eval_result.is_terminal,
                    task_id=result.task_id,
                    reasoning=eval_result.reasoning,
                    score=eval_result.score,
                )
            )
            self._write_log_entry(
                LogEntryType.JUDGE_RESULT,
                f"task={result.task_id} model={result.model_name} layer={layer} verdict={eval_result.verdict} resolved={eval_result.is_terminal}",
            )

            if eval_result.is_terminal:
                accumulated["final_verdict"] = str(eval_result.verdict)
                accumulated["resolution_layer"] = str(layer)

                # Override: continue to LLM judge even though a prior layer resolved
                _keyword_overridden = layer == EvalLayer.KEYWORD and judge_override_keyword_fail
                _cosine_overridden = layer == EvalLayer.COSINE and judge_override_cosine_low
                if _keyword_overridden or _cosine_overridden:
                    self._write_log_entry(
                        LogEntryType.JUDGE_RESULT,
                        f"task={result.task_id} judge_override applied after {layer} "
                        f"(keyword_fail={judge_override_keyword_fail} cosine_low={judge_override_cosine_low})",
                    )
                    self.logger.debug(
                        "judge_override",
                        extra={"task_id": result.task_id, "resolved_by": str(layer)},
                    )
                    # Continue to next layer (LLM judge) without breaking
                    continue

                break

        return dataclasses.replace(result, status=BenchmarkResultStatus.COMPLETED, **accumulated)

    @staticmethod
    def _accumulate_layer_result(
        accumulated: dict[str, Any],
        layer: EvalLayer,
        eval_result: EvaluationResult,
    ) -> None:
        """Write evaluation layer results into the accumulated dict."""
        if layer == EvalLayer.RULE_BASED:
            accumulated["rule_check_result"] = str(eval_result.verdict)
            accumulated["rule_check_flag"] = eval_result.reasoning
            accumulated["rule_check_resolved"] = eval_result.is_terminal
        elif layer == EvalLayer.KEYWORD:
            accumulated["keyword_check_result"] = str(eval_result.verdict)
            accumulated["keyword_check_resolved"] = eval_result.is_terminal
            if eval_result.missing_exact_terms:
                accumulated["missing_exact_terms"] = ", ".join(eval_result.missing_exact_terms)
            if eval_result.found_forbidden_terms:
                accumulated["found_forbidden_terms"] = ", ".join(eval_result.found_forbidden_terms)
            if eval_result.semantic_term_scores:
                accumulated["semantic_term_scores"] = ", ".join(f"{s:.4f}" for s in eval_result.semantic_term_scores)
        elif layer == EvalLayer.COSINE:
            accumulated["cosine_similarity"] = eval_result.score if eval_result.verdict != EvalVerdict.UNKNOWN else None
            accumulated["cosine_strategy"] = eval_result.reasoning
            accumulated["cosine_resolved"] = eval_result.is_terminal
            accumulated["cosine_auto_pass"] = eval_result.verdict == EvalVerdict.PASS
        elif layer == EvalLayer.LLM_JUDGE:
            accumulated["judge_result"] = str(eval_result.verdict)
            accumulated["judge_score"] = eval_result.score
            accumulated["judge_reasoning"] = eval_result.reasoning
            if eval_result.judge_time_ms is not None:
                accumulated["judge_time_ms"] = eval_result.judge_time_ms
            if eval_result.judge_completion_tokens is not None:
                accumulated["judge_completion_tokens"] = eval_result.judge_completion_tokens
            if eval_result.judge_prompt_template is not None:
                accumulated["judge_prompt_template"] = eval_result.judge_prompt_template

    # ------------------------------------------------------------------
    # Progress / legacy signal helpers
    # ------------------------------------------------------------------

    def _emit_progress(self) -> None:
        """Emit ProgressUpdateEvent and legacy ReporterStatusMsg."""
        now_ms = time.monotonic() * 1000.0
        self._event_bus.emit_progress_update(
            ProgressUpdateEvent(
                run_id=self._run_id,
                stage=self._stage,
                current_provider=self._current_provider_id,
                current_model=self._current_model,
                current_task=self._current_task_id,
                tasks_completed=self._completed_tasks,
                tasks_total=self._total_tasks,
                start_time_ms=self._start_time_ms,
                current_time_ms=now_ms,
                estimated_remaining_ms=self._compute_eta(),
                task_start_ms=self._task_start_ms,
            )
        )
        self._emit_legacy_progress()

    def _emit_legacy_progress(self) -> None:
        """Emit V1-compatible ReporterStatusMsg progress signal."""
        end_time = time.monotonic() * 1000.0
        status_msg = ReporterStatusMsg(
            current_run_id=self._run_id,
            current_task=self._current_task_id,
            current_model=self._current_model,
            current_stage=str(self._stage),
            tasks_total=self._total_tasks,
            tasks_completed=self._completed_tasks,
            start_time_ms=self._start_time_ms,
            end_time_ms=end_time,
            task_start_ms=self._task_start_ms,
        )
        self.signals.progress.emit(status_msg)

    def _emit_mode_switch(self, from_stage: PipelineStage, to_stage: PipelineStage) -> None:
        """Emit a ModeSwitchEvent for a pipeline stage transition."""
        self._event_bus.emit_mode_switch(ModeSwitchEvent(run_id=self._run_id, from_stage=from_stage, to_stage=to_stage))

    def _compute_eta(self) -> float | None:
        """Compute estimated remaining time in ms using a rolling average."""
        if not self._task_durations:
            return None
        avg_ms = sum(self._task_durations) / len(self._task_durations)
        remaining = max(0, self._total_tasks - self._completed_tasks)
        return avg_ms * remaining

    def _record_task_duration(self, duration_ms: float) -> None:
        """Track the latest task duration for ETA computation."""
        self._task_durations.append(duration_ms)
        if len(self._task_durations) > _ETA_WINDOW_SIZE:
            self._task_durations.pop(0)

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    def _mark_failed(self, result: BenchmarkResult, exc: Exception) -> None:
        """Persist a FAILED status with inference error details."""
        try:
            self._data_api.update_benchmark_result(
                dataclasses.replace(
                    result,
                    status=BenchmarkResultStatus.FAILED,
                    has_inference_error=True,
                    inference_error_message=str(exc),
                )
            )
        except Exception as update_exc:
            self.logger.warning("failed_to_persist_inference_failure", extra={"error": str(update_exc)})
        self._failed_tasks += 1
        self._write_log_entry(
            LogEntryType.ERROR,
            f"inference_failed task={result.task_id} error={exc}",
        )

    def _mark_judge_failed(self, result: BenchmarkResult, exc: Exception) -> None:
        """Persist a FAILED status with judge error details."""
        try:
            self._data_api.update_benchmark_result(
                dataclasses.replace(
                    result,
                    status=BenchmarkResultStatus.FAILED,
                    has_judge_error=True,
                    judge_error_message=f"Eval pipeline failed: {exc}",
                )
            )
        except Exception as update_exc:
            self.logger.warning("failed_to_persist_judge_failure", extra={"error": str(update_exc)})
        self._failed_tasks += 1
        self._write_log_entry(
            LogEntryType.ERROR,
            f"judge_failed task={result.task_id} error={exc}",
        )

    # ------------------------------------------------------------------
    # Miscellaneous helpers
    # ------------------------------------------------------------------

    def _check_embedding_provider_health(self) -> None:
        """Test the embedding provider before the JUDGING stage starts.

        When cosine evaluation is enabled, attempts a sentinel encode call so the
        user sees a clear warning if no embedding provider is available rather than
        an opaque RuntimeError mid-pipeline.
        """
        if not self._app_settings.get_bool(SETTING_COSINE_ENABLED):
            return
        try:
            embedding_provider = self._provider_registry.get_embedding_provider()
            embedding_provider.encode(["health_check"])
        except RuntimeError as exc:
            self._notify_warn(f"Embedding provider unavailable — cosine layer will be skipped: {exc}")
            self._event_bus.emit_provider_health_check(
                ProviderHealthCheckEvent(
                    run_id=self._run_id,
                    provider_id="embedding",
                    is_healthy=False,
                    error_message=str(exc),
                )
            )

    def _check_pause_or_stop(self) -> bool:
        """Block while paused; return False if stopped, True to continue."""
        if self._stop_requested:
            return False
        while not self._pause_event.is_set():
            self._pause_event.wait(timeout=1.0)
            if self._stop_requested:
                return False
        return not self._stop_requested

    def _run_health_check(self, provider: LLMProviderApi, provider_id: str) -> bool:
        """Run provider health check and emit event.

        Returns:
            False if unhealthy and stop-on-error is configured, True otherwise.
        """
        is_healthy = True
        error_msg: str | None = None
        try:
            provider.get_available_models()
        except Exception as exc:
            is_healthy = False
            error_msg = str(exc)

        self._event_bus.emit_provider_health_check(
            ProviderHealthCheckEvent(
                run_id=self._run_id,
                provider_id=provider_id,
                is_healthy=is_healthy,
                error_message=error_msg,
            )
        )

        if not is_healthy and self._app_settings.get_bool(SETTING_STOP_ON_PROVIDER_ERROR):
            self._notify_warn(f"Provider {provider_id} is unhealthy; stopping run.")
            self._stop_requested = True
            return False
        return True

    def _warm_up_model(self, provider: LLMProviderApi, model_name: str) -> None:
        """Attempt to warm up a model; log warning on failure but don't stop."""
        try:
            self.logger.debug(f"Warming up model: {model_name}")
            provider.warm_up(model_name)
        except Exception as exc:
            self._notify_warn(f"Warm-up failed for {model_name}: {exc}")

    @staticmethod
    def _build_messages(user_prompt: str, system_prompt: str) -> list[dict[str, str]]:
        """Build the messages list for the provider API."""
        if system_prompt:
            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        return [{"role": "user", "content": user_prompt}]

    def _enrich_descriptor_provider_types(self, descriptors: list[ModelDescriptor]) -> list[ModelDescriptor]:
        """Fill in missing provider_type on descriptors by querying the provider registry."""
        result: list[ModelDescriptor] = []
        for desc in descriptors:
            if desc.provider_type:
                result.append(desc)
                continue
            try:
                provider = self._provider_registry.get_provider(desc.provider_id)
                result.append(dataclasses.replace(desc, provider_type=provider.provider_type))
            except Exception:
                self.logger.warning("provider_type_lookup_failed", extra={"provider_id": desc.provider_id})
                result.append(desc)
        return result

    @staticmethod
    def _parse_model_descriptors(models_json: str) -> list[ModelDescriptor]:
        """Parse models_json into a list of ModelDescriptor instances.

        Returns:
            Empty list on parse failure or empty JSON array.
        """
        try:
            raw: list[dict[str, Any]] = json.loads(models_json)
        except json.JSONDecodeError:
            logger.warning("models_json_parse_failed", extra={"value": models_json[:100]})
            return []
        descriptors: list[ModelDescriptor] = []
        for item in raw:
            try:
                descriptors.append(
                    ModelDescriptor(
                        provider_id=item["provider_id"],
                        provider_type=item.get("provider_type", ""),
                        model_name=item["model_name"],
                        display_label=item.get("display_label", item["model_name"]),
                        model_family=item.get("model_family"),
                        model_size_b=item.get("model_size_b"),
                        quantization_label=item.get("quantization_label"),
                    )
                )
            except (KeyError, TypeError) as exc:
                logger.warning("malformed_model_descriptor", extra={"item": str(item), "error": str(exc)})
        return descriptors

    @staticmethod
    def _build_initial_result(
        run: BenchmarkRun,
        desc: ModelDescriptor,
        task: BenchmarkTask,
    ) -> BenchmarkResult:
        """Build a minimal NOT_COMPLETED BenchmarkResult row."""
        return BenchmarkResult(
            run_id=run.run_id,
            run_type=str(run.run_mode),
            provider_id=desc.provider_id,
            provider_type=desc.provider_type,
            model_name=desc.model_name,
            model_family=desc.model_family,
            model_size_b=desc.model_size_b,
            quantization_label=desc.quantization_label,
            task_id=task.task_id,
            task_category=task.category or task.task_id.split("_")[0],
            task_type=str(task.task_type),
            task_difficulty=str(task.difficulty) if task.difficulty else None,
            response_scope=str(task.response_scope) if task.response_scope else None,
            source_language=task.source_language,
            target_language=task.target_language,
            golden_answer=task.golden_answer,
            status=BenchmarkResultStatus.NOT_COMPLETED,
        )

    @staticmethod
    def _build_prompt_eval_result(
        run: BenchmarkRun,
        desc: ModelDescriptor,
        task: BenchmarkTask,
        variant: PromptVariant,
    ) -> BenchmarkResult:
        """Build a NOT_COMPLETED BenchmarkResult pre-rendered for a prompt variant."""
        rendered_prompt = variant.user_prompt_template.replace("{question}", task.question)
        return BenchmarkResult(
            run_id=run.run_id,
            run_type=str(run.run_mode),
            provider_id=desc.provider_id,
            provider_type=desc.provider_type,
            model_name=desc.model_name,
            model_family=desc.model_family,
            model_size_b=desc.model_size_b,
            quantization_label=desc.quantization_label,
            task_id=task.task_id,
            task_category=task.category or task.task_id.split("_")[0],
            task_type=str(task.task_type),
            task_difficulty=str(task.difficulty) if task.difficulty else None,
            response_scope=str(task.response_scope) if task.response_scope else None,
            source_language=task.source_language,
            target_language=task.target_language,
            golden_answer=task.golden_answer,
            prompt_version=variant.variant_id,
            user_prompt_sent=rendered_prompt,
            system_prompt_sent=variant.system_prompt,
            status=BenchmarkResultStatus.NOT_COMPLETED,
        )

    # ------------------------------------------------------------------
    # Performance analysis
    # ------------------------------------------------------------------

    def _stage_performance_analysis(self, run: BenchmarkRun) -> None:
        """Build a throughput analysis prompt, call the judge LLM, store and emit the result."""
        self._notify("=== PERFORMANCE ANALYSIS ===")
        if not run.judge_provider_id or not run.judge_model:
            self._notify_warn("Performance analysis skipped: no judge model configured.")
            return

        try:
            results = self._data_api.retrieve_benchmark_results_for_run(run.run_id)
            if not results:
                self._notify_warn("Performance analysis skipped: no results found.")
                return

            prompt = self._build_perf_analysis_prompt(run, results)
            provider = self._provider_registry.get_provider(run.judge_provider_id)
            messages = self._build_messages(prompt, "")
            response = provider.inference_sync(model=run.judge_model, messages=messages, temperature=0.3)
            analysis_text = response.llm_response or "(no response)"

            self._data_api.update_run_perf_analysis(run_id=run.run_id, analysis=analysis_text)
            self._event_bus.emit_perf_analysis(PerfAnalysisEvent(run_id=run.run_id, analysis_text=analysis_text))
            self._notify("Performance analysis complete.")
        except Exception as exc:
            self.logger.warning("perf_analysis_failed", extra={"error": str(exc)})
            self._notify_warn(f"Performance analysis failed: {exc}")

    @staticmethod
    def _build_perf_analysis_prompt(run: BenchmarkRun, results: list[BenchmarkResult]) -> str:
        """Aggregate benchmark results into a markdown table and wrap it in an analysis prompt."""
        # Group by (input_size_prefix, output_size) extracted from task_id, then by model
        # task_id format: perf_<input>_<output>_r<N>  OR  arbitrary for speed mode
        cell_tps: dict[tuple[str, str], list[float]] = defaultdict(list)
        cell_ttft: dict[tuple[str, str], list[float]] = defaultdict(list)

        for r in results:
            parts = r.task_id.split("_")
            cell_key = (parts[1], parts[2]) if len(parts) >= 3 and parts[0] == "perf" else ("all", "all")
            if r.tokens_per_second is not None:
                cell_tps[cell_key].append(r.tokens_per_second)
            if r.ttft_ms is not None:
                cell_ttft[cell_key].append(r.ttft_ms)

        model_names = sorted({r.model_name for r in results})
        rows: list[str] = ["| Cell | Avg tok/s | Min tok/s | Max tok/s | Avg TTFT ms |", "|-|-|-|-|-|"]
        for key in sorted(cell_tps.keys()):
            tps_vals = cell_tps[key]
            ttft_vals = cell_ttft.get(key, [])
            label = f"{key[0]}x{key[1]}"
            avg_tps = statistics.mean(tps_vals) if tps_vals else 0.0
            min_tps = min(tps_vals) if tps_vals else 0.0
            max_tps = max(tps_vals) if tps_vals else 0.0
            avg_ttft = statistics.mean(ttft_vals) if ttft_vals else 0.0
            rows.append(f"| {label} | {avg_tps:.1f} | {min_tps:.1f} | {max_tps:.1f} | {avg_ttft:.0f} |")

        table = "\n".join(rows)
        return (
            f"You are analyzing LLM benchmark performance results.\n"
            f"Run mode: {run.run_mode}. Models tested: {', '.join(model_names)}.\n\n"
            f"Performance metrics per cell (input_size x output_size):\n{table}\n\n"
            f"Provide a concise analysis covering:\n"
            f"1. Overall throughput trends by input size\n"
            f"2. Output size impact on tokens/sec\n"
            f"3. TTFT trends\n"
            f"4. Any anomalies or notable patterns\n"
            f"5. Summary recommendation"
        )

    @staticmethod
    def _parse_performance_config(config_json: str | None) -> PerformanceConfig | None:
        """Parse a JSON string into a PerformanceConfig, returning None on failure."""
        if not config_json:
            return None
        try:
            data = json.loads(config_json)
            input_sizes = tuple(PromptInputSize(s) for s in data.get("input_sizes", []))
            output_sizes = tuple(PromptOutputSize(s) for s in data.get("output_sizes", []))
            repeat_count = int(data.get("repeat_count", 3))
            if not input_sizes or not output_sizes:
                return None
            return PerformanceConfig(
                input_sizes=input_sizes,
                output_sizes=output_sizes,
                repeat_count=repeat_count,
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            return None

    # ------------------------------------------------------------------
    # Logging helpers (V1 compatible)
    # ------------------------------------------------------------------

    def _log_msg_to_global_logger(self, msg: str) -> None:
        """Forward a message to the log widget via the V1 signal."""
        self.signals.log_message.emit(msg)

    def _notify(self, message: str) -> None:
        """Log at DEBUG level and forward to the log widget."""
        self.logger.debug(message)
        self._log_msg_to_global_logger(message)

    def _notify_warn(self, message: str) -> None:
        """Log at WARNING level and forward to the log widget."""
        self.logger.warning(message)
        self._log_msg_to_global_logger(message)

    def _write_log_entry(self, entry_type: LogEntryType, content: str) -> None:
        """Write a structured log entry to disk if log-to-file is enabled.

        Args:
            entry_type: Category of the log entry.
            content: Human-readable entry content.
        """
        if not self._app_settings.get_bool(SETTING_LOG_TO_FILE):
            return
        try:
            self._log_file_writer.write_entry(self._run_id, entry_type, content)
        except Exception:
            self.logger.warning("log_file_write_failed", extra={"entry_type": str(entry_type)})
