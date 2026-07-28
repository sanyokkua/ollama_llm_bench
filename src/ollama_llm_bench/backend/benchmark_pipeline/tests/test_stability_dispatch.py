"""Proves: STORY-082-AC-1, STORY-082-AC-2

A per-task inference that exhausts its retry ladder with `HttpTimeoutError` feeds only
the adaptive-timeout service — it never counts toward the provider circuit breaker
(`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` §6.4, §6.9) — and settles a
contained `FAILED_TIMEOUT` patch so the run advances to the next unit.
"""

from collections.abc import Callable
from concurrent.futures import Future

from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_dispatch import (
    run_task_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import FakeClock
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    ResultPatch,
    ResultStatus,
)
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_EXPECTED_ATTEMPT_COUNT = 2


class _QueueTaskRunner:
    """Runs a unit synchronously; `outcomes` is consumed one entry per `submit` call."""

    def __init__(self, outcomes: list[Callable[[], object]]) -> None:
        self._outcomes = outcomes
        self.submit_count = 0

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        del fn
        del token
        self.submit_count += 1
        outcome = self._outcomes.pop(0)
        future: Future[object] = Future()
        try:
            future.set_result(outcome())
        except BaseException as exc:  # noqa: BLE001  # captured for the Future, not swallowed
            future.set_exception(exc)
        return future


def _always_raises(error: BaseException) -> Callable[[], object]:
    def _outcome() -> object:
        raise error

    return _outcome


def test_exhausted_per_task_timeout_does_not_record_breaker_failure() -> None:
    """Proves: STORY-082-AC-1

    Every attempt in the ladder times out; the breaker's consecutive-failure count for
    the provider is unchanged, because a per-task `FAILED_TIMEOUT` is a model-level
    signal, not a provider-attributable one (08_CIRCUIT_BREAKER.md §6.4).
    """
    # Arrange
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_should_skip(_PROVIDER_ID, should_skip=False)
    timeout_error = HttpTimeoutError(message="timed out", context=ErrorContext())
    runner = _QueueTaskRunner([_always_raises(timeout_error), _always_raises(timeout_error)])
    token = CancellationToken(clock=FakeClock())

    # Act
    run_task_with_stability(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        role=AdaptiveTimeoutRole.INFERENCE,
        retry_count=1,
        build_attempt=lambda timeout_ms: lambda: "unused",
        finalize_success=lambda raw: ResultPatch(status=ResultStatus.COMPLETED),
        on_timeout_exhausted=lambda: ResultPatch(status=ResultStatus.FAILED_TIMEOUT),
        runner=runner,
        token=token,
        clock=FakeClock(),
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
    )

    # Assert
    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []
    assert runner.submit_count == _EXPECTED_ATTEMPT_COUNT


def test_exhausted_per_task_timeout_settles_failed_timeout_and_advances() -> None:
    """Proves: STORY-082-AC-2

    Removing the breaker call leaves containment intact: the exhausted timeout returns
    the terminal FAILED_TIMEOUT patch rather than raising — which is what lets the
    dispatcher persist it and move to the next row — and the adaptive-timeout service
    is still told about the timeout so it can escalate this model's budget
    (08_CIRCUIT_BREAKER.md §6.9).
    """
    # Arrange
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_should_skip(_PROVIDER_ID, should_skip=False)
    timeout_error = HttpTimeoutError(message="timed out", context=ErrorContext())
    runner = _QueueTaskRunner([_always_raises(timeout_error)])
    token = CancellationToken(clock=FakeClock())

    # Act
    patch = run_task_with_stability(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        role=AdaptiveTimeoutRole.INFERENCE,
        retry_count=0,
        build_attempt=lambda timeout_ms: lambda: "unused",
        finalize_success=lambda raw: ResultPatch(status=ResultStatus.COMPLETED),
        on_timeout_exhausted=lambda: ResultPatch(status=ResultStatus.FAILED_TIMEOUT),
        runner=runner,
        token=token,
        clock=FakeClock(),
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
    )

    # Assert
    assert patch.status is ResultStatus.FAILED_TIMEOUT
    assert adaptive_timeout.recorded_timeouts == [
        (_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.INFERENCE)
    ]
    assert adaptive_timeout.recorded_successes == []
    assert circuit_breaker.recorded_failures == []
