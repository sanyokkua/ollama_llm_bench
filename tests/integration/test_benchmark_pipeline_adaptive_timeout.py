"""Integration tests for AdaptiveTimeoutService in a pipeline context.

These tests exercise the real service end-to-end (no mocking of the service)
and reflect the scenarios that arise when the benchmark pipeline uses
AdaptiveTimeoutService to manage per-model timeouts across multiple attempts.
"""

import pytest

from ollama_llm_bench.backend.services.adaptive_timeout_service import AdaptiveTimeoutService

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def svc() -> AdaptiveTimeoutService:
    """Default service configured for pipeline-realistic parameters."""
    return AdaptiveTimeoutService(
        min_s=10,
        max_s=30,
        retry_count=3,
        max_failures_to_exclude=3,
    )


# ---------------------------------------------------------------------------
# 1. Timeout is promoted after a success recorded at a higher attempt value
# ---------------------------------------------------------------------------


def test_timeout_promoted_after_success_at_higher_attempt(svc: AdaptiveTimeoutService) -> None:
    # Arrange — success was observed at 20 s (higher than the initial min of 10 s)

    # Act
    svc.record_success("bench_provider", "bench_model", successful_timeout_s=20)
    result = svc.next_timeout("bench_provider", "bench_model", 0)

    # Assert — next run starts from the promoted value, not min_s
    assert result == 20


# ---------------------------------------------------------------------------
# 2. Model is excluded after N consecutive full-max failures
# ---------------------------------------------------------------------------


def test_model_excluded_after_n_consecutive_max_failures(svc: AdaptiveTimeoutService) -> None:
    # Arrange — 3 consecutive failures all at max_s=30

    # Act
    svc.record_full_failure("bench_provider", "bench_model", final_timeout_s=30)
    svc.record_full_failure("bench_provider", "bench_model", final_timeout_s=30)
    svc.record_full_failure("bench_provider", "bench_model", final_timeout_s=30)

    # Assert
    assert svc.is_excluded("bench_provider", "bench_model") is True


# ---------------------------------------------------------------------------
# 3. Other models remain unaffected when one model is excluded
# ---------------------------------------------------------------------------


def test_other_models_unaffected_by_exclusion(svc: AdaptiveTimeoutService) -> None:
    # Arrange — exclude (p1, m1) via 3 full max failures

    # Act
    svc.record_full_failure("p1", "m1", final_timeout_s=30)
    svc.record_full_failure("p1", "m1", final_timeout_s=30)
    svc.record_full_failure("p1", "m1", final_timeout_s=30)

    # Assert — sibling model under same provider is not affected
    assert svc.is_excluded("p1", "m1") is True
    assert svc.is_excluded("p1", "m2") is False


# ---------------------------------------------------------------------------
# 4. Judge timeout carries over via record_success → next_timeout
# ---------------------------------------------------------------------------


def test_judge_timeout_carries_over() -> None:
    # Arrange — separate service to isolate this scenario
    judge_svc = AdaptiveTimeoutService(
        min_s=10,
        max_s=60,
        retry_count=3,
        max_failures_to_exclude=3,
    )

    # Act
    judge_svc.record_success("judge_provider", "judge_model", successful_timeout_s=25)
    result = judge_svc.next_timeout("judge_provider", "judge_model", 0)

    # Assert — previously observed good timeout is reused for the next run
    assert result == 25
