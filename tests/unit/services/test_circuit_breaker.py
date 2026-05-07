"""Unit tests for ModelCircuitBreaker state machine.

Tests cover all state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED),
edge cases around threshold/probe clamping, and the no-throw contract.
No mocks are needed — ModelCircuitBreaker is pure logic with no injected deps.
"""

import pytest

from ollama_llm_bench.backend.services.circuit_breaker import ModelCircuitBreaker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make(*, threshold: int = 3, probe: int = 5) -> ModelCircuitBreaker:
    """Construct a breaker with given threshold and probe_interval."""
    return ModelCircuitBreaker(failure_threshold=threshold, probe_interval=probe)


def _open_circuit(cb: ModelCircuitBreaker, threshold: int) -> None:
    """Drive a closed breaker into OPEN state by recording `threshold` failures."""
    for _ in range(threshold):
        cb.record_full_failure()


# ---------------------------------------------------------------------------
# CLOSED state — initial behaviour
# ---------------------------------------------------------------------------


def test_starts_in_closed_state() -> None:
    # Arrange / Act
    cb = _make()

    # Assert
    assert cb.state == "closed"


def test_is_open_false_when_closed() -> None:
    # Arrange / Act
    cb = _make()

    # Assert
    assert cb.is_open is False


def test_returns_full_retry_count_when_closed() -> None:
    # Arrange
    cb = _make()

    # Act
    result = cb.get_effective_retry_count(3)

    # Assert
    assert result == 3


def test_single_failure_below_threshold_stays_closed() -> None:
    # Arrange
    cb = _make(threshold=2)

    # Act
    cb.record_full_failure()

    # Assert
    assert cb.state == "closed"


def test_consecutive_failures_reach_threshold_opens_circuit() -> None:
    # Arrange
    cb = _make(threshold=2)

    # Act
    cb.record_full_failure()
    cb.record_full_failure()

    # Assert
    assert cb.state == "open"


def test_is_open_true_when_open() -> None:
    # Arrange
    cb = _make(threshold=2)

    # Act
    _open_circuit(cb, 2)

    # Assert
    assert cb.is_open is True


def test_success_after_failures_resets_and_stays_closed() -> None:
    # Arrange
    cb = _make(threshold=3)
    cb.record_full_failure()
    cb.record_full_failure()

    # Act
    cb.record_success()

    # Assert
    assert cb.state == "closed"
    assert cb.is_open is False


def test_success_resets_consecutive_failure_counter() -> None:
    # Arrange — two failures, then success, threshold=3 means one more fail should not open
    cb = _make(threshold=3)
    cb.record_full_failure()
    cb.record_full_failure()
    cb.record_success()

    # Act — one failure after reset
    cb.record_full_failure()

    # Assert — still closed (counter was reset to 0 by success)
    assert cb.state == "closed"


def test_multiple_successes_while_closed_stay_closed() -> None:
    # Arrange
    cb = _make()

    # Act
    cb.record_success()
    cb.record_success()
    cb.record_success()

    # Assert
    assert cb.state == "closed"
    assert cb.is_open is False


# ---------------------------------------------------------------------------
# OPEN state
# ---------------------------------------------------------------------------


def test_open_state_returns_single_attempt() -> None:
    # Arrange
    cb = _make(threshold=1, probe=10)
    _open_circuit(cb, 1)

    # Act
    result = cb.get_effective_retry_count(5)

    # Assert
    assert result == 1


def test_open_state_full_failure_counts_tasks_not_state() -> None:
    # Arrange
    cb = _make(threshold=1, probe=10)
    _open_circuit(cb, 1)

    # Act — additional failures while OPEN should NOT change state
    cb.record_full_failure()
    cb.record_full_failure()

    # Assert
    assert cb.state == "open"


def test_open_state_success_closes_circuit() -> None:
    # Arrange
    cb = _make(threshold=1, probe=10)
    _open_circuit(cb, 1)

    # Act
    cb.record_success()

    # Assert
    assert cb.state == "closed"
    assert cb.is_open is False


def test_open_state_probe_triggered_after_probe_interval_failures() -> None:
    # Arrange — probe_interval=3 means after 3 tasks in OPEN the next
    # get_effective_retry_count call should transition to HALF_OPEN.
    cb = _make(threshold=1, probe=3)
    _open_circuit(cb, 1)
    # Record 3 tasks in OPEN state via record_full_failure
    cb.record_full_failure()
    cb.record_full_failure()
    cb.record_full_failure()

    # Act
    result = cb.get_effective_retry_count(4)

    # Assert — probe fires: full count returned, state now half_open
    assert result == 4
    assert cb.state == "half_open"


def test_open_state_probe_returns_full_retry_count() -> None:
    # Arrange
    cb = _make(threshold=1, probe=2)
    _open_circuit(cb, 1)
    cb.record_full_failure()
    cb.record_full_failure()

    # Act
    result = cb.get_effective_retry_count(7)

    # Assert
    assert result == 7


# ---------------------------------------------------------------------------
# HALF_OPEN state
# ---------------------------------------------------------------------------


def test_half_open_state_returns_full_retry_count() -> None:
    # Arrange — drive to HALF_OPEN
    cb = _make(threshold=1, probe=1)
    _open_circuit(cb, 1)
    cb.record_full_failure()  # 1 task in open → probe_interval met
    cb.get_effective_retry_count(3)  # triggers HALF_OPEN transition

    # Act
    result = cb.get_effective_retry_count(5)

    # Assert
    assert cb.state == "half_open"
    assert result == 5


def test_half_open_success_closes_circuit() -> None:
    # Arrange — drive to HALF_OPEN
    cb = _make(threshold=1, probe=1)
    _open_circuit(cb, 1)
    cb.record_full_failure()
    cb.get_effective_retry_count(3)  # → HALF_OPEN

    # Act
    cb.record_success()

    # Assert
    assert cb.state == "closed"
    assert cb.is_open is False


def test_half_open_failure_reopens_circuit_and_resets_task_counter() -> None:
    # Arrange — drive to HALF_OPEN
    cb = _make(threshold=1, probe=1)
    _open_circuit(cb, 1)
    cb.record_full_failure()
    cb.get_effective_retry_count(3)  # → HALF_OPEN

    # Act
    cb.record_full_failure()

    # Assert — back to OPEN, tasks_in_open reset
    assert cb.state == "open"
    # Verify tasks counter reset: next single failure while OPEN should NOT probe
    result = cb.get_effective_retry_count(5)
    assert result == 1


def test_is_open_true_when_half_open() -> None:
    # Arrange — drive to HALF_OPEN
    cb = _make(threshold=1, probe=1)
    _open_circuit(cb, 1)
    cb.record_full_failure()
    cb.get_effective_retry_count(3)  # → HALF_OPEN

    # Assert
    assert cb.state == "half_open"
    assert cb.is_open is True


# ---------------------------------------------------------------------------
# Edge / boundary cases
# ---------------------------------------------------------------------------


def test_custom_failure_threshold_of_1_opens_after_first_failure() -> None:
    # Arrange
    cb = _make(threshold=1, probe=5)

    # Act
    cb.record_full_failure()

    # Assert
    assert cb.state == "open"


def test_custom_probe_interval_of_1_probes_after_one_task() -> None:
    # Arrange
    cb = _make(threshold=1, probe=1)
    _open_circuit(cb, 1)
    cb.record_full_failure()  # 1 task in OPEN → meets probe_interval=1

    # Act
    result = cb.get_effective_retry_count(4)

    # Assert — probe fires immediately
    assert result == 4
    assert cb.state == "half_open"


def test_get_effective_retry_count_clamps_to_minimum_1() -> None:
    # Arrange
    cb = _make()

    # Act
    result = cb.get_effective_retry_count(0)

    # Assert — even base_retry_count=0 returns at least 1
    assert result == 1


def test_threshold_clamped_to_minimum_1() -> None:
    # Arrange — pass a non-positive threshold
    cb = ModelCircuitBreaker(failure_threshold=0, probe_interval=5)

    # Act — one failure should open the circuit (clamped threshold=1)
    cb.record_full_failure()

    # Assert
    assert cb.state == "open"


def test_probe_interval_clamped_to_minimum_1() -> None:
    # Arrange — pass a non-positive probe_interval
    cb = ModelCircuitBreaker(failure_threshold=1, probe_interval=0)
    _open_circuit(cb, 1)
    # With probe_interval clamped to 1, one task in OPEN should trigger probe
    cb.record_full_failure()  # 1 task in OPEN

    # Act
    result = cb.get_effective_retry_count(3)

    # Assert
    assert result == 3
    assert cb.state == "half_open"


# ---------------------------------------------------------------------------
# Parametrized: state property values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state_name", "is_open_expected"),
    [
        ("closed", False),
        ("open", True),
        ("half_open", True),
    ],
    ids=["closed", "open", "half_open"],
)
def test_is_open_property_matches_state(state_name: str, is_open_expected: bool) -> None:
    # Arrange — build a breaker and drive it to the target state
    cb = ModelCircuitBreaker(failure_threshold=1, probe_interval=1)

    if state_name == "closed":
        pass  # default
    elif state_name == "open":
        cb.record_full_failure()
    else:  # half_open
        cb.record_full_failure()  # → OPEN
        cb.record_full_failure()  # 1 task in OPEN (probe_interval=1)
        cb.get_effective_retry_count(3)  # → HALF_OPEN

    # Assert
    assert cb.is_open is is_open_expected
    assert cb.state == state_name


# ---------------------------------------------------------------------------
# Parametrized: get_effective_retry_count when CLOSED or HALF_OPEN
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("base_count", "expected"),
    [
        (1, 1),
        (3, 3),
        (10, 10),
        (0, 1),  # clamped
    ],
    ids=["base_1", "base_3", "base_10", "base_0_clamped"],
)
def test_get_effective_retry_count_when_closed_returns_base_or_clamped(base_count: int, expected: int) -> None:
    # Arrange
    cb = _make()

    # Act
    result = cb.get_effective_retry_count(base_count)

    # Assert
    assert result == expected
