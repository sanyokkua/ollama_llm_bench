"""Proves: STORY-101-AC-6, STORY-101-AC-7, STORY-101-AC-8

A per-task inference that exhausts its retry ladder with `HttpTimeoutError` feeds only
the adaptive-timeout service — it never counts toward the provider circuit breaker
(`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` §6.4, §6.9) — and settles a
contained `FAILED_TIMEOUT` patch so the run advances to the next unit. A row targeting
a `PROBING` provider is skipped by `should_skip` before `run_task_with_stability` ever
submits a network call, reporting nothing to the breaker: liveness for a `PROBING`
provider is decided exclusively by the pipeline's dedicated `run_provider_probe` call
(DD-71, ADR-0013), never by admitting an ordinary task through this dispatch path.
"""

from collections.abc import Callable
from concurrent.futures import Future

from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_dispatch import (
    run_task_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import FakeClock
from ollama_llm_bench.backend.circuit_breaker import CircuitState, make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.testing import FakeProviderCircuitBreaker
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkRunSettingEntry,
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
    """Proves: STORY-101-AC-6

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
    """Proves: STORY-101-AC-7

    Every attempt in the ladder times out; the exhausted timeout returns the terminal
    FAILED_TIMEOUT patch rather than raising — which lets the dispatcher persist it and
    move to the next row — and the adaptive-timeout service is still told about the
    timeout so it can escalate this model's budget (08_CIRCUIT_BREAKER.md §6.9).
    """
    # Arrange
    adaptive_timeout = FakeAdaptiveTimeoutService()
    circuit_breaker = FakeProviderCircuitBreaker()
    circuit_breaker.set_should_skip(_PROVIDER_ID, should_skip=False)
    timeout_error = HttpTimeoutError(message="timed out", context=ErrorContext())
    runner = _QueueTaskRunner([_always_raises(timeout_error), _always_raises(timeout_error)])
    token = CancellationToken(clock=FakeClock())

    # Act
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

    # Assert
    assert patch.status is ResultStatus.FAILED_TIMEOUT
    assert adaptive_timeout.recorded_timeouts == [
        (_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.INFERENCE),
        (_PROVIDER_ID, _MODEL_NAME, AdaptiveTimeoutRole.INFERENCE),
    ]
    assert adaptive_timeout.recorded_successes == []
    assert circuit_breaker.recorded_failures == []
    assert circuit_breaker.recorded_successes == []
    assert runner.submit_count == _EXPECTED_ATTEMPT_COUNT


def test_probing_provider_task_is_skipped_and_reports_nothing() -> None:
    """Proves: STORY-101-AC-8

    Drives the real `ProviderCircuitBreaker` state machine, not a fake: trip it to
    TRIPPED, elapse its cooldown so the next query lazily moves it to PROBING. A row
    targeting that provider must be skipped by `should_skip` before
    `run_task_with_stability` ever submits a network call — no attempt is made (the
    runner's outcome queue is empty; a submit call would raise `IndexError`), the
    breaker stays PROBING exactly as it was (no `record_success`/`record_failure`
    is ever reached from this dispatch path), and the row settles as an ordinary
    tripped/probing skip (`FAILED_PROVIDER`).
    """
    # Arrange
    adaptive_timeout = FakeAdaptiveTimeoutService()
    breaker_clock = FakeClock()
    cooldown_seconds = 30
    snapshot = (
        BenchmarkRunSettingEntry(setting_key="circuit_breaker.enabled", setting_value="true"),
        BenchmarkRunSettingEntry(
            setting_key="circuit_breaker.failure_threshold", setting_value="1"
        ),
        BenchmarkRunSettingEntry(
            setting_key="circuit_breaker.cooldown_seconds", setting_value=str(cooldown_seconds)
        ),
    )
    circuit_breaker = make_circuit_breaker(snapshot=snapshot, clock=breaker_clock)
    circuit_breaker.record_failure(_PROVIDER_ID)  # threshold=1: trips immediately
    breaker_clock.advance_monotonic_ms(cooldown_seconds * 1000)  # cooldown elapses
    assert circuit_breaker.state(_PROVIDER_ID) is CircuitState.PROBING
    runner = _QueueTaskRunner([])  # any submit call is a bug: raises IndexError
    token = CancellationToken(clock=FakeClock())

    # Act
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

    # Assert
    assert patch.status is ResultStatus.FAILED_PROVIDER
    assert circuit_breaker.state(_PROVIDER_ID) is CircuitState.PROBING
    assert circuit_breaker.should_skip(_PROVIDER_ID) is True
    assert runner.submit_count == 0
