"""Proves STORY-023-AC-2 and STORY-023-AC-3 — exact-threshold tripping, counter
reset on early success, and the lazy one-probe-slot admission rule."""

import pytest

from ollama_llm_bench.backend.circuit_breaker import CircuitState, make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.tests.conftest import FakeClock, build_snapshot

_PROVIDER = "openai_cloud"
_FAILURE_THRESHOLD = 5
_COOLDOWN_SECONDS = 60


def test_trips_on_exact_threshold_and_success_resets_counter() -> None:
    """Proves: STORY-023-AC-2

    A CLOSED provider stays CLOSED for `failure_threshold - 1` consecutive
    failures; a record_success below the threshold resets the counter so no
    trip occurs; `failure_threshold` consecutive failures with no intervening
    success trips the breaker on exactly the threshold-th call.
    """
    clock = FakeClock()
    snapshot = build_snapshot(
        failure_threshold=_FAILURE_THRESHOLD, cooldown_seconds=_COOLDOWN_SECONDS
    )
    breaker = make_circuit_breaker(snapshot=snapshot, clock=clock)

    for _ in range(_FAILURE_THRESHOLD - 1):
        breaker.record_failure(_PROVIDER)
    assert breaker.state(_PROVIDER) == CircuitState.CLOSED
    assert breaker.should_skip(_PROVIDER) is False

    breaker.record_success(_PROVIDER)  # resets the counter below threshold

    for _ in range(_FAILURE_THRESHOLD - 1):
        breaker.record_failure(_PROVIDER)
    assert breaker.state(_PROVIDER) == CircuitState.CLOSED  # still not tripped

    breaker.record_failure(_PROVIDER)  # the threshold-th consecutive failure

    assert breaker.state(_PROVIDER) == CircuitState.TRIPPED
    assert breaker.should_skip(_PROVIDER) is True


@pytest.mark.parametrize(
    ("query_sequence", "expected_results"),
    [
        pytest.param(
            ["should_skip", "state", "should_skip", "cooldown_remaining_seconds"],
            [False, CircuitState.PROBING, True, None],
            id="first-skip-admits-probe-then-second-skip-blocked",
        ),
    ],
)
def test_lazy_probe_slot_admits_exactly_one_task(
    query_sequence: list[str], expected_results: list[object]
) -> None:
    """Proves: STORY-023-AC-3

    Once the cooldown has elapsed, the first `should_skip` query returns
    False (admitting the probe) and flips `state` to PROBING; every
    subsequent `should_skip` query returns True until the probe resolves;
    `cooldown_remaining_seconds` returns None while PROBING.
    """
    clock = FakeClock()
    snapshot = build_snapshot(
        failure_threshold=_FAILURE_THRESHOLD, cooldown_seconds=_COOLDOWN_SECONDS
    )
    breaker = make_circuit_breaker(snapshot=snapshot, clock=clock)

    for _ in range(_FAILURE_THRESHOLD):
        breaker.record_failure(_PROVIDER)
    assert breaker.state(_PROVIDER) == CircuitState.TRIPPED

    clock.advance_monotonic_ms(_COOLDOWN_SECONDS * 1000)  # cooldown just elapsed

    results: list[object] = []
    for query in query_sequence:
        if query == "should_skip":
            results.append(breaker.should_skip(_PROVIDER))
        elif query == "state":
            results.append(breaker.state(_PROVIDER))
        elif query == "cooldown_remaining_seconds":
            results.append(breaker.cooldown_remaining_seconds(_PROVIDER))

    assert results == expected_results
