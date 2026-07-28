"""Proves STORY-101-AC-4 — a probe's outcome closes or re-trips the breaker."""

from ollama_llm_bench.backend.circuit_breaker import (
    ProviderCircuitBreaker,
    make_circuit_breaker,
)
from ollama_llm_bench.backend.circuit_breaker.models import CircuitState
from ollama_llm_bench.backend.circuit_breaker.tests.conftest import FakeClock, build_snapshot

_PROVIDER = "openai_cloud"
_FAILURE_THRESHOLD = 5
_COOLDOWN_SECONDS = 60


def _trip_and_advance_to_probing(clock: FakeClock, breaker: ProviderCircuitBreaker) -> None:
    for _ in range(_FAILURE_THRESHOLD):
        breaker.record_failure(_PROVIDER)
    clock.advance_monotonic_ms(_COOLDOWN_SECONDS * 1000)
    breaker.should_skip(_PROVIDER)  # forces the lazy TRIPPED -> PROBING transition


def test_probe_success_closes_and_probe_failure_retrips() -> None:
    """Proves: STORY-101-AC-4

    A record_success while PROBING closes the breaker with a zero counter; a
    record_failure while PROBING (in an independent scenario) re-trips the
    breaker and stamps a fresh cooldown_seconds window, not the elapsed
    remainder of the prior one.
    """
    # --- Success path ---
    clock = FakeClock()
    snapshot = build_snapshot(
        failure_threshold=_FAILURE_THRESHOLD, cooldown_seconds=_COOLDOWN_SECONDS
    )
    breaker = make_circuit_breaker(snapshot=snapshot, clock=clock)
    _trip_and_advance_to_probing(clock, breaker)
    assert breaker.state(_PROVIDER) == CircuitState.PROBING

    breaker.record_success(_PROVIDER)

    assert breaker.state(_PROVIDER) == CircuitState.CLOSED
    assert breaker.should_skip(_PROVIDER) is False

    # --- Failure path (fresh breaker instance) ---
    clock2 = FakeClock()
    breaker2 = make_circuit_breaker(snapshot=snapshot, clock=clock2)
    _trip_and_advance_to_probing(clock2, breaker2)
    assert breaker2.state(_PROVIDER) == CircuitState.PROBING

    breaker2.record_failure(_PROVIDER)

    assert breaker2.state(_PROVIDER) == CircuitState.TRIPPED
    assert breaker2.cooldown_remaining_seconds(_PROVIDER) == _COOLDOWN_SECONDS

    # A fresh window: advancing by less than the full cooldown still leaves it tripped.
    clock2.advance_monotonic_ms((_COOLDOWN_SECONDS - 1) * 1000)
    assert breaker2.state(_PROVIDER) == CircuitState.TRIPPED
