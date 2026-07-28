"""Proves STORY-101-AC-2 and STORY-101-AC-3 — exact-threshold tripping, counter
reset on early success, and the post-cooldown PROBING transition admitting no
benchmark task."""

from ollama_llm_bench.backend.circuit_breaker import CircuitState, make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.tests.conftest import FakeClock, build_snapshot

_PROVIDER = "openai_cloud"
_FAILURE_THRESHOLD = 5
_COOLDOWN_SECONDS = 60


def test_trips_on_exact_threshold_and_success_resets_counter() -> None:
    """Proves: STORY-101-AC-2

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


def test_cooldown_elapse_moves_to_probing_and_admits_no_task() -> None:
    """Proves: STORY-101-AC-3

    Once the cooldown has elapsed, `state` lazily moves to PROBING; every
    `should_skip` query — the first and every later one, with no intervening
    `record_success`/`record_failure` — returns True, admitting no benchmark
    task; `cooldown_remaining_seconds` returns None while PROBING.
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

    assert breaker.should_skip(_PROVIDER) is True
    assert breaker.state(_PROVIDER) == CircuitState.PROBING
    assert breaker.should_skip(_PROVIDER) is True  # still True, no admission window
    assert breaker.cooldown_remaining_seconds(_PROVIDER) is None
