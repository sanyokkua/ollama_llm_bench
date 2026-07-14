"""Drives the INFERENCE/JUDGE_CHECK phases through the full stability stack (STORY-030).

Extracted out of `_internal/lifecycle.py` to keep `_BenchmarkFlowApiImpl` within the
project's per-class line budget (`coding-style.md`) — this module owns the
role-appropriate `run_phase_with_stability` wiring, run-wide judge-exclusion
detection, and the `_model_stability_changed` composite event, all as free functions
over an explicit `_StabilityRunState` bundle rather than instance methods.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, cast

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.dispatcher import (
    run_phase_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.events import (
    emit_judge_model_excluded,
    emit_model_stability_changed,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.judge_target import (
    resolve_judge_target,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
    build_inference_attempt,
    build_judge_attempt,
    build_judge_timeout_exhausted_patch,
    finalize_inference_success,
    finalize_judge_success,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import Phase
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    ErrorKind,
    ModelName,
    ModelNameStr,
    ProviderId,
    ProviderIdStr,
    ResultPatch,
    ResultStatus,
)
from ollama_llm_bench.backend.errors import ContractViolationError
from ollama_llm_bench.backend.evaluation.protocols import JudgeEvaluator, SanityChecker
from ollama_llm_bench.backend.events.models import (
    JudgeModelExcludedEvent,
    ModelStabilityChangedEvent,
)
from ollama_llm_bench.backend.events.protocols import EventBus
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.settings.protocols import SettingsService

if TYPE_CHECKING:
    from ollama_llm_bench.backend.adaptive_timeout.models import AdaptiveTimeoutModelState
    from ollama_llm_bench.backend.benchmark_pipeline._internal.units import (
        _InferenceAttemptOutcome,
    )
    from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
    from ollama_llm_bench.backend.evaluation.models import JudgePhaseResult

__all__: list[str] = ["StabilityCollaborators", "StabilityRunState", "run_stability_phase"]

_MS_PER_SECOND = 1000


@dataclass(slots=True, frozen=True)
class StabilityCollaborators:
    """Fixed, per-controller collaborators the stability phases need
    (`_internal`-only, never crosses this module's boundary)."""

    bus: EventBus
    clock: Clock
    provider_registry: ProviderRegistry
    results_store: ResultsStore
    settings_service: SettingsService
    task_runner: TaskRunner[object]


@dataclass(slots=True)
class StabilityRunState:
    """Per-run mutable state the one-shot exclusion check and the
    stability-changed transition check need, reset at the start of every run
    (`_internal`-only)."""

    judge_excluded_emitted: bool = False
    last_stability_state: dict[
        tuple[ProviderId, ModelName], tuple["AdaptiveTimeoutModelState", "CircuitState"]
    ] = field(default_factory=dict)


def run_stability_phase(  # noqa: PLR0913  # every keyword-only argument is a
    # distinct collaborator this stability-aware phase dispatch needs — the
    # phase/groups the caller resolved, the run/tasks/sanity_checker/judge_evaluator/
    # token/toggles every unit builder needs, and the stability collaborators
    # (collaborators, state, adaptive_timeout, circuit_breaker, retry_count)
    *,
    phase: Phase,
    groups: tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...],
    run: BenchmarkRun,
    tasks_by_id: dict[str, BenchmarkTask],
    sanity_checker: SanityChecker,
    judge_evaluator: JudgeEvaluator | None,
    token: CancellationToken,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    force_judge_on_prior_failure: bool,
    collaborators: StabilityCollaborators,
    state: StabilityRunState,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    retry_count: int,
) -> None:
    """Dispatch one stability-aware phase (`INFERENCE` or `JUDGE_CHECK`) to
    `run_phase_with_stability` with the role-appropriate closures (STORY-030).
    """
    if phase is Phase.INFERENCE:
        _run_inference_phase(
            groups=groups,
            tasks_by_id=tasks_by_id,
            sanity_checker=sanity_checker,
            token=token,
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
            collaborators=collaborators,
            adaptive_timeout=adaptive_timeout,
            circuit_breaker=circuit_breaker,
            retry_count=retry_count,
        )
        return
    if phase is Phase.JUDGE_CHECK:
        _run_judge_phase(
            groups=groups,
            run=run,
            tasks_by_id=tasks_by_id,
            judge_evaluator=judge_evaluator,
            token=token,
            force_judge_on_prior_failure=force_judge_on_prior_failure,
            collaborators=collaborators,
            state=state,
            adaptive_timeout=adaptive_timeout,
            circuit_breaker=circuit_breaker,
            retry_count=retry_count,
        )
        return
    raise ContractViolationError(
        message=f"unreachable: run_stability_phase called with non-stability phase {phase!r}"
    )


