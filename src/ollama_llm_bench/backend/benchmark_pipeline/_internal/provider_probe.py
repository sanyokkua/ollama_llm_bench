"""The circuit breaker's dedicated post-cooldown liveness probe (STORY-100, ADR-0013).

Per DD-71 (`08_Cross_Cutting/08-F_spec_issues_log.md`), a `PROBING` provider's
liveness is decided by a dedicated, single-attempt, short-budget call issued by the
pipeline itself — never by admitting the next real benchmark task as the probe. This
closes the liveness gap the old real-task-probe design had: several dispatcher error
paths reported no outcome to the breaker, so a `PROBING` provider with its probe slot
claimed but never resolved stayed permanently unusable for the rest of the run
(ADR-0013's Context section).

`run_provider_probe` is invoked once per row from `_internal.dispatcher`'s per-row
`before_row` hook (not the per-group `before_group` warmup hook) — a run against a
single `(provider, model)` group would otherwise never revisit the provider once it
trips, since no later group boundary exists to notice the cooldown's expiry.
"""

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.lightweight_call import (
    issue_lightweight_call,
)
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import ChatResponse, ModelName, ProviderId
from ollama_llm_bench.backend.errors import (
    AppError,
    ConfigurationError,
    HttpConnectionError,
    HttpTimeoutError,
    MissingEnvVarError,
    TaskCancelledError,
)
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry

__all__: list[str] = ["run_provider_probe"]

_SINGLE_ATTEMPT = 1


def run_provider_probe(  # noqa: PLR0913  # each keyword-only argument is a distinct
    # dispatcher-thread collaborator this probe needs, mirroring
    # `run_model_warmup`'s own flat, ungrouped parameter list
    *,
    provider_id: ProviderId,
    model_name: ModelName,
    provider_registry: ProviderRegistry,
    adaptive_timeout: AdaptiveTimeoutService,
    circuit_breaker: ProviderCircuitBreaker,
    retry_count: int,
    runner: TaskRunner[ChatResponse],
    token: CancellationToken,
) -> None:
    """Issue the breaker's dedicated post-cooldown liveness call (ADR-0013).

    Returns immediately unless `circuit_breaker.state(provider_id)` is
    `CircuitState.PROBING` — a `CLOSED` or `TRIPPED` provider makes no
    network call and touches no other breaker method. When `PROBING`, issues
    exactly one lightweight liveness call at the first-attempt adaptive
    budget (`adaptive_timeout.next_budget(..., attempt_index=1 +
    retry_count)`) — no retry ladder, no backoff, no second attempt — and
    maps its outcome onto exactly one breaker call, per ADR-0013's outcome
    table: any `ChatResponse`, or any other provider-response `AppError`
    (401/404/400/422/429/5xx/…), means the provider answered and is alive
    (`record_success`); `HttpTimeoutError`/`HttpConnectionError`, or a
    pre-call `ConfigurationError`/`MissingEnvVarError` raised by
    `get_client()` before any network attempt, means still down
    (`record_failure`).

    Deliberately does **not** consult `adaptive_timeout.is_excluded`, unlike
    `run_model_warmup`'s guard: an excluded model is still a valid liveness
    target for the breaker's own recovery — that per-role exclusion
    bookkeeping is independent of whether the provider itself is reachable.

    Invariant: no exit path other than `TaskCancelledError` leaves the
    provider `PROBING` — every other reachable outcome calls exactly one of
    `record_success`/`record_failure` before returning. A bare
    `except AppError: return` is forbidden in this function; every `AppError`
    branch below ends in a breaker call.

    Args:
        provider_id: The probe target's provider.
        model_name: The probe target's model — the row's own test model when
            called from the INFERENCE phase's `before_row` hook, or the
            run's fixed judge model when called from the JUDGE_CHECK phase's.
        provider_registry: Resolves `provider_id` to a live `LLMClient`.
        adaptive_timeout: Touched only from this function, never from a
            worker-submitted callable — a read-only `next_budget` query
            only; no adaptive-timeout state is ever written by a probe.
        circuit_breaker: Touched only from this function, same rule: a
            read-only `state()` query plus exactly one of `record_success`/
            `record_failure` on every non-cancellation exit.
        retry_count: The run's resolved `benchmark.retry_count` setting;
            selects where on the adaptive-timeout ladder the probe's single
            budget is drawn from — it does not drive a retry loop here.
        runner: The `TaskRunner` the probe's single blocking `chat` call is
            submitted to.
        token: The run's live `CancellationToken`.

    Raises:
        TaskCancelledError: The run was cancelled mid-probe; reports neither
            a success nor a failure to the circuit breaker.
    """
    if circuit_breaker.state(provider_id) is not CircuitState.PROBING:
        return

    try:
        issue_lightweight_call(
            provider_id=provider_id,
            model_name=model_name,
            provider_registry=provider_registry,
            adaptive_timeout=adaptive_timeout,
            attempts=_SINGLE_ATTEMPT,
            budget_attempt_offset=retry_count,
            runner=runner,
            token=token,
        )
    except TaskCancelledError:
        raise
    except (HttpTimeoutError, HttpConnectionError, ConfigurationError, MissingEnvVarError):
        circuit_breaker.record_failure(provider_id)
        return
    except AppError:
        circuit_breaker.record_success(provider_id)
        return
    circuit_breaker.record_success(provider_id)
