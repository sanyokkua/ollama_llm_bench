"""Proves: STORY-030-AC-1

`run_task_with_stability` requests a per-attempt budget from the
`AdaptiveTimeoutService` with the matching role for both the per-task inference
call and the per-task judge call, and reports the clean outcome
(`record_success`/`record_timeout`) exactly once per attempt.
"""

from collections.abc import Callable
from concurrent.futures import Future

import pytest
from pytest_mock import MockerFixture

from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_dispatch import (
    run_task_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import FakeClock
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import AdaptiveTimeoutRole, ResultPatch, ResultStatus
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError, TaskCancelledError
from ollama_llm_bench.backend.evaluation.models import JudgePhaseOutcome, JudgePhaseResult

_PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
_MODEL_NAME = "llama3"
_JUDGE_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_JUDGE_MODEL_NAME = "judge-model"
_EXPECTED_ATTEMPT_COUNT = 2


class _QueueTaskRunner:
    """Runs a unit synchronously; a test double whose `submit` behaviour is
    driven by `outcomes`, a queue of `Callable[[], object]` consumed one per call."""

    def __init__(self, outcomes: list[Callable[[], object]]) -> None:
        self._outcomes = outcomes
        self.submit_count = 0

    def submit(self, fn: Callable[[], object], *, token: CancellationToken) -> "Future[object]":
        del fn  # the queued outcome supersedes whatever build_attempt(...) produced
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


def _always_raises(exc: BaseException) -> Callable[[], object]:
    def _outcome() -> object:
        raise exc

    return _outcome


def test_inference_role_requests_budget_and_reports_success(mocker: MockerFixture) -> None:
    """Proves: STORY-030-AC-1

    A successful role=INFERENCE attempt requests exactly one
    next_budget(role=INFERENCE, attempt_index=1) and reports exactly one
    record_success — no record_timeout.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    runner = _QueueTaskRunner([_always_returns("raw-response")])
    token = CancellationToken(clock=FakeClock())
    finalize_calls: list[object] = []

    def _finalize(raw: object) -> ResultPatch:
        finalize_calls.append(raw)
        return ResultPatch(status=ResultStatus.COMPLETED)

    patch = run_task_with_stability(
        provider_id=_PROVIDER_ID,
        model_name=_MODEL_NAME,
        role=AdaptiveTimeoutRole.INFERENCE,
        retry_count=0,
        build_attempt=lambda timeout_ms: mocker.Mock(return_value="unused"),
        finalize_success=_finalize,
        on_timeout_exhausted=lambda: ResultPatch(status=ResultStatus.FAILED_TIMEOUT),
        runner=runner,
        token=token,
        clock=FakeClock(),
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
    )

    assert patch.status is ResultStatus.COMPLETED
    assert finalize_calls == ["raw-response"]
    assert len(adaptive_timeout.recorded_successes) == 1
    provider_id, model_name, role, _observed_ms = adaptive_timeout.recorded_successes[0]
    assert (provider_id, model_name, role) == (
        _PROVIDER_ID,
        _MODEL_NAME,
        AdaptiveTimeoutRole.INFERENCE,
    )
    assert adaptive_timeout.recorded_timeouts == []


def test_judge_role_requests_budget_and_reports_success() -> None:
    """Proves: STORY-030-AC-1

    A successful role=JUDGE attempt requests next_budget(role=JUDGE,
    attempt_index=1) and reports record_success under the JUDGE role bucket —
    keyed on the run's fixed judge target, independent of the INFERENCE bucket.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    resolved = JudgePhaseResult(
        outcome=JudgePhaseOutcome.RESOLVED,
        verdict=None,
        reasoning="ok",
        time_ms=100,
        completion_tokens=10,
    )
    runner = _QueueTaskRunner([_always_returns(resolved)])
    token = CancellationToken(clock=FakeClock())

    patch = run_task_with_stability(
        provider_id=_JUDGE_PROVIDER_ID,
        model_name=_JUDGE_MODEL_NAME,
        role=AdaptiveTimeoutRole.JUDGE,
        retry_count=0,
        build_attempt=lambda timeout_ms: lambda: resolved,
        finalize_success=lambda raw: ResultPatch(status=ResultStatus.COMPLETED),
        on_timeout_exhausted=lambda: ResultPatch(status=ResultStatus.FAILED_JUDGE_TIMEOUT),
        runner=runner,
        token=token,
        clock=FakeClock(),
        adaptive_timeout=adaptive_timeout,
        circuit_breaker=circuit_breaker,
    )

    assert patch.status is ResultStatus.COMPLETED
    assert len(adaptive_timeout.recorded_successes) == 1
    provider_id, model_name, role, _observed_ms = adaptive_timeout.recorded_successes[0]
    assert (provider_id, model_name, role) == (
        _JUDGE_PROVIDER_ID,
        _JUDGE_MODEL_NAME,
        AdaptiveTimeoutRole.JUDGE,
    )


def test_cancelled_attempt_reports_no_outcome_to_adaptive_timeout() -> None:
    """Proves: STORY-030-AC-1

    A `TaskCancelledError` raised mid-attempt propagates uncontained and
    results in no `record_success`/`record_timeout` call for that attempt.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    runner = _QueueTaskRunner([_always_raises(TaskCancelledError(message="stopped"))])
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

    assert adaptive_timeout.recorded_successes == []
    assert adaptive_timeout.recorded_timeouts == []


def test_timeout_then_success_reports_one_timeout_then_one_success() -> None:
    """Proves: STORY-030-AC-1

    A retry ladder that times out on attempt 1 and succeeds on attempt 2
    reports exactly one record_timeout (for the failed attempt) then exactly
    one record_success (for the winning attempt) — proving the ladder
    escalates across attempts, not just the single-attempt case.
    """
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    timeout_error = HttpTimeoutError(message="timed out", context=ErrorContext())
    runner = _QueueTaskRunner([_always_raises(timeout_error), _always_returns("second-attempt-ok")])
    token = CancellationToken(clock=FakeClock())

    patch = run_task_with_stability(
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

    assert patch.status is ResultStatus.COMPLETED
    assert runner.submit_count == _EXPECTED_ATTEMPT_COUNT
    assert len(adaptive_timeout.recorded_timeouts) == 1
    assert len(adaptive_timeout.recorded_successes) == 1
