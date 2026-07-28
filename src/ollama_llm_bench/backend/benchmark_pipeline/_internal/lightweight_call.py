"""The shared blocking call shape behind `run_model_warmup` and `run_provider_probe`
(STORY-100, ADR-0013).

Builds one `ChatRequest` from the fixed `WARMUP_PROMPT`/`WARMUP_MAX_OUTPUT_TOKENS`
payload, resolves the target's `LLMClient`, submits the blocking `chat` call to the
`TaskRunner`, and wraps the whole thing in a fixed-attempt-count `with_retry`. This
module only RAISES — it never classifies an outcome and performs no breaker or
adaptive-timeout writes; that is exclusively `_internal.warmup.run_model_warmup`'s and
`_internal.provider_probe.run_provider_probe`'s job, because the two callers' outcome
semantics genuinely differ (a good warmup on model B must never reset a failure run
spanning models A and B, while a successful probe must close the breaker) — see those
two modules' own docstrings for the full rationale. Do not fold the two callers into
this module or give this function a mode flag; only the call *shape* is shared.

Sized by the role=INFERENCE adaptive ladder (DD-64) for both callers. Runs on the
dispatcher thread; only the blocking `chat` call is submitted to a worker, matching
`_internal.stability_dispatch.run_task_with_stability`'s own thread-affinity rule for
the stability services (`concurrency-standard.md`).
"""

from typing import Final

from ollama_llm_bench.backend.adaptive_timeout.protocols import AdaptiveTimeoutService
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.concurrency.protocols import TaskRunner
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatRole,
    ModelName,
    ProviderId,
)
from ollama_llm_bench.backend.provider_registry.protocols import ProviderRegistry
from ollama_llm_bench.backend.retry import default_transient_policy, with_retry

__all__: list[str] = ["WARMUP_MAX_OUTPUT_TOKENS", "WARMUP_PROMPT", "issue_lightweight_call"]

WARMUP_PROMPT: Final[str] = "Reply with exactly: OK"  # owner-settled, 2026-07-22
WARMUP_MAX_OUTPUT_TOKENS: Final[int] = 16  # owner-settled, 2026-07-22
_MS_PER_SECOND: Final[int] = 1000


def issue_lightweight_call(  # noqa: PLR0913  # each keyword-only argument is a
    # distinct dispatcher-thread collaborator the shared call shape needs, mirroring
    # `run_model_warmup`'s and `run_provider_probe`'s own flat parameter lists
    *,
    provider_id: ProviderId,
    model_name: ModelName,
    provider_registry: ProviderRegistry,
    adaptive_timeout: AdaptiveTimeoutService,
    attempts: int,
    budget_attempt_offset: int,
    runner: TaskRunner[ChatResponse],
    token: CancellationToken,
) -> ChatResponse:
    """Issue the shared warmup/probe call shape and return its response.

    Runs up to `attempts` attempts through `with_retry`'s own transient-only
    retry filter and backoff, each sized by
    `adaptive_timeout.next_budget(provider_id, model_name,
    AdaptiveTimeoutRole.INFERENCE, attempt_index=<loop attempt number> +
    budget_attempt_offset)`. `run_model_warmup` passes `attempts=1 +
    retry_count` and `budget_attempt_offset=0` — the same ladder walk it
    always used. `run_provider_probe` passes `attempts=1` and
    `budget_attempt_offset=retry_count`, so its one and only attempt draws
    the same top-of-ladder budget a real task's final retry would receive,
    while `with_retry`'s own single-attempt policy (`attempts=1`) makes no
    second attempt on failure — ADR-0013's one-attempt shape, enforced by
    `with_retry`'s existing loop rather than a bespoke bypass of it.

    Args:
        provider_id: The call target's provider.
        model_name: The call target's model.
        provider_registry: Resolves `provider_id` to a live `LLMClient`.
        adaptive_timeout: Touched only from this function — one
            `next_budget` query per attempt. `next_budget` is not a pure
            read: it also materializes/updates the target's adaptive-timeout
            bucket (see `AdaptiveTimeoutService.next_budget`'s own
            contract). No outcome-reporting method
            (`record_success`/`record_timeout`) is ever called here; that
            distinction, not "read-only", is what this module's callers
            actually rely on.
        attempts: The total attempt count `with_retry`'s policy allows.
        budget_attempt_offset: Added to each loop-local 1-based attempt
            number before it is used to query `next_budget`'s ladder
            position.
        runner: The `TaskRunner` each attempt's single blocking `chat` call
            is submitted to.
        token: The run's live `CancellationToken`.

    Returns:
        The `ChatResponse` from whichever attempt succeeds.

    Raises:
        TransientError: Every allowed attempt failed transiently, or the
            retry budget was exhausted before the next attempt.
        PermanentError: The provider rejected the request with a permanent
            error.
        UserError: A configuration/auth error occurred, or `token` observed
            a cancellation (`TaskCancelledError`).
    """
    attempt_index = 0

    def _one_attempt() -> ChatResponse:
        nonlocal attempt_index
        attempt_index += 1
        budget_seconds = adaptive_timeout.next_budget(
            provider_id,
            model_name,
            AdaptiveTimeoutRole.INFERENCE,
            attempt_index=attempt_index + budget_attempt_offset,
        )
        request = ChatRequest(
            model=model_name,
            messages=(ChatMessage(role=ChatRole.USER, content=WARMUP_PROMPT),),
            timeout_ms=budget_seconds * _MS_PER_SECOND,
            temperature=0.0,
            max_output_tokens=WARMUP_MAX_OUTPUT_TOKENS,
        )
        client = provider_registry.get_client(provider_id)
        return runner.submit(lambda: client.chat(request, token=token), token=token).result()

    policy = default_transient_policy(retry_count=attempts - 1)
    return with_retry(_one_attempt, policy=policy, token=token)
