"""Public surface for ``backend/retry/``: ``with_retry`` and ``default_transient_policy``.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/18_RETRY_POLICY.md``
§6.1 (the retry filter), §6.2 (per-category retry parameters), §6.3 (backoff
computation), §6.4 (honouring a provider retry-after), §6.5 (respecting cancellation).
"""

from collections.abc import Callable
import random
import time

import icontract

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.errors import TransientError
from ollama_llm_bench.backend.retry.models import RetryPolicy

__all__: list[str] = [
    "default_transient_policy",
    "with_retry",
]

_DEFAULT_INITIAL_WAIT_SECONDS = 0.5
_DEFAULT_MAX_WAIT_SECONDS = 8.0
_DEFAULT_JITTER_SECONDS = 1.0
_DEFAULT_TOTAL_BUDGET_SECONDS = 60.0


@icontract.require(lambda retry_count: retry_count >= 0, "retry_count must be non-negative")
@icontract.ensure(lambda result: result.attempts >= 1, "a policy must allow at least one attempt")
def default_transient_policy(*, retry_count: int = 3) -> RetryPolicy:
    """Build the default transient-category retry policy (§6.2).

    Args:
        retry_count: The ``benchmark.retry_count`` setting from the run's frozen
            settings snapshot; the number of retries *beyond* the first attempt.

    Returns:
        A ``RetryPolicy`` with ``attempts = 1 + retry_count``, ``initial_wait = 0.5s``,
        ``max_wait = 8.0s``, ``jitter = 1.0s``, ``total_budget = 60s``.
    """
    return RetryPolicy(
        attempts=1 + retry_count,
        initial_wait=_DEFAULT_INITIAL_WAIT_SECONDS,
        max_wait=_DEFAULT_MAX_WAIT_SECONDS,
        jitter=_DEFAULT_JITTER_SECONDS,
        total_budget=_DEFAULT_TOTAL_BUDGET_SECONDS,
    )


@icontract.require(lambda policy: policy.attempts >= 1, "policy.attempts must be >= 1")
@icontract.require(lambda policy: policy.initial_wait >= 0, "policy.initial_wait must be >= 0")
@icontract.require(lambda policy: policy.max_wait >= 0, "policy.max_wait must be >= 0")
@icontract.require(lambda policy: policy.jitter >= 0, "policy.jitter must be >= 0")
@icontract.require(lambda policy: policy.total_budget >= 0, "policy.total_budget must be >= 0")
def with_retry[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    token: CancellationToken,
) -> T:
    """Run ``operation``, retrying only a ``TransientError`` with bounded backoff.

    Retries are decided on the category root, never a leaf list (§6.1): a new
    ``TransientError`` subclass is retried automatically with no change to this
    function. Every other exception — ``PermanentError``, ``UserError`` (including
    ``TaskCancelledError``), or a ``ProgrammerError`` — propagates immediately on its
    first occurrence; a ``ProgrammerError`` is never even caught, because it descends
    from ``BaseException`` outside ``Exception``.

    Args:
        operation: The blocking, zero-argument callable to run and retry.
        policy: The attempt/backoff/budget parameters governing this call.
        token: The per-run cooperative cancellation handle, checked at the start of
            every attempt and used for the cancellation-aware backoff sleep.

    Returns:
        The value returned by ``operation`` on the attempt that succeeds.

    Raises:
        TransientError: Every allowed attempt failed, or the cumulative elapsed time
            would exceed ``policy.total_budget`` before the next attempt; the last
            error is re-raised with its ``__cause__`` chain intact.
        PermanentError: ``operation`` raised a non-transient application error.
        UserError: ``operation`` raised a user error, including a cancellation
            requested by the caller (``TaskCancelledError``).
    """
    start_monotonic = time.monotonic()

    for attempt_index in range(1, policy.attempts + 1):
        token.raise_if_cancelled()
        try:
            return operation()
        except TransientError as error:
            is_last_attempt = attempt_index == policy.attempts
            retry_after = getattr(error, "retry_after", None)
            override = min(float(retry_after), policy.max_wait) if retry_after is not None else None
            wait_seconds = _compute_wait(
                policy=policy,
                attempt_index=attempt_index,
                override=override,
            )
            elapsed = time.monotonic() - start_monotonic
            if is_last_attempt or elapsed + wait_seconds > policy.total_budget:
                raise
            token.wait(wait_seconds)

    message = "unreachable: with_retry loop must return or raise before exhausting range"
    raise AssertionError(message)


def _compute_wait(*, policy: RetryPolicy, attempt_index: int, override: float | None) -> float:
    """Compute the backoff wait before the attempt following ``attempt_index`` (§6.3).

    Applies the ``retry_after`` override (already clamped to ``policy.max_wait`` by
    the caller) in place of the exponential formula when one is supplied.
    """
    if override is not None:
        return max(0.0, override)
    base: float = min(policy.initial_wait * 2 ** (attempt_index - 1), policy.max_wait)
    jitter: float = random.uniform(-policy.jitter, policy.jitter)  # noqa: S311  # not cryptographic
    wait: float = max(0.0, base + jitter)
    return wait
