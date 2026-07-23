"""The dispatcher-thread run loop: strictly serial, one unit in flight (D-R-16, DD-38)."""

from collections.abc import Callable
from typing import cast

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.grouping import (
    eligible_for_phase,
    group_by_provider_and_model,
    phase_applies,
)
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_dispatch import (
    run_task_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline.models import PHASE_ORDER, Phase
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency._internal.cancellation_token import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkResult,
    ModelNameStr,
    ProviderIdStr,
    ResultPatch,
    RunId,
    RunMode,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.persistence.results.protocols import ResultsStore

__all__: list[str] = [
    "run_all_phases",
    "run_phase",
    "run_phase_with_stability",
]


def run_phase(
    *,
    groups: tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...],
    runner: TaskRunner[object],
    token: CancellationToken,
    results_store: ResultsStore,
    unit_factory: Callable[[BenchmarkResult], Callable[[], ResultPatch]],
) -> None:
    """Run one phase over its already-grouped eligible rows, strictly serially.

    Submits exactly one unit at a time, blocks on its Future, persists the
    result, then submits the next — never more than one unit in flight
    (16_CONCURRENCY_MODEL.md §6.2).

    Args:
        groups: The phase's eligible rows, provider-then-model grouped, in
            first-seen order (never alphabetized).
        runner: The `TaskRunner` port a single unit is submitted to. Typed
            `TaskRunner[object]` (mirroring `backend/readiness`'s own
            established pattern) because the same runner instance also
            serves `run_phase_with_stability`'s per-role payload types; the
            `.result()` read is cast back to `ResultPatch` below, since every
            `unit_factory` this function is called with returns one.
        token: The run's `CancellationToken`, checked before every unit.
        results_store: The single-writer store each unit's patch is persisted
            through before the next unit is submitted.
        unit_factory: Builds the blocking callable for one result row.

    Raises:
        TaskCancelledError: The token was cancelled at a safe checkpoint
            before a unit's submission.
    """
    for _provider_id, _model_name, group_rows in groups:
        for result in group_rows:
            token.raise_if_cancelled()
            unit = unit_factory(result)
            future = runner.submit(unit, token=token)
            patch = cast("ResultPatch", future.result())
            results_store.update_result(result.result_id, patch)


def run_phase_with_stability[T](  # noqa: PLR0913  # every keyword-only argument is
    # a distinct collaborator this stability-aware phase loop needs: the grouped
    # rows, the runner/token/clock/service collaborators, the role/attempt-cap
    # inputs, and the four per-row closures the caller (lifecycle.py) varies per
    # phase — bundling them would only indirect the read without reducing coupling
    *,
    groups: tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...],
    runner: TaskRunner[T],
    token: CancellationToken,
    results_store: ResultsStore,
    role: AdaptiveTimeoutRole,
    retry_count: int,
    clock: Clock,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    stability_target_for: Callable[[BenchmarkResult], tuple[ProviderIdStr, ModelNameStr]],
    build_attempt_for: Callable[[BenchmarkResult], Callable[[int], Callable[[], T]]],
    finalize_success_for: Callable[[BenchmarkResult], Callable[[T], ResultPatch]],
    on_timeout_exhausted_for: Callable[[BenchmarkResult], Callable[[], ResultPatch]],
    after_row: Callable[[BenchmarkResult, ResultPatch, int], None] | None = None,
    before_group: Callable[[ProviderIdStr, ModelNameStr], None] | None = None,
) -> None:
    """Run one phase's rows through the full stability stack, strictly serially (STORY-030).

    Same iteration shape as `run_phase` (groups -> rows, strictly serial, one
    row's outcome persisted before the next row starts), but drives each row
    through `_internal.stability_dispatch.run_task_with_stability` instead of
    a single submit-and-block — requesting a per-attempt adaptive-timeout
    budget, consulting the circuit breaker, and retrying transient failures.

    Args:
        groups: The phase's eligible rows, provider-then-model grouped, in
            first-seen order.
        runner: The `TaskRunner` port each individual attempt is submitted to.
        token: The run's `CancellationToken`, checked before every row.
        results_store: The single-writer store each row's patch is persisted
            through before the next row is processed.
        role: The `AdaptiveTimeoutRole` bucket this phase's calls consult.
        retry_count: The run's resolved `benchmark.retry_count` setting.
        clock: The injected time source, threaded to the stability dispatcher.
        adaptive_timeout: Touched only on this thread, never inside a
            worker-submitted attempt callable.
        circuit_breaker: Touched only on this thread, same rule.
        stability_target_for: Resolves the `(provider_id, model_name)`
            stability target for one row — the row's own provider/model for
            `role=INFERENCE`, or the run's fixed judge target for `role=JUDGE`.
        build_attempt_for: Builds one row's attempt builder.
        finalize_success_for: Builds one row's winning-attempt finalizer.
        on_timeout_exhausted_for: Builds one row's timeout-exhaustion terminal
            patch builder.
        after_row: Optional hook invoked with `(result, patch, remaining_row_count)`
            after each row's patch is persisted — used only by the JUDGE_CHECK
            call site for run-wide judge-exclusion detection and the
            `_model_stability_changed` composite event. Kept out of this
            function's own body to stay free of judge-specific logic.
        before_group: Optional hook invoked once per `(provider_id, model_name)`
            group, after that group's own `token.raise_if_cancelled()` safe
            checkpoint and before its first row — used only by the INFERENCE
            call site to fire a model-switch-boundary warmup (STORY-075).
            `None` for JUDGE_CHECK and whenever warmup is disabled for the run.
    """
    for provider_id, model_name, group_rows in groups:
        token.raise_if_cancelled()  # model-switch safe checkpoint (STORY-075-AC-6)
        if before_group is not None:
            before_group(provider_id, model_name)
        for index, result in enumerate(group_rows):
            token.raise_if_cancelled()
            target_provider_id, target_model_name = stability_target_for(result)
            patch = run_task_with_stability(
                provider_id=target_provider_id,
                model_name=target_model_name,
                role=role,
                retry_count=retry_count,
                build_attempt=build_attempt_for(result),
                finalize_success=finalize_success_for(result),
                on_timeout_exhausted=on_timeout_exhausted_for(result),
                runner=runner,
                token=token,
                clock=clock,
                adaptive_timeout=adaptive_timeout,
                circuit_breaker=circuit_breaker,
            )
            results_store.update_result(result.result_id, patch)
            if after_row is not None:
                remaining = len(group_rows) - index - 1
                after_row(result, patch, remaining)


