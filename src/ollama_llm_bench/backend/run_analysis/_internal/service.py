"""The RunAnalysisService implementation (§6 — the full algorithm)."""

from dataclasses import dataclass
from typing import Final

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.concurrency import CancellationToken, make_cancellation_token
from ollama_llm_bench.backend.domain import (
    AdaptiveTimeoutRole,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkRunSettingEntry,
    BenchmarkTask,
    InferenceActivity,
    InferenceActivityContext,
    InferenceContext,
    ModelName,
    ProviderId,
    ResultStatus,
    RunId,
    RunStatus,
)
from ollama_llm_bench.backend.errors import AppError, ContractViolationError, HttpTimeoutError
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.inference_progress import emit_progress_during
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.persistence.runs.protocols import RunsStore
from ollama_llm_bench.backend.persistence.tasks.protocols import TasksStore
from ollama_llm_bench.backend.provider_registry.protocols import LLMClient, ProviderRegistry
from ollama_llm_bench.backend.run_analysis._internal.aggregation import RunDigest, build_run_digest
from ollama_llm_bench.backend.run_analysis._internal.prompt import build_analysis_request
from ollama_llm_bench.backend.run_analysis._internal.timeout_cache import RunAdaptiveTimeoutCache
from ollama_llm_bench.backend.run_analysis.models import RunAnalysisOutcome, RunAnalysisResult
from ollama_llm_bench.backend.stores.inference_activity.protocols import InferenceActivityStore

__all__: list[str] = ["RunAnalysisServiceImpl"]

_MS_PER_SECOND: Final[int] = 1000
_BUSY_MESSAGE: Final[str] = "An inference is currently in flight - please wait."
_JUDGE_RUN_ANALYSIS_ENABLED_KEY: Final[str] = "feature.judge_run_analysis_enabled"
_ESCALATION_STEPS_KEY: Final[str] = "eval.judge_timeout_escalation_steps"
_TERMINAL_RUN_STATUSES: Final[frozenset[RunStatus]] = frozenset(
    {RunStatus.COMPLETED, RunStatus.STOPPED, RunStatus.FAILED}
)
_NON_TERMINAL_RESULT_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {
        ResultStatus.PENDING,
        ResultStatus.RUNNING_INFERENCE,
        ResultStatus.AWAITING_KEYWORD_CHECK,
        ResultStatus.AWAITING_COSINE_CHECK,
        ResultStatus.AWAITING_JUDGE_CHECK,
    }
)


def _snapshot_flag(snapshot: tuple[BenchmarkRunSettingEntry, ...], key: str) -> str | None:
    for entry in snapshot:
        if entry.setting_key == key:
            return entry.setting_value
    return None


def _read_int(snapshot: tuple[BenchmarkRunSettingEntry, ...], key: str) -> int:
    value = _snapshot_flag(snapshot, key)
    return int(value) if value is not None else 0


def _has_terminal_result(results: tuple[BenchmarkResult, ...]) -> bool:
    return any(result.status not in _NON_TERMINAL_RESULT_STATUSES for result in results)


@dataclass(slots=True, frozen=True)
class _LoadedRun:
    """Bundles one ``generate()`` call's loaded run state (§6.1, §6.2)."""

    run: BenchmarkRun
    results: tuple[BenchmarkResult, ...]
    tasks_by_id: dict[str, BenchmarkTask]
    is_regeneration: bool


@dataclass(slots=True, frozen=True)
class _EscalationContext:
    """Bundles one ``generate()`` call's escalation-loop dependencies (§6.4)."""

    run: BenchmarkRun
    digest: RunDigest
    provider_id: ProviderId
    model_name: ModelName
    adaptive_timeout: AdaptiveTimeoutService
    client: LLMClient
    token: CancellationToken
    is_regeneration: bool


