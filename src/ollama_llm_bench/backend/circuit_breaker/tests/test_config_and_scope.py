"""Proves STORY-101-AC-5 — a disabled breaker is inert, and per-provider records
are independent."""

from ollama_llm_bench.backend.circuit_breaker import CircuitState, make_circuit_breaker
from ollama_llm_bench.backend.circuit_breaker.tests.conftest import FakeClock, build_snapshot

_PROVIDER_A = "provider_a"
_PROVIDER_B = "provider_b"
_FAILURE_THRESHOLD = 5
_COOLDOWN_SECONDS = 60


def test_disabled_breaker_is_inert_and_providers_are_independent() -> None:
    """Proves: STORY-101-AC-5

    With circuit_breaker.enabled=false, state stays CLOSED and should_skip
    stays False even after failure_threshold-or-more record_failure calls; a
    separate enabled breaker shows two providers are independent — tripping
    one leaves the other CLOSED.
    """
    # --- Disabled breaker is inert ---
    clock = FakeClock()
    disabled_snapshot = build_snapshot(
        enabled=False, failure_threshold=_FAILURE_THRESHOLD, cooldown_seconds=_COOLDOWN_SECONDS
    )
    disabled_breaker = make_circuit_breaker(snapshot=disabled_snapshot, clock=clock)

    for _ in range(_FAILURE_THRESHOLD + 2):
        disabled_breaker.record_failure(_PROVIDER_A)

    assert disabled_breaker.state(_PROVIDER_A) == CircuitState.CLOSED
    assert disabled_breaker.should_skip(_PROVIDER_A) is False
    assert disabled_breaker.cooldown_remaining_seconds(_PROVIDER_A) is None

    # --- Independent per-provider scope ---
    enabled_snapshot = build_snapshot(
        failure_threshold=_FAILURE_THRESHOLD, cooldown_seconds=_COOLDOWN_SECONDS
    )
    enabled_breaker = make_circuit_breaker(snapshot=enabled_snapshot, clock=clock)

    for _ in range(_FAILURE_THRESHOLD):
        enabled_breaker.record_failure(_PROVIDER_A)
    enabled_breaker.record_success(_PROVIDER_B)

    assert enabled_breaker.state(_PROVIDER_A) == CircuitState.TRIPPED
    assert enabled_breaker.state(_PROVIDER_B) == CircuitState.CLOSED
    assert enabled_breaker.should_skip(_PROVIDER_B) is False