def run_all_phases(  # noqa: PLR0913  # every keyword-only argument is a distinct
    # collaborator of the whole-run phase loop (08-B §3); bundling them into a struct
    # would only indirect the read without reducing real coupling
    *,
    run_mode: RunMode,
    keyword_enabled: bool,
    cosine_enabled: bool,
    judge_enabled: bool,
    run_id: RunId,
    runner: TaskRunner[object],
    token: CancellationToken,
    results_store: ResultsStore,
    unit_factory_for_phase: Callable[[Phase, BenchmarkResult], Callable[[], ResultPatch]],
    stability_phase_runner: Callable[
        [Phase, tuple[tuple[ProviderIdStr, ModelNameStr, tuple[BenchmarkResult, ...]], ...]], None
    ]
    | None = None,
) -> None:
    """Drive every applicable phase to completion in strict order (08-B §3).

    Re-derives each phase's eligible set from freshly re-read persisted rows
    — a phase never begins until every eligible row of the prior phase left
    it, because eligibility itself is recomputed from what was just written.

    Args:
        run_mode: The run's fixed mode; only `GRADED` ever runs a grading phase.
        keyword_enabled: The run's resolved keyword-check toggle.
        cosine_enabled: The run's resolved cosine-check toggle.
        judge_enabled: The run's resolved judge-check toggle.
        run_id: The run whose rows are read fresh at the start of every phase.
        runner: The `TaskRunner` port each phase's units are submitted to.
            Unused directly by `INFERENCE`/`JUDGE_CHECK` when
            `stability_phase_runner` is supplied (STORY-030) — those two
            phases route through it instead.
        token: The run's `CancellationToken`, checked before every unit.
        results_store: The single-writer store rows are read from and
            written through.
        unit_factory_for_phase: Builds the blocking callable for one result
            row within a given phase — used for `KEYWORD_CHECK`/
            `COSINE_CHECK` (and for `INFERENCE`/`JUDGE_CHECK` when
            `stability_phase_runner` is `None`, preserved for callers that
            have not yet wired the stability stack).
        stability_phase_runner: When supplied, called instead of `run_phase`
            for `Phase.INFERENCE` and `Phase.JUDGE_CHECK` — a closure over
            `run_phase_with_stability` and this run's stability collaborators
            (STORY-030). `KEYWORD_CHECK`/`COSINE_CHECK` always use
            `unit_factory_for_phase`/`run_phase`, unaffected by this parameter.
    """
    for phase in PHASE_ORDER:
        if phase is Phase.INITIALIZATION:
            continue
        if not phase_applies(
            phase=phase,
            run_mode=run_mode,
            keyword_enabled=keyword_enabled,
            cosine_enabled=cosine_enabled,
            judge_enabled=judge_enabled,
        ):
            continue
        current_rows = results_store.list_results(run_id)
        eligible = eligible_for_phase(current_rows, phase=phase)
        groups = group_by_provider_and_model(eligible)
        if stability_phase_runner is not None and phase in (Phase.INFERENCE, Phase.JUDGE_CHECK):
            stability_phase_runner(phase, groups)
            continue
        run_phase(
            groups=groups,
            runner=runner,
            token=token,
            results_store=results_store,
            unit_factory=_bind_phase(phase, unit_factory_for_phase),
        )


def _bind_phase(
    phase: Phase,
    unit_factory_for_phase: Callable[[Phase, BenchmarkResult], Callable[[], ResultPatch]],
) -> Callable[[BenchmarkResult], Callable[[], ResultPatch]]:
    """Partially apply `phase` onto a per-phase unit factory for `run_phase`'s single-arg contract."""

    def _for_result(result: BenchmarkResult) -> Callable[[], ResultPatch]:
        return unit_factory_for_phase(phase, result)

    return _for_result
