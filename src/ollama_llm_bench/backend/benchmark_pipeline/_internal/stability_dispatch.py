"""Dispatcher-thread retry orchestration wiring `AdaptiveTimeoutService` and
`ProviderCircuitBreaker` around one result row's attempt sequence (STORY-030).

Touches both stability services ONLY from code that runs on the calling (dispatcher)
thread — never from inside a callable passed to `TaskRunner.submit()` — per
`concurrency-standard.md` and this story's architecture-test Definition of Done. Each
attempt's actual blocking call is its own separate `TaskRunner` submission;
`backend/retry`'s `with_retry` loop (attempt cap, backoff, cancellation) runs on the
dispatcher thread and blocks only on that per-attempt `Future`. This is the "one
pipeline unit inside a retry wrapper at any moment" design of
`11_Services_and_Algorithms/18_RETRY_POLICY.md` §9, resolved for this codebase's
stricter dispatcher-thread-only stability-service rule (`16_CONCURRENCY_MODEL.md`
§6.6, `04_CONCURRENCY_STANDARD.md`): the retry loop itself is dispatcher-thread code,
and only the single blocking call per attempt is submitted to a worker.
"""

from collections.abc import Callable

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.containment import contain_unit_failure
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    ErrorKind,
    ModelName,
    ProviderId,
    ResultPatch,
    ResultStatus,
)
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpTimeoutError,
    TaskCancelledError,
    TransientError as _TransientError,
)
from ollama_llm_bench.backend.infra.protocols import Clock
from ollama_llm_bench.backend.retry import default_transient_policy, with_retry

__all__: list[str] = ["run_task_with_stability"]

_MS_PER_SECOND = 1000


def run_task_with_stability[T](  # noqa: PLR0913  # each parameter is a distinct
    # collaborator this dispatcher-thread orchestrator needs: the stability target,
    # the role, the attempt-cap input, the three per-outcome closures the caller
    # varies per phase, and the runner/token/clock/service collaborators — bundling
    # them would only indirect the read without reducing real coupling
    *,
    provider_id: ProviderId,
    model_name: ModelName,
    role: AdaptiveTimeoutRole,
    retry_count: int,
    build_attempt: Callable[[int], Callable[[], T]],
    finalize_success: Callable[[T], ResultPatch],
    on_timeout_exhausted: Callable[[], ResultPatch],
    runner: TaskRunner[T],
    token: CancellationToken,
    clock: Clock,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
) -> ResultPatch:
    """Run one task's phase call with the full stability stack, on the dispatcher thread.

    Consults the `ProviderCircuitBreaker` and `AdaptiveTimeoutService` before any
    network call, submits exactly one attempt at a time to `runner`, blocks on each
    attempt's `Future`, and reports every clean outcome back to both services — all
    from the calling thread, which must be the dispatcher thread.

    Args:
        provider_id: The stability target's provider — the row's own provider for
            `role=INFERENCE`, or the run's fixed judge provider for `role=JUDGE`.
        model_name: The stability target's model, same rule as `provider_id`.
        role: Selects the `AdaptiveTimeoutService` bucket and parameter set.
        retry_count: The run's resolved `benchmark.retry_count` setting; sizes the
            attempt cap `with_retry` applies (the role-appropriate per-attempt
            budget ceiling is applied by `AdaptiveTimeoutService.next_budget`
            itself, independently).
        build_attempt: Builds one attempt's single-shot callable given a
            `timeout_ms` budget. Returns a nullary callable executed on a worker
            thread via `runner.submit`; raises an `AppError` leaf uncaught on
            failure (classified here, never inside the callable).
        finalize_success: Converts the winning attempt's raw return value into the
            phase's terminal `ResultPatch` (the verdict-combination step).
        on_timeout_exhausted: Builds the terminal `ResultPatch` for the
            role-appropriate timeout-exhaustion outcome (`FAILED_TIMEOUT` for
            `role=INFERENCE` via `contain_unit_failure`, `FAILED_JUDGE_TIMEOUT`
            for `role=JUDGE` via a dedicated builder) — the one place the two
            roles' handling genuinely diverges. Also used for the pre-attempt
            fast path when the target is already excluded.
        runner: The `TaskRunner` each individual attempt is submitted to.
        token: The run's `CancellationToken`.
        clock: Used to time each successful attempt for `record_success`'s
            `observed_ms`.
        adaptive_timeout: Touched only from this function, never from
            `build_attempt`'s returned callable.
        circuit_breaker: Touched only from this function, same rule.

    Returns:
        The phase's terminal `ResultPatch` — from `finalize_success`,
        `on_timeout_exhausted`, or the generic non-timeout exhaustion/permanent-error
        path (`contain_unit_failure`).

    Raises:
        TaskCancelledError: Propagates uncontained to the dispatcher's halt path,
            per the existing per-unit contract (`build_inference_unit`/
            `build_judge_unit` already document and rely on this) — a cancelled
            attempt reports no outcome to either stability service.
    """
    if circuit_breaker.should_skip(provider_id):
        return ResultPatch(
            status=ResultStatus.FAILED_PROVIDER,
            error_kind=ErrorKind.PROVIDER,
            error_message="Provider circuit breaker is tripped; skipped without a network call.",
        )
    if adaptive_timeout.is_excluded(provider_id, model_name, role):
        return on_timeout_exhausted()

    attempt_index = 0

    def operation() -> T:
        nonlocal attempt_index
        attempt_index += 1
        budget_seconds = adaptive_timeout.next_budget(
            provider_id, model_name, role, attempt_index=attempt_index
        )
        attempt_unit = build_attempt(budget_seconds * _MS_PER_SECOND)
        started_at_ms = clock.monotonic_ms()
        try:
            raw = runner.submit(attempt_unit, token=token).result()
        except HttpTimeoutError:
            adaptive_timeout.record_timeout(provider_id, model_name, role)
            raise
        observed_ms = clock.monotonic_ms() - started_at_ms
        adaptive_timeout.record_success(provider_id, model_name, role, observed_ms)
        return raw

    policy = default_transient_policy(retry_count=retry_count)
    try:
        raw_result = with_retry(operation, policy=policy, token=token)
    except TaskCancelledError:
        raise
    except HttpTimeoutError:
        # A per-task timeout is a MODEL-level signal, never a provider-attributable one:
        # it feeds only the adaptive-timeout service (which escalates this model's budget
        # and can exclude this one model), and must NOT reach the breaker — otherwise one
        # slow model would skip every other model on the same provider
        # (08_CIRCUIT_BREAKER.md §6.4 MISS-25, §6.9). The breaker's timeout signal comes
        # exclusively from the warmup probe at a model switch (`_internal/warmup.py`).
        # This clause MUST stay above `except _TransientError` — HttpTimeoutError is a
        # TransientError subclass, and reordering would silently restore the failure count.
        return on_timeout_exhausted()
    except _TransientError as exc:
        circuit_breaker.record_failure(provider_id)
        return contain_unit_failure(exc)
    except AppError as exc:
        return contain_unit_failure(exc)

    circuit_breaker.record_success(provider_id)
    return finalize_success(raw_result)
