"""Proves: STORY-102-AC-1

Pins, across all three `ProviderCircuitBreaker` states, the rule STORY-101 finished
implementing: a per-task inference that exhausts its retry ladder with
`HttpTimeoutError` never records a breaker failure from the ordinary per-task
dispatch path (`_internal.stability_dispatch.run_task_with_stability`). A timeout is
a model-level signal owned by the adaptive-timeout service, never a
provider-attributable one owned by the breaker
(`11_Services_and_Algorithms/08_CIRCUIT_BREAKER.md` §6.4, §6.9) — otherwise one slow
model would trip a provider that is perfectly healthy and still serving the judge
model or other test models.

Drives the real `make_circuit_breaker` state machine in every case, never a fake's
call log: `CLOSED` proves the dispatch path's own `except HttpTimeoutError` branch
never calls `record_failure` (the branch this story's title is about); `TRIPPED` and
`PROBING` prove the earlier `should_skip` guard keeps the dispatch path from ever
reaching that branch at all in a non-CLOSED state, so "zero breaker failures" holds
there for a different, structural reason rather than because the branch itself is
correct. See this module's own test docstring for which case is load-bearing against
which regression class.
"""

from collections.abc import Callable
from typing import NamedTuple

import pytest

from ollama_llm_bench.backend.adaptive_timeout.testing import FakeAdaptiveTimeoutService
from ollama_llm_bench.backend.benchmark_pipeline._internal.stability_dispatch import (
    run_task_with_stability,
)
from ollama_llm_bench.backend.benchmark_pipeline.tests.conftest import (
    FakeClock,
    QueueTaskRunner,
    always_raises,
)
from ollama_llm_bench.backend.circuit_breaker import (
    CircuitState,
    ProviderCircuitBreaker,
    make_circuit_breaker,
)
from ollama_llm_bench.backend.concurrency import CancellationToken
from ollama_llm_bench.backend.domain.models import (
    AdaptiveTimeoutRole,
    BenchmarkRunSettingEntry,
    ResultPatch,
    ResultStatus,
)
from ollama_llm_bench.backend.errors import ErrorContext, HttpTimeoutError

_PROVIDER_ID = "22222222-2222-4222-8222-222222222222"
_MODEL_NAME = "llama3"
_COOLDOWN_SECONDS = 30
_EXPECTED_LADDER_ATTEMPTS = 2  # retry_count=1 -> 2 attempts (matches test_stability_dispatch.py)


def _snapshot() -> tuple[BenchmarkRunSettingEntry, ...]:
    """The breaker's three required run-frozen keys, `failure_threshold=1`.

    A threshold of one makes any single leaked `record_failure` call immediately
    observable: the CLOSED case's real breaker would flip straight to TRIPPED on the
    very first (and only, in this story's scenario) exhausted-timeout task if the
    production code under test ever called `record_failure` from that path.
    """
    return (
        BenchmarkRunSettingEntry(setting_key="circuit_breaker.enabled", setting_value="true"),
        BenchmarkRunSettingEntry(
            setting_key="circuit_breaker.failure_threshold", setting_value="1"
        ),
        BenchmarkRunSettingEntry(
            setting_key="circuit_breaker.cooldown_seconds", setting_value=str(_COOLDOWN_SECONDS)
        ),
    )


def _make_closed_breaker() -> ProviderCircuitBreaker:
    """A fresh breaker: no prior failure, so the provider starts CLOSED."""
    return make_circuit_breaker(snapshot=_snapshot(), clock=FakeClock())


def _make_tripped_breaker() -> ProviderCircuitBreaker:
    """A breaker mid-cooldown: one real failure has already tripped it and the
    cooldown has not elapsed, so `should_skip` short-circuits every row."""
    clock = FakeClock()
    breaker = make_circuit_breaker(snapshot=_snapshot(), clock=clock)
    breaker.record_failure(_PROVIDER_ID)
    return breaker


