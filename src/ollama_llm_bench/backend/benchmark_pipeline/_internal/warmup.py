"""Model-switch warmup: pre-load one (provider, model) test target (STORY-075).

Sized by the role=INFERENCE adaptive ladder (DD-64); its outcome feeds the
provider circuit breaker's liveness verdict, never this run's result rows and
never the adaptive-timeout model-exclusion counter (`07_ADAPTIVE_TIMEOUT.md`
§4, `08_CIRCUIT_BREAKER.md` §6.4/§6.9). Runs on the dispatcher thread; only
the blocking `chat` call is submitted to a worker, matching
`_internal.stability_dispatch.run_task_with_stability`'s own thread-affinity
rule for the two stability services.

The blocking call shape itself lives in `_internal.lightweight_call`, shared
with `_internal.provider_probe.run_provider_probe` (STORY-100); the two
callers' outcome handling stays deliberately separate — see
`_internal.lightweight_call`'s module docstring for why.
"""

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.lightweight_call import (
    WARMUP_MAX_OUTPUT_TOKENS,
    WARMUP_PROMPT,
    issue_lightweight_call,
)
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.protocols import ProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    ChatResponse,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.errors import (
    AppError,
    HttpConnectionError,
    HttpTimeoutError,
    TaskCancelledError,
)
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry

__all__: list[str] = ["WARMUP_MAX_OUTPUT_TOKENS", "WARMUP_PROMPT", "run_model_warmup"]


def run_model_warmup(  # noqa: PLR0913  # each keyword-only argument is a distinct
    # dispatcher-thread collaborator this warmup needs, mirroring
    # `run_task_with_stability`'s own flat, ungrouped parameter list
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
    """Issue one lightweight pre-load inference and report its liveness.

    Skips outright when the provider's breaker is not `CLOSED` (a probe
    admission is a distinct call site owned by the breaker's own
    post-cooldown lazy transition, STORY-023/STORY-030 — never consumed
    here) or when the target is already excluded for `role=INFERENCE`.
    Otherwise runs the full `1 + retry_count` attempt ladder, sized at each
    attempt by the target's role=INFERENCE adaptive-timeout budget. Every
    response — a normal completion or a model-side error — is
    liveness-neutral; a ladder-exhausted timeout or a connection/transport
    error reports `record_failure(provider_id)`. Never calls
    `record_success` on either service, never calls `record_timeout` on the
    adaptive-timeout service, and writes no `BenchmarkResult` row.

    Args:
        provider_id: The warmup target's provider.
        model_name: The warmup target's model.
        provider_registry: Resolves `provider_id` to a live `LLMClient`.
        adaptive_timeout: Touched only from this function, never from the
            worker-submitted `chat` callable — read-only `next_budget`/
            `is_excluded` queries only; no adaptive-timeout state is ever
            written by a warmup.
        circuit_breaker: Touched only from this function, same rule as
            `adaptive_timeout`; a read-only `state()` query plus, on a
            no-response failure, `record_failure`.
        retry_count: The run's resolved `benchmark.retry_count` setting;
            sizes the attempt cap the same way an ordinary inference call
            does.
        runner: The `TaskRunner` the warmup's single blocking `chat` call
            per attempt is submitted to.
        token: The run's live `CancellationToken`.

    Raises:
        TaskCancelledError: The run was cancelled mid-warmup; reports
            neither a success nor a failure to the circuit breaker.
    """
    if circuit_breaker.state(provider_id) is not CircuitState.CLOSED:
        return
    if adaptive_timeout.is_excluded(provider_id, model_name, AdaptiveTimeoutRole.INFERENCE):
        return

    try:
        issue_lightweight_call(
            provider_id=provider_id,
            model_name=model_name,
            provider_registry=provider_registry,
            adaptive_timeout=adaptive_timeout,
            attempts=1 + retry_count,
            budget_attempt_offset=0,
            runner=runner,
            token=token,
        )
    except TaskCancelledError:
        raise
    except (HttpTimeoutError, HttpConnectionError):
        circuit_breaker.record_failure(provider_id)
    except AppError:
        return