def _run_inference_phase(  # noqa: PLR0913  # each parameter is a distinct
    # collaborator run_phase_with_stability requires
    *,
    groups: tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...],
    tasks_by_id: dict[str, BenchmarkTask],
    sanity_checker: SanityChecker,
    token: CancellationToken,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    collaborators: StabilityCollaborators,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    retry_count: int,
) -> None:
    """Drive the INFERENCE phase's rows through `run_phase_with_stability`."""

    def _stability_target_for(result: BenchmarkResult) -> tuple[ProviderId, ModelName]:
        return result.provider_id, result.model_name

    def _build_attempt_for(
        result: BenchmarkResult,
    ) -> Callable[[int], Callable[[], "_InferenceAttemptOutcome"]]:
        return build_inference_attempt(
            result=result,
            task=tasks_by_id[result.task_id],
            provider_registry=collaborators.provider_registry,
            sanity_checker=sanity_checker,
            clock=collaborators.clock,
            bus=collaborators.bus,
            token=token,
        )

    def _finalize_success_for(
        result: BenchmarkResult,
    ) -> Callable[["_InferenceAttemptOutcome"], ResultPatch]:
        return finalize_inference_success(
            result=result,
            task=tasks_by_id[result.task_id],
            bus=collaborators.bus,
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
        )

    def _on_timeout_exhausted_for(result: BenchmarkResult) -> Callable[[], ResultPatch]:
        del result  # role=INFERENCE's timeout-exhaustion terminal patch matches
        # HttpTimeoutError's own DD-44 status/kind mapping (FAILED_TIMEOUT) — built
        # directly here rather than round-tripping through contain_unit_failure,
        # unlike role=JUDGE's FAILED_JUDGE_TIMEOUT override which genuinely
        # diverges from the generic mapping
        return lambda: ResultPatch(
            status=ResultStatus.FAILED_TIMEOUT,
            error_kind=ErrorKind.TIMEOUT,
            error_message="Inference call exhausted adaptive budget for this task.",
        )

    run_phase_with_stability(
        groups=groups,
        runner=cast("TaskRunner[_InferenceAttemptOutcome]", collaborators.task_runner),
        token=token,
        results_store=collaborators.results_store,
        role=AdaptiveTimeoutRole.INFERENCE,
        retry_count=retry_count,
        clock=collaborators.clock,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        stability_target_for=_stability_target_for,
        build_attempt_for=_build_attempt_for,
        finalize_success_for=_finalize_success_for,
        on_timeout_exhausted_for=_on_timeout_exhausted_for,
    )


def _run_judge_phase(  # noqa: PLR0913  # each parameter is a distinct collaborator
    # run_phase_with_stability and the judge-exclusion/stability-changed hooks require
    *,
    groups: tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...],
    run: BenchmarkRun,
    tasks_by_id: dict[str, BenchmarkTask],
    judge_evaluator: JudgeEvaluator | None,
    token: CancellationToken,
    force_judge_on_prior_failure: bool,
    collaborators: StabilityCollaborators,
    state: StabilityRunState,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    retry_count: int,
) -> None:
    """Drive the JUDGE_CHECK phase's rows through `run_phase_with_stability`.

    `judge_evaluator is None` here should be unreachable in practice:
    `phase_applies(JUDGE_CHECK)` already guarantees `judge_enabled`, and the
    caller's evaluator construction only returns `None` when the phase is not
    actually enabled — the `ContractViolationError` below is a defensive
    backstop, not this story's primary handling for that case.
    """
    if judge_evaluator is None:
        raise ContractViolationError(
            message="unreachable: JUDGE_CHECK stability phase requested but "
            "judge_evaluator is None (phase_applies already guarantees "
            "judge_enabled implies this)"
        )
    judge_target = resolve_judge_target(run)
    if judge_target is None:
        raise ContractViolationError(
            message="unreachable: JUDGE_CHECK stability phase requested but "
            "the run has no ModelRole.JUDGE entry"
        )
    judge_provider_id, judge_model_name = judge_target

    def _stability_target_for(result: BenchmarkResult) -> tuple[ProviderId, ModelName]:
        del result  # role=JUDGE's target is the run's one fixed judge pair, never
        # the row's own test-model identity
        return judge_provider_id, judge_model_name

    def _build_attempt_for(
        result: BenchmarkResult,
    ) -> Callable[[int], Callable[[], "JudgePhaseResult"]]:
        return build_judge_attempt(
            result=result,
            task=tasks_by_id[result.task_id],
            evaluator=judge_evaluator,
            token=token,
            bus=collaborators.bus,
            judge_provider_id=judge_provider_id,
            judge_model_name=judge_model_name,
        )

    def _finalize_success_for(
        result: BenchmarkResult,
    ) -> Callable[["JudgePhaseResult"], ResultPatch]:
        return finalize_judge_success(
            result=result,
            force_judge_on_prior_failure=force_judge_on_prior_failure,
            bus=collaborators.bus,
        )

    def _on_timeout_exhausted_for(result: BenchmarkResult) -> Callable[[], ResultPatch]:
        del result
        return build_judge_timeout_exhausted_patch()

    def _after_row(result: BenchmarkResult, patch: ResultPatch, remaining: int) -> None:
        del result
        if patch.status is ResultStatus.FAILED_JUDGE_TIMEOUT:
            _check_and_emit_judge_exclusion(
                run=run,
                judge_provider_id=judge_provider_id,
                judge_model_name=judge_model_name,
                adaptive_timeout=adaptive_timeout,
                remaining_row_count=remaining,
                collaborators=collaborators,
                state=state,
            )
        _maybe_emit_stability_changed(
            run_id=run.run_id,
            provider_id=judge_provider_id,
            model_name=judge_model_name,
            adaptive_timeout=adaptive_timeout,
            circuit_breaker=circuit_breaker,
            retry_count=retry_count,
            collaborators=collaborators,
            state=state,
        )

    run_phase_with_stability(
        groups=groups,
        runner=cast("TaskRunner[JudgePhaseResult]", collaborators.task_runner),
        token=token,
        results_store=collaborators.results_store,
        role=AdaptiveTimeoutRole.JUDGE,
        retry_count=retry_count,
        clock=collaborators.clock,
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
        stability_target_for=_stability_target_for,
        build_attempt_for=_build_attempt_for,
        finalize_success_for=_finalize_success_for,
        on_timeout_exhausted_for=_on_timeout_exhausted_for,
        after_row=_after_row,
    )


