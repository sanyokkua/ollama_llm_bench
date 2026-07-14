"""Proves: STORY-030-AC-2

`run_task_with_stability` consults the `ProviderCircuitBreaker` before submitting a
unit: a tripped provider settles `FAILED_PROVIDER` with no network call; a clean
outcome is reported to the breaker exactly once; a cancelled unit reports nothing.
"""

from collections.abc import Callable
from concurrent.futures import Future

import pytest

from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_dispatch import (
    run_task_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import FakeClock
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    ErrorKind,
    ResultPatch,
    ResultStatus,
)
from ollama_llm_bench.backend.errors import TaskCancelledError

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"


class _QueueTaskRunner:
    """Runs a unit synchronously; a test double whose `submit` behaviour is
    driven by `outcomes`, a queue of `Callable[[], object]` consumed one per call.
    Also tracks how many times `submit` was ever called, to prove a tripped
    breaker skips the network call entirely."""

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


def _always_returns(value: object) -> Callable[[], object]:
    def _outcome() -> object:
        return value

    return _outcome


def test_tripped_provider_settles_failed_provider_with_no_network_call() -> None:
    """Proves: STORY-030-AC-2

    Given `ProviderCircuitBreaker.should_skip` returns True, the unit settles
    `FAILED_PROVIDER` and the `TaskRunner`'s `submit` is never called.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_should_skip(_PROVIDER_ID, should_skip=True)
    runner = _QueueTaskRunner([_always_returns("unused")])
    token = CancellationToken(clock=FakeClock())

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

    assert patch.status is ResultStatus.FAILED_PROVIDER
    assert patch.error_kind is ErrorKind.PROVIDER
    assert runner.submit_count == 0
    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []


def test_untripped_provider_calls_normally_and_records_one_success() -> None:
    """Proves: STORY-030-AC-2

    Once `should_skip` is False, the unit calls the client normally and
    reports exactly one `record_success` on completion.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_should_skip(_PROVIDER_ID, should_skip=False)
    runner = _QueueTaskRunner([_always_returns("raw-response")])
    token = CancellationToken(clock=FakeClock())

    patch = run_task_with_stability(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        role=AdaptiveTimeoutRole.INFERENCE,
        retry_count=0,
        build_attempt=lambda timeout_ms: lambda: "raw-response",
        finalize_success=lambda raw: ResultPatch(status=ResultStatus.COMPLETED),
        on_timeout_exhausted=lambda: ResultPatch(status=ResultStatus.FAILED_TIMEOUT),
        runner=runner,
        token=token,
        clock=FakeClock(),
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
    )

    assert patch.status is ResultStatus.COMPLETED
    assert runner.submit_count == 1
    assert circuit_breaker.recorded_successes == [_PROVIDER_ID]
    assert circuit_breaker.recorded_failures == []


def test_cancelled_unit_reports_no_outcome_to_circuit_breaker() -> None:
    """Proves: STORY-030-AC-2

    A `TaskCancelledError` raised mid-attempt propagates uncontained and
    reports neither `record_failure` nor `record_success` to the breaker.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()

    def _raise_cancelled() -> object:
        raise TaskCancelledError(message="stopped")

    runner = _QueueTaskRunner([_raise_cancelled])
    token = CancellationToken(clock=FakeClock())

    with pytest.raises(TaskCancelledError):
        run_task_with_stability(
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

    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []
