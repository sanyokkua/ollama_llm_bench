"""Integration tests for provider circuit-breaker failover in _stage_benchmarking.

These tests verify that the circuit breaker correctly:
- Trips after threshold failures across 2+ models and skips remaining tasks.
- Allows a second provider to continue when the first trips.
- Resets the circuit state on explicit reset (simulating Resume after restart).
"""

import time

import pytest

from ollama_llm_bench.backend.services.provider_circuit_breaker import (
    HEALTHY,
    TRIPPED,
    ProviderCircuitBreaker,
)

_PROVIDER_A = "ollama_local"
_PROVIDER_B = "openai_remote"
_MODEL_A1 = "llama3:8b"
_MODEL_A2 = "mistral:7b"
_MODEL_B1 = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cb() -> ProviderCircuitBreaker:
    """Circuit breaker with aggressive settings for fast test execution."""
    return ProviderCircuitBreaker(
        failure_threshold=3,
        window_s=60.0,
        probe_interval_s=0.02,
    )


# ---------------------------------------------------------------------------
# 1. Single provider trips and pauses (circuit blocks dispatch)
# ---------------------------------------------------------------------------


def test_single_provider_trips_after_failures(cb: ProviderCircuitBreaker) -> None:
    # Arrange — provider_a has a success, then 3 failures across 2 models
    cb.record_success(_PROVIDER_A)
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A2, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")

    # Assert — circuit tripped, dispatch blocked
    assert cb.state(_PROVIDER_A) == TRIPPED
    assert cb.should_dispatch(_PROVIDER_A) is False


def test_single_provider_remaining_tasks_skipped_via_should_dispatch(cb: ProviderCircuitBreaker) -> None:
    # Arrange — trip the circuit
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="conn")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A2, reason="conn")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="conn")

    # Act — simulate pipeline checking before each task
    skipped = 0
    for _ in range(5):
        if not cb.should_dispatch(_PROVIDER_A):
            skipped += 1

    # Assert — all remaining 5 tasks would be skipped
    assert skipped == 5


# ---------------------------------------------------------------------------
# 2. Two providers — first trips, second continues
# ---------------------------------------------------------------------------


def test_second_provider_unaffected_by_first_trip(cb: ProviderCircuitBreaker) -> None:
    # Arrange — trip provider_a
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A2, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")

    # Assert — provider_b unaffected
    assert cb.state(_PROVIDER_A) == TRIPPED
    assert cb.state(_PROVIDER_B) == HEALTHY
    assert cb.should_dispatch(_PROVIDER_B) is True


def test_second_provider_records_independent_failures(cb: ProviderCircuitBreaker) -> None:
    # Arrange — only 2 failures on provider_b (below threshold)
    cb.record_failure(_PROVIDER_B, model_name=_MODEL_B1, reason="timeout")
    cb.record_failure(_PROVIDER_B, model_name=_MODEL_B1, reason="timeout")

    # Assert — single model, never trips
    assert cb.state(_PROVIDER_B) == HEALTHY


# ---------------------------------------------------------------------------
# 3. Circuit reset on resume clears trip state
# ---------------------------------------------------------------------------


def test_circuit_resets_on_resume(cb: ProviderCircuitBreaker) -> None:
    # Arrange — trip the circuit
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A2, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")
    assert cb.should_dispatch(_PROVIDER_A) is False

    # Act — simulate user clicking Resume after restarting provider
    cb.reset(_PROVIDER_A)

    # Assert — dispatch allowed again
    assert cb.should_dispatch(_PROVIDER_A) is True
    assert cb.state(_PROVIDER_A) == HEALTHY


def test_reset_allows_subsequent_tasks_to_dispatch(cb: ProviderCircuitBreaker) -> None:
    # Arrange — trip then reset
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="conn")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A2, reason="conn")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="conn")
    cb.reset(_PROVIDER_A)

    # Act — record a success (as would happen after reset + new task completes)
    cb.record_success(_PROVIDER_A)

    # Assert
    assert cb.state(_PROVIDER_A) == HEALTHY
    assert cb.should_dispatch(_PROVIDER_A) is True


# ---------------------------------------------------------------------------
# 4. Probe after cooldown allows one attempt
# ---------------------------------------------------------------------------


def test_probe_allows_dispatch_after_cooldown(cb: ProviderCircuitBreaker) -> None:
    # Arrange — trip, then wait for probe window
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A2, reason="timeout")
    cb.record_failure(_PROVIDER_A, model_name=_MODEL_A1, reason="timeout")
    assert cb.should_dispatch(_PROVIDER_A) is False

    time.sleep(0.2)  # probe_interval_s=0.02

    # Assert — should_dispatch returns True while probing
    assert cb.should_dispatch(_PROVIDER_A) is True