def _check_and_emit_judge_exclusion(  # noqa: PLR0913  # each parameter is a distinct
    # input the one-shot exclusion check and its event payload need
    *,
    run: BenchmarkRun,
    judge_provider_id: ProviderId,
    judge_model_name: ModelName,
    adaptive_timeout: AdaptiveTimeoutService,
    remaining_row_count: int,
    collaborators: StabilityCollaborators,
    state: StabilityRunState,
) -> None:
    """Emit `_judge_model_excluded` exactly once, on the not-excluded -> excluded
    transition of the role=JUDGE bucket (STORY-030-AC-4)."""
    if state.judge_excluded_emitted:
        return
    if not adaptive_timeout.is_excluded(
        judge_provider_id, judge_model_name, AdaptiveTimeoutRole.JUDGE
    ):
        return
    state.judge_excluded_emitted = True
    threshold = collaborators.settings_service.get_int(
        "eval.judge_timeout_consecutive_threshold", run=run
    )
    emit_judge_model_excluded(
        collaborators.bus,
        JudgeModelExcludedEvent(
            run_id=run.run_id,
            provider_id=judge_provider_id,
            model_name=judge_model_name,
            consecutive_timeouts=threshold,
            exclusion_reason="did not fit the allotted time",
            excluded_at=int(
                datetime.fromisoformat(collaborators.clock.now_utc()).timestamp() * 1000
            ),
            remaining_tasks_affected=remaining_row_count,
        ),
    )


def _maybe_emit_stability_changed(  # noqa: PLR0913  # each parameter is a distinct
    # input the stability-changed transition check and its event payload need
    *,
    run_id: int,
    provider_id: ProviderId,
    model_name: ModelName,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    retry_count: int,
    collaborators: StabilityCollaborators,
    state: StabilityRunState,
) -> None:
    """Emit `_model_stability_changed` only on a genuine observable-state
    transition for `(provider_id, model_name)` (STORY-030, `08-J §5.2`).

    `model_consecutive_successes`/`provider_consecutive_failures` are recorded
    as `0` — a documented placeholder, not a fabricated value: neither the
    `AdaptiveTimeoutService` nor the `ProviderCircuitBreaker` Protocol exposes
    an accessor for these internal counters (verified against both modules'
    `_internal/` implementations); adding one is a STORY-022/023 follow-up,
    out of this story's `modules:` scope. See this story's Notes section.
    """
    model_state = adaptive_timeout.model_state(provider_id, model_name, AdaptiveTimeoutRole.JUDGE)
    provider_state = circuit_breaker.state(provider_id)
    key = (provider_id, model_name)
    current = (model_state, provider_state)
    if state.last_stability_state.get(key) == current:
        return
    state.last_stability_state[key] = current
    cooldown_seconds = circuit_breaker.cooldown_remaining_seconds(provider_id) or 0
    emit_model_stability_changed(
        collaborators.bus,
        ModelStabilityChangedEvent(
            run_id=run_id,
            provider_id=provider_id,
            model_name=model_name,
            model_state=model_state.value,
            model_consecutive_successes=0,
            model_promotion_threshold=retry_count,
            provider_state=provider_state.value,
            provider_consecutive_failures=0,
            provider_cooldown_remaining_ms=cooldown_seconds * _MS_PER_SECOND,
        ),
    )