class RunAnalysisServiceImpl:
    """Concrete ``RunAnalysisService`` — see the module docstring for the algorithm.

    ``generate``'s public Protocol signature is exactly
    ``generate(run_id, provider_id, model_name) -> RunAnalysisResult`` — no
    ``inside_pipeline`` parameter. This concrete class adds
    ``inside_pipeline: bool = False`` as a keyword-only extension: the benchmark
    pipeline's own finalization step (a later story, out of STORY-035's scope)
    passes ``inside_pipeline=True`` explicitly; every other caller — including
    the user-initiated Generate Analysis dialog — gets the default ``False``.
    """

    def __init__(  # noqa: PLR0913  # constructor injection — every dependency is distinct and load-bearing
        self,
        *,
        runs_store: RunsStore,
        results_store: ResultsStore,
        tasks_store: TasksStore,
        provider_registry: ProviderRegistry,
        inference_activity_store: InferenceActivityStore,
        event_bus: EventBus,
        clock: Clock,
        timeout_cache: RunAdaptiveTimeoutCache,
    ) -> None:
        self._runs_store = runs_store
        self._results_store = results_store
        self._tasks_store = tasks_store
        self._provider_registry = provider_registry
        self._inference_activity_store = inference_activity_store
        self._event_bus = event_bus
        self._clock = clock
        self._timeout_cache = timeout_cache

    def generate(
        self,
        run_id: RunId,
        provider_id: ProviderId,
        model_name: ModelName,
        *,
        inside_pipeline: bool = False,
    ) -> RunAnalysisResult:
        """See ``RunAnalysisService.generate`` for the full contract."""
        run = self._runs_store.get_run(run_id)
        if run.status not in _TERMINAL_RUN_STATUSES:
            raise ContractViolationError(
                message=f"run {run_id} is not in a terminal status (status={run.status.value})"
            )
        loaded = _LoadedRun(
            run=run,
            results=self._results_store.list_results(run_id),
            tasks_by_id={task.task_id: task for task in self._tasks_store.list_tasks(run_id)},
            is_regeneration=run.run_analysis is not None,
        )

        if self._should_skip(loaded, inside_pipeline=inside_pipeline):
            return RunAnalysisResult(
                outcome=RunAnalysisOutcome.SKIPPED, is_regeneration=loaded.is_regeneration
            )

        lease = None
        if not inside_pipeline:
            lease = self._inference_activity_store.try_acquire(
                InferenceActivity.JUDGE_ANALYSIS,
                InferenceActivityContext(
                    activity=InferenceActivity.JUDGE_ANALYSIS,
                    started_at=self._clock.monotonic_ms(),
                    run_id=run_id,
                    provider_id=provider_id,
                    model_name=model_name,
                ),
            )
            if lease is None:
                return RunAnalysisResult(
                    outcome=RunAnalysisOutcome.FAILED,
                    error_message=_BUSY_MESSAGE,
                    is_regeneration=loaded.is_regeneration,
                )
        try:
            return self._run_analysis(loaded, provider_id=provider_id, model_name=model_name)
        finally:
            if lease is not None:
                self._inference_activity_store.release(lease)

    def _should_skip(self, loaded: _LoadedRun, *, inside_pipeline: bool) -> bool:
        if (
            inside_pipeline
            and _snapshot_flag(loaded.run.settings_snapshot, _JUDGE_RUN_ANALYSIS_ENABLED_KEY)
            != "true"
        ):
            return True
        return not _has_terminal_result(loaded.results)

    def _run_analysis(
        self, loaded: _LoadedRun, *, provider_id: ProviderId, model_name: ModelName
    ) -> RunAnalysisResult:
        digest = build_run_digest(
            run=loaded.run, results=loaded.results, tasks_by_id=loaded.tasks_by_id
        )
        adaptive_timeout = self._timeout_cache.get_or_create(
            run_id=loaded.run.run_id, snapshot=loaded.run.settings_snapshot
        )
        context = _EscalationContext(
            run=loaded.run,
            digest=digest,
            provider_id=provider_id,
            model_name=model_name,
            adaptive_timeout=adaptive_timeout,
            client=self._provider_registry.get_client(provider_id),
            token=make_cancellation_token(clock=self._clock),
            is_regeneration=loaded.is_regeneration,
        )
        return self._call_model_with_escalation(context)

    def _call_model_with_escalation(self, context: _EscalationContext) -> RunAnalysisResult:
        escalation_steps = _read_int(context.run.settings_snapshot, _ESCALATION_STEPS_KEY)
        max_attempts = 1 + escalation_steps
        for attempt_index in range(1, max_attempts + 1):
            outcome = self._attempt_once(context, attempt_index)
            if outcome is not None:
                return outcome
        return RunAnalysisResult(
            outcome=RunAnalysisOutcome.FAILED,
            error_message="judge_timeout_exhausted: escalation ladder exhausted.",
            is_regeneration=context.is_regeneration,
        )

    def _attempt_once(
        self, context: _EscalationContext, attempt_index: int
    ) -> RunAnalysisResult | None:
        budget_seconds = context.adaptive_timeout.next_budget(
            context.provider_id, context.model_name, AdaptiveTimeoutRole.RUN_ANALYSIS, attempt_index
        )
        request = build_analysis_request(
            context.digest,
            run_mode=context.run.run_mode,
            model_name=context.model_name,
            timeout_ms=budget_seconds * _MS_PER_SECOND,
        )
        started_at_ms = self._clock.monotonic_ms()
        try:
            chat_stream = context.client.chat_stream(request, token=context.token)
            response = emit_progress_during(
                chat_stream,
                context=InferenceContext.RUN_ANALYSIS,
                run_id=context.run.run_id,
                result_id=None,
                task_id=None,
                provider_id=context.provider_id,
                model_name=context.model_name,
                clock=self._clock,
                event_bus=self._event_bus,
                token=context.token,
            )
        except HttpTimeoutError:
            return self._handle_timeout(context, attempt_index)
        except AppError as exc:
            return RunAnalysisResult(
                outcome=RunAnalysisOutcome.FAILED,
                error_message=exc.message,
                is_regeneration=context.is_regeneration,
            )
        if response.error is not None:
            return RunAnalysisResult(
                outcome=RunAnalysisOutcome.FAILED,
                error_message=f"Analysis model returned an unusable response: {response.error}",
                is_regeneration=context.is_regeneration,
            )
        context.adaptive_timeout.record_success(
            context.provider_id,
            context.model_name,
            AdaptiveTimeoutRole.RUN_ANALYSIS,
            observed_ms=self._clock.monotonic_ms() - started_at_ms,
        )
        return RunAnalysisResult(
            outcome=RunAnalysisOutcome.GENERATED,
            run_analysis_markdown=response.text.strip(),
            is_regeneration=context.is_regeneration,
        )

    def _handle_timeout(
        self, context: _EscalationContext, attempt_index: int
    ) -> RunAnalysisResult | None:
        context.adaptive_timeout.record_timeout(
            context.provider_id, context.model_name, AdaptiveTimeoutRole.RUN_ANALYSIS
        )
        if not context.adaptive_timeout.is_excluded(
            context.provider_id, context.model_name, AdaptiveTimeoutRole.RUN_ANALYSIS
        ):
            return None
        return RunAnalysisResult(
            outcome=RunAnalysisOutcome.FAILED,
            error_message=(
                "judge_timeout_exhausted: the judge model failed to respond "
                f"within the time budget after {attempt_index} attempts."
            ),
            is_regeneration=context.is_regeneration,
        )
