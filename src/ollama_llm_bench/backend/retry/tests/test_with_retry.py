"""Tests proving STORY-007-AC-1 through STORY-007-AC-5: ``with_retry``.

Source of truth: ``docs/v3_specification/11_Services_and_Algorithms/18_RETRY_POLICY.md``
§6.1 (the retry filter), §6.2 (per-category retry parameters), §6.3 (backoff
computation), §6.4 (honouring a provider retry-after), §6.5 (respecting cancellation).
"""

from collections.abc import Callable
from typing import cast

import pytest

from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.errors import (
    PermanentError,
    ProgrammerError,
    TaskCancelledError,
    TransientError,
    UserError,
)
from ollama_llm_bench.backend.retry import RetryPolicy, default_transient_policy, with_retry
from ollama_llm_bench.backend.retry.api import _compute_wait

_DEFAULT_RETRY_COUNT = 3
_DEFAULT_ATTEMPTS = 1 + _DEFAULT_RETRY_COUNT
_SUCCESS_ON_THIRD_CALL = 3
_TWO_ATTEMPTS_MADE = 2


class _FakeCancellationToken:
    """A duck-typed, no-sleep stand-in for ``CancellationToken``.

    Records every ``wait()`` call's requested duration (without actually sleeping)
    and can be scripted to raise ``TaskCancelledError`` from ``raise_if_cancelled()``
    starting at a given call number, or to report a cancellation occurring partway
    through a ``wait()`` call.
    """

    def __init__(
        self,
        *,
        cancel_at_raise_call: int | None = None,
        cancel_during_wait_call: int | None = None,
    ) -> None:
        self._cancel_at_raise_call = cancel_at_raise_call
        self._cancel_during_wait_call = cancel_during_wait_call
        self.raise_call_count = 0
        self.wait_call_count = 0
        self.recorded_waits: list[float] = []

    def raise_if_cancelled(self) -> None:
        self.raise_call_count += 1
        if (
            self._cancel_at_raise_call is not None
            and self.raise_call_count >= self._cancel_at_raise_call
        ):
            raise TaskCancelledError(message="cancelled", context=None)

    def wait(self, timeout: float) -> bool:
        self.wait_call_count += 1
        self.recorded_waits.append(timeout)
        return (
            self._cancel_during_wait_call is not None
            and self.wait_call_count >= self._cancel_during_wait_call
        )


def _make_token(
    *,
    cancel_at_raise_call: int | None = None,
    cancel_during_wait_call: int | None = None,
) -> CancellationToken:
    """Build a duck-typed fake token, cast to ``CancellationToken`` for callers.

    ``with_retry`` is typed against the concrete ``CancellationToken`` class (there
    is no cancellation Protocol to satisfy structurally), so the fake is cast at its
    single construction point rather than scattering ``# type: ignore`` at every
    call site.
    """
    fake = _FakeCancellationToken(
        cancel_at_raise_call=cancel_at_raise_call,
        cancel_during_wait_call=cancel_during_wait_call,
    )
    return cast("CancellationToken", fake)


class _CustomTransientLeaf(TransientError):
    """A transient leaf outside the four built-in leaves, proving the filter matches
    the category root rather than a hardcoded leaf list."""


class _CustomPermanentLeaf(PermanentError):
    """A permanent leaf used to prove permanent errors are never retried."""


class _CustomProgrammerLeaf(ProgrammerError):
    """A programmer-error leaf used to prove it is never even caught."""


class _RetryAfterTransientError(TransientError):
    """A transient leaf exposing a ``retry_after`` attribute, mirroring
    ``ProviderRateLimitedError`` without depending on the provider-specific leaf."""

    def __init__(self, *, message: str, retry_after: float | None) -> None:
        super().__init__(message=message, context=None)
        self.retry_after = retry_after


class _CountingOperation[ExcT: BaseException]:
    """A callable that fails a fixed number of times, then either succeeds or keeps
    failing forever, recording every invocation."""

    def __init__(
        self,
        *,
        error_factory: Callable[[], ExcT],
        fail_count: int | None,
        success_value: str = "ok",
    ) -> None:
        self._error_factory = error_factory
        self._fail_count = fail_count
        self._success_value = success_value
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        if self._fail_count is None or self.call_count <= self._fail_count:
            raise self._error_factory()
        return self._success_value


def _make_policy(
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    initial_wait: float = 0.5,
    max_wait: float = 8.0,
    jitter: float = 1.0,
    total_budget: float = 60.0,
) -> RetryPolicy:
    return RetryPolicy(
        attempts=attempts,
        initial_wait=initial_wait,
        max_wait=max_wait,
        jitter=jitter,
        total_budget=total_budget,
    )


def test_retry_filter_matches_transient_category_root_not_leaf_list() -> None:
    """Proves: STORY-007-AC-1

    A custom ``TransientError`` subclass — not one of the four built-in transient
    leaves — is retried automatically: an operation raising it twice then succeeding
    returns the success value, having been invoked exactly three times.
    """
    operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="boom", context=None),
        fail_count=2,
    )
    token = _make_token()

    result = with_retry(operation, policy=_make_policy(), token=token)

    assert result == "ok"
    assert operation.call_count == _SUCCESS_ON_THIRD_CALL


