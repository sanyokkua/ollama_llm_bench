"""Unit tests for AdaptiveTimeoutService.

Tests cover: initial state (min_s), geometric interpolation, retry_count=1
edge case, success promotion, failure counter increment/reset, exclusion
threshold, model key isolation, and reset_for_run.

No external dependencies are injected — the service is pure logic.
"""

from collections.abc import Callable

import pytest

from ollama_llm_bench.backend.services.adaptive_timeout_service import AdaptiveTimeoutService

# ---------------------------------------------------------------------------
# Factory fixture — each test supplies its own configuration
# ---------------------------------------------------------------------------


@pytest.fixture
def make_service() -> Callable[..., AdaptiveTimeoutService]:
    """Return a factory that constructs AdaptiveTimeoutService with given params."""

    def _factory(
        *,
        min_s: int = 100,
        max_s: int = 900,
        retry_count: int = 3,
        max_failures_to_exclude: int = 3,
    ) -> AdaptiveTimeoutService:
        return AdaptiveTimeoutService(
            min_s=min_s,
            max_s=max_s,
            retry_count=retry_count,
            max_failures_to_exclude=max_failures_to_exclude,
        )

    return _factory


# ---------------------------------------------------------------------------
# 1. First attempt returns min_s for unknown key
# ---------------------------------------------------------------------------


def test_first_task_uses_min_s(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=120, max_s=900, retry_count=3)

    # Act
    result = svc.next_timeout("provider1", "model_a", 0)

    # Assert
    assert result == 120


# ---------------------------------------------------------------------------
# 2. record_success promotes current_good_s
# ---------------------------------------------------------------------------


def test_success_promotes_current_good_s(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=100, max_s=600, retry_count=3)

    # Act
    svc.record_success("provider1", "model_a", successful_timeout_s=520)
    result = svc.next_timeout("provider1", "model_a", 0)

    # Assert
    assert result == 520


# ---------------------------------------------------------------------------
# 3. record_success after failure resets consecutive counter → not excluded
# ---------------------------------------------------------------------------


def test_success_resets_consecutive_failures(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=3)
    svc.record_full_failure("provider1", "model_a", final_timeout_s=900)

    # Act — success wipes the consecutive_max_failures counter
    svc.record_success("provider1", "model_a", successful_timeout_s=900)

    # Assert
    assert svc.is_excluded("provider1", "model_a") is False
    assert svc.next_timeout("provider1", "model_a", 0) == 900


# ---------------------------------------------------------------------------
# 4. Geometric interpolation across retry_count attempts
# ---------------------------------------------------------------------------


def test_next_timeout_geometric_interpolation(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange — min=100, max=900, retry_count=3 → attempts: 0, 1, 2
    svc = make_service(min_s=100, max_s=900, retry_count=3)

    # Act
    t0 = svc.next_timeout("p", "m", 0)
    t1 = svc.next_timeout("p", "m", 1)
    t2 = svc.next_timeout("p", "m", 2)

    # Assert
    assert t0 == 100
    assert 100 < t1 < 900
    assert t2 == 900


# ---------------------------------------------------------------------------
# 5. retry_count=1: attempt=0 always returns current_good_s (not max_s)
# ---------------------------------------------------------------------------


def test_next_timeout_single_retry_returns_current_good(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange — with retry_count=1 there is no interpolation window at all
    svc = make_service(min_s=100, max_s=900, retry_count=1)

    # Act
    result = svc.next_timeout("p", "m", 0)

    # Assert — must be current_good_s (min_s), NOT max_s
    assert result == 100


# ---------------------------------------------------------------------------
# 6. Full failure at max_s locks current_good_s to max_s
# ---------------------------------------------------------------------------


def test_full_failure_at_max_locks_current_good_at_max(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange — max_failures_to_exclude=2 so one failure alone does not exclude
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=2)

    # Act
    svc.record_full_failure("p", "m", final_timeout_s=900)
    result = svc.next_timeout("p", "m", 0)

    # Assert — current_good is now max_s
    assert result == 900
    assert svc.is_excluded("p", "m") is False


# ---------------------------------------------------------------------------
# 7. Exclusion triggered after N consecutive max failures
# ---------------------------------------------------------------------------


def test_exclusion_after_consecutive_max_failures(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=3)

    # Act — 3 failures all at max_s
    svc.record_full_failure("p", "m", final_timeout_s=900)
    svc.record_full_failure("p", "m", final_timeout_s=900)
    svc.record_full_failure("p", "m", final_timeout_s=900)

    # Assert
    assert svc.is_excluded("p", "m") is True


# ---------------------------------------------------------------------------
# 8. Exclusion NOT triggered below threshold
# ---------------------------------------------------------------------------


def test_exclusion_not_triggered_below_threshold(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=3)

    # Act — only 2 failures (threshold is 3)
    svc.record_full_failure("p", "m", final_timeout_s=900)
    svc.record_full_failure("p", "m", final_timeout_s=900)

    # Assert
    assert svc.is_excluded("p", "m") is False


# ---------------------------------------------------------------------------
# 9. Success between failures resets counter — not excluded after failure, success, failure, failure
# ---------------------------------------------------------------------------


def test_success_between_failures_resets_counter(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=3)

    # Act — pattern: fail → success → fail → fail
    # Consecutive counter after each step: 1, 0, 1, 2
    svc.record_full_failure("p", "m", final_timeout_s=900)
    svc.record_success("p", "m", successful_timeout_s=900)
    svc.record_full_failure("p", "m", final_timeout_s=900)
    svc.record_full_failure("p", "m", final_timeout_s=900)

    # Assert — counter is 2, not 3 → not excluded
    assert svc.is_excluded("p", "m") is False


# ---------------------------------------------------------------------------
# 10. Model keys are independent — (p1, m1) failure does not affect (p1, m2)
# ---------------------------------------------------------------------------


def test_model_keys_are_independent(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=3)

    # Act — exhaust (p1, m1) failures
    svc.record_full_failure("p1", "m1", final_timeout_s=900)
    svc.record_full_failure("p1", "m1", final_timeout_s=900)
    svc.record_full_failure("p1", "m1", final_timeout_s=900)

    # Assert — (p1, m2) is untouched
    assert svc.is_excluded("p1", "m1") is True
    assert svc.is_excluded("p1", "m2") is False


# ---------------------------------------------------------------------------
# 11. reset_for_run clears all state — model returns to min_s afterwards
# ---------------------------------------------------------------------------


def test_reset_for_run_clears_state(make_service: Callable[..., AdaptiveTimeoutService]) -> None:
    # Arrange — build up some state
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=3)
    svc.record_success("p", "m", successful_timeout_s=700)

    # Act
    svc.reset_for_run()
    result = svc.next_timeout("p", "m", 0)

    # Assert — state wiped, back to min_s
    assert result == 100


# ---------------------------------------------------------------------------
# 12. Non-max failure does NOT increment consecutive_max_failures counter
# ---------------------------------------------------------------------------


def test_full_failure_not_at_max_does_not_increment_consecutive(
    make_service: Callable[..., AdaptiveTimeoutService],
) -> None:
    # Arrange — max_failures_to_exclude=1 so even a single increment would exclude
    svc = make_service(min_s=100, max_s=900, retry_count=3, max_failures_to_exclude=1)

    # Act — failure at 500 (below max_s=900) should NOT count toward exclusion
    svc.record_full_failure("p", "m", final_timeout_s=500)

    # Assert — not excluded because consecutive counter was not incremented
    assert svc.is_excluded("p", "m") is False