def _make_probing_breaker() -> ProviderCircuitBreaker:
    """A breaker whose cooldown has fully elapsed by the time it is first queried,
    so the lazy TRIPPED -> PROBING transition has already happened (STORY-101:
    `PROBING` still admits no benchmark task; `should_skip` stays `True`)."""
    clock = FakeClock()
    breaker = make_circuit_breaker(snapshot=_snapshot(), clock=clock)
    breaker.record_failure(_PROVIDER_ID)
    clock.advance_monotonic_ms(_COOLDOWN_SECONDS * 1000)
    return breaker


def _closed_outcomes() -> list[Callable[[], object]]:
    """Every attempt in the retry ladder times out — the one case in this table
    where the dispatch path actually reaches the `except HttpTimeoutError` branch
    under test."""
    return [
        always_raises(HttpTimeoutError(message="timed out", context=ErrorContext())),
        always_raises(HttpTimeoutError(message="timed out", context=ErrorContext())),
    ]


def _no_dispatch_outcomes() -> list[Callable[[], object]]:
    """An empty outcome queue: `should_skip` must short-circuit the row before any
    attempt is submitted here — a `submit` call against an empty queue is a bug and
    raises `IndexError`, which fails the test loudly rather than silently."""
    return []


class _Expected(NamedTuple):
    """The one case's expected observable outcome, bundled to keep the test
    function's own parameter count within the project's argument-count limit."""

    status: ResultStatus
    submit_count: int
    state_after: CircuitState
    should_skip_after: bool


@pytest.mark.parametrize(
    ("make_breaker", "make_outcomes", "expected"),
    [
        pytest.param(
            _make_closed_breaker,
            _closed_outcomes,
            _Expected(
                status=ResultStatus.FAILED_TIMEOUT,
                submit_count=_EXPECTED_LADDER_ATTEMPTS,
                state_after=CircuitState.CLOSED,
                should_skip_after=False,
            ),
            id="CLOSED-real-retry-ladder-exhausts-on-timeout",
        ),
        pytest.param(
            _make_tripped_breaker,
            _no_dispatch_outcomes,
            _Expected(
                status=ResultStatus.FAILED_PROVIDER,
                submit_count=0,
                state_after=CircuitState.TRIPPED,
                should_skip_after=True,
            ),
            id="TRIPPED-short-circuited-before-any-dispatch",
        ),
        pytest.param(
            _make_probing_breaker,
            _no_dispatch_outcomes,
            _Expected(
                status=ResultStatus.FAILED_PROVIDER,
                submit_count=0,
                state_after=CircuitState.PROBING,
                should_skip_after=True,
            ),
            id="PROBING-short-circuited-before-any-dispatch",
        ),
    ],
)
def test_exhausted_timeout_records_zero_breaker_failures_in_every_state(
    make_breaker: Callable[[], ProviderCircuitBreaker],
    make_outcomes: Callable[[], list[Callable[[], object]]],
    expected: _Expected,
) -> None:
    """Proves: STORY-102-AC-1

    Builds the real breaker fresh in the state under test, then runs one per-task
    inference through `run_task_with_stability` whose every attempt raises
    `HttpTimeoutError`. In `CLOSED` the ladder actually runs and exhausts, exercising
    the dispatch path's own `except HttpTimeoutError` branch. In `TRIPPED` and
    `PROBING` the row is skipped before any attempt is submitted at all (per
    STORY-101, `should_skip` returns `True` unconditionally in both non-CLOSED
    states), so the branch under test is never reached for those two cases — a
    structurally different, and by construction narrower, guarantee than the
    `CLOSED` case's. In every state the breaker's observable state and `should_skip`
    verdict are exactly what they were before the call: no failure was recorded.
    """
    # Arrange
    circuit_breaker = make_breaker()
    runner = QueueTaskRunner(make_outcomes())
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
        adaptive_timeout=FakeAdaptiveTimeoutService(),
        circuit_breaker=circuit_breaker,
    )

    # Assert
    assert patch.status is expected.status
    assert runner.submit_count == expected.submit_count
    assert circuit_breaker.state(_PROVIDER_ID) is expected.state_after
    assert circuit_breaker.should_skip(_PROVIDER_ID) is expected.should_skip_after