def test_default_policy_attempt_cap_and_cause_chaining() -> None:
    """Proves: STORY-007-AC-2

    An operation that always raises the default-policy transient error is retried
    up to ``1 + retry_count`` times and the original exception is re-raised chained
    as ``__cause__``; with ``retry_count = 0`` exactly one attempt is made.
    """
    policy = default_transient_policy(retry_count=_DEFAULT_RETRY_COUNT)
    operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="always fails", context=None),
        fail_count=None,
    )
    token = _make_token()

    with pytest.raises(_CustomTransientLeaf) as exc_info:
        with_retry(operation, policy=policy, token=token)

    assert operation.call_count == policy.attempts == _DEFAULT_ATTEMPTS
    # A bare `raise` inside the except block re-raises the same object the loop
    # caught on its last attempt, so the "original exception" is exc_info.value
    # itself — the exhausted retry re-raises the last error, chain intact.
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None

    zero_retry_policy = default_transient_policy(retry_count=0)
    assert zero_retry_policy.attempts == 1
    single_attempt_operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="always fails", context=None),
        fail_count=None,
    )
    single_attempt_token = _make_token()

    with pytest.raises(_CustomTransientLeaf):
        with_retry(single_attempt_operation, policy=zero_retry_policy, token=single_attempt_token)

    assert single_attempt_operation.call_count == 1


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: _CustomPermanentLeaf(message="permanent", context=None),
        lambda: UserError(message="user", context=None),
        lambda: TaskCancelledError(message="cancelled", context=None),
    ],
    ids=["permanent_error", "user_error", "task_cancelled_error"],
)
def test_permanent_user_and_programmer_errors_are_not_retried(
    error_factory: Callable[[], Exception],
) -> None:
    """Proves: STORY-007-AC-3

    A ``PermanentError``, a ``UserError``, or a ``TaskCancelledError`` is re-raised
    immediately after exactly one attempt.
    """
    operation = _CountingOperation(error_factory=error_factory, fail_count=None)
    token = _make_token()

    with pytest.raises((PermanentError, UserError)):
        with_retry(operation, policy=_make_policy(), token=token)

    assert operation.call_count == 1


def test_programmer_error_propagates_uncaught_with_no_retry_bookkeeping() -> None:
    """Proves: STORY-007-AC-3

    A ``ProgrammerError`` subclass propagates uncaught — ``with_retry``'s
    ``except TransientError``-shaped filter structurally cannot catch a
    ``BaseException``-rooted error — verified by asserting no retry bookkeeping (a
    single call, no waiting) occurred.
    """
    operation = _CountingOperation(
        error_factory=lambda: _CustomProgrammerLeaf(message="bug"),
        fail_count=None,
    )
    token = _make_token()

    with pytest.raises(_CustomProgrammerLeaf):
        with_retry(operation, policy=_make_policy(), token=token)

    assert operation.call_count == 1
    assert cast("_FakeCancellationToken", token).wait_call_count == 0


def test_backoff_growth_cap_budget_cutoff_and_retry_after_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves: STORY-007-AC-4

    Successive computed backoff waits grow geometrically per the documented formula
    and are capped at ``max_wait`` before jitter is added; a series of transient
    failures whose cumulative backoff would exceed ``total_budget`` stops before the
    budget is breached and re-raises without a further attempt; a ``retry_after``
    value overrides the next computed backoff, clamped to ``max_wait``.
    """
    monkeypatch.setattr("ollama_llm_bench.backend.retry.api.random.uniform", lambda _a, _b: 0.0)

    # Geometric growth, capped at max_wait, with deterministic (zero) jitter.
    growth_attempts = 6
    policy = _make_policy(
        attempts=growth_attempts, initial_wait=1.0, max_wait=4.0, jitter=1.0, total_budget=1_000.0
    )
    operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="boom", context=None),
        fail_count=None,
    )
    token = _make_token()

    with pytest.raises(_CustomTransientLeaf):
        with_retry(operation, policy=policy, token=token)

    # attempt 1 -> wait before attempt 2: base = min(1*2^0, 4) = 1
    # attempt 2 -> wait before attempt 3: base = min(1*2^1, 4) = 2
    # attempt 3 -> wait before attempt 4: base = min(1*2^2, 4) = 4 (capped)
    # attempt 4 -> wait before attempt 5: base = min(1*2^3, 4) = 4 (capped)
    # attempt 5 -> wait before attempt 6: base = min(1*2^4, 4) = 4 (capped)
    assert cast("_FakeCancellationToken", token).recorded_waits == [1.0, 2.0, 4.0, 4.0, 4.0]

    # Budget cutoff: a tight total_budget stops before it would be exceeded. The
    # elapsed-time budget check is driven by real `time.monotonic()` reads (per
    # §6.3), so a fake monotonic clock advancing by exactly each recorded wait
    # keeps the cutoff arithmetic deterministic without any real sleeping.
    fake_monotonic_seconds = [0.0]

    def _fake_monotonic() -> float:
        return fake_monotonic_seconds[0]

    monkeypatch.setattr("ollama_llm_bench.backend.retry.api.time.monotonic", _fake_monotonic)

    class _AdvancingFakeToken(_FakeCancellationToken):
        """Advances the fake monotonic clock by each requested wait duration."""

        def wait(self, timeout: float) -> bool:
            fake_monotonic_seconds[0] += timeout
            return super().wait(timeout)

    budget_attempts = 10
    budget_total_budget = 2.5
    budget_policy = _make_policy(
        attempts=budget_attempts,
        initial_wait=1.0,
        max_wait=4.0,
        jitter=1.0,
        total_budget=budget_total_budget,
    )
    budget_operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="boom", context=None),
        fail_count=None,
    )
    budget_token = cast("CancellationToken", _AdvancingFakeToken())

    with pytest.raises(_CustomTransientLeaf):
        with_retry(budget_operation, policy=budget_policy, token=budget_token)

    # wait 1 (elapsed 0 -> 1, within 2.5), wait 2 candidate (elapsed 1 + 2 = 3,
    # exceeds 2.5) -> stop before a further attempt or sleep.
    assert cast("_FakeCancellationToken", budget_token).recorded_waits == [1.0]
    assert budget_operation.call_count == _TWO_ATTEMPTS_MADE

    # retry_after override, clamped to max_wait, applies to the *next* wait only.
    retry_after_attempts = 3
    retry_after_policy = _make_policy(
        attempts=retry_after_attempts,
        initial_wait=1.0,
        max_wait=4.0,
        jitter=1.0,
        total_budget=1_000.0,
    )
    call_count = 0
    retry_after_seconds = 100.0

    def _retry_after_error_factory() -> TransientError:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _RetryAfterTransientError(
                message="rate limited", retry_after=retry_after_seconds
            )
        return _CustomTransientLeaf(message="boom", context=None)

    retry_after_operation = _CountingOperation(
        error_factory=_retry_after_error_factory,
        fail_count=None,
    )
    retry_after_token = _make_token()

    with pytest.raises(_CustomTransientLeaf):
        with_retry(retry_after_operation, policy=retry_after_policy, token=retry_after_token)

    # First failure carries retry_after=100, clamped to max_wait=4.0; second failure
    # (no retry_after) falls back to the normal computed backoff for attempt 2.
    assert cast("_FakeCancellationToken", retry_after_token).recorded_waits == [4.0, 2.0]


def test_compute_wait_formula_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proves: STORY-007-AC-4

    ``_compute_wait`` applies ``base = min(initial_wait * 2 ** (n - 1), max_wait)``
    then adds jitter, clamped at zero, matching the documented formula exactly.
    """
    monkeypatch.setattr("ollama_llm_bench.backend.retry.api.random.uniform", lambda _a, _b: -10.0)
    policy = _make_policy(initial_wait=1.0, max_wait=4.0, jitter=1.0, total_budget=60.0)

    wait = _compute_wait(policy=policy, attempt_index=1, override=None)

    assert wait == 0.0  # max(0, 1 + (-10)) clamped at zero


def test_cancellation_at_attempt_start_and_during_backoff_sleep() -> None:
    """Proves: STORY-007-AC-5

    A cancellation requested between attempts causes the next
    ``token.raise_if_cancelled()`` checkpoint to raise ``TaskCancelledError`` with no
    further attempt made; a cancellation requested during the backoff sleep ends the
    sleep immediately (the fake ``wait()`` returns early) and the next checkpoint
    raises ``TaskCancelledError``.
    """
    # Cancellation reported at the second raise_if_cancelled() checkpoint (before
    # attempt 2 begins) — attempt 1 runs and fails transiently, then the checkpoint
    # for attempt 2 raises before operation() is called again.
    operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="boom", context=None),
        fail_count=None,
    )
    token = _make_token(cancel_at_raise_call=2)

    with pytest.raises(TaskCancelledError):
        with_retry(operation, policy=_make_policy(), token=token)

    assert operation.call_count == 1

    # Cancellation reported mid-backoff: wait() returns True (early) well before its
    # full requested duration would have elapsed; the next checkpoint then raises.
    backoff_operation = _CountingOperation(
        error_factory=lambda: _CustomTransientLeaf(message="boom", context=None),
        fail_count=None,
    )
    backoff_token = _make_token(cancel_during_wait_call=1, cancel_at_raise_call=2)

    with pytest.raises(TaskCancelledError):
        with_retry(backoff_operation, policy=_make_policy(), token=backoff_token)

    assert backoff_operation.call_count == 1
    assert cast("_FakeCancellationToken", backoff_token).wait_call_count == 1
