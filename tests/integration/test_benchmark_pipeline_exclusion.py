"""Integration tests for the pipeline-level model exclusion flow.

Exercises the sequence that BenchmarkExecutionTask follows when a model
repeatedly times out at max_s:

    record_full_failure x N  ->  is_excluded = True
    ->  remaining tasks skipped
    ->  notification emitted exactly once (simulated via counter)

These tests exercise AdaptiveTimeoutService end-to-end and simulate the
guard logic that lives in BenchmarkExecutionTask._excluded_notified.
"""

import pytest

from ollama_llm_bench.backend.services.adaptive_timeout_service import AdaptiveTimeoutService

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def pipeline_svc() -> AdaptiveTimeoutService:
    """Service with pipeline-realistic parameters: 3-retry, excluded after 3 max failures."""
    return AdaptiveTimeoutService(
        min_s=10,
        max_s=30,
        retry_count=3,
        max_failures_to_exclude=3,
    )


# ---------------------------------------------------------------------------
# 1. Not excluded after fewer than threshold failures
# ---------------------------------------------------------------------------


def test_model_not_excluded_before_threshold(pipeline_svc: AdaptiveTimeoutService) -> None:
    provider, model = "bench_provider", "bench_model"

    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)
    assert pipeline_svc.is_excluded(provider, model) is False

    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)
    assert pipeline_svc.is_excluded(provider, model) is False


# ---------------------------------------------------------------------------
# 2. Excluded exactly at threshold; all subsequent tasks see exclusion
# ---------------------------------------------------------------------------


def test_model_excluded_at_threshold_and_remains_excluded(pipeline_svc: AdaptiveTimeoutService) -> None:
    provider, model = "bench_provider", "bench_model"

    for _ in range(3):
        pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)

    # All five remaining "tasks" see exclusion — simulates a 5-task pipeline
    for _ in range(5):
        assert pipeline_svc.is_excluded(provider, model) is True


# ---------------------------------------------------------------------------
# 3. Single-notification guarantee (simulates _excluded_notified set)
# ---------------------------------------------------------------------------


def test_single_notification_emitted_when_tasks_check_excluded() -> None:
    svc = AdaptiveTimeoutService(min_s=10, max_s=30, retry_count=3, max_failures_to_exclude=2)
    provider, model = "p1", "slow_model"

    svc.record_full_failure(provider, model, final_timeout_s=30)
    svc.record_full_failure(provider, model, final_timeout_s=30)

    # Mirrors BenchmarkExecutionTask._excluded_notified guard
    excluded_notified: set[tuple[str, str]] = set()
    notification_count = 0
    skipped_count = 0

    model_key = (provider, model)
    remaining_tasks = 5

    for _ in range(remaining_tasks):
        if svc.is_excluded(*model_key):
            if model_key not in excluded_notified:
                excluded_notified.add(model_key)
                notification_count += 1  # _notify_warn(...) equivalent
            skipped_count += 1
            continue  # _mark_failed + continue equivalent

    assert notification_count == 1
    assert skipped_count == remaining_tasks


# ---------------------------------------------------------------------------
# 4. Sibling model on same provider is unaffected
# ---------------------------------------------------------------------------


def test_sibling_model_unaffected_by_exclusion(pipeline_svc: AdaptiveTimeoutService) -> None:
    provider = "shared_provider"

    for _ in range(3):
        pipeline_svc.record_full_failure(provider, "slow_model", final_timeout_s=30)

    assert pipeline_svc.is_excluded(provider, "slow_model") is True
    assert pipeline_svc.is_excluded(provider, "fast_model") is False

    # fast_model still gets normal timeout progression
    timeout = pipeline_svc.next_timeout(provider, "fast_model", attempt=0)
    assert timeout == 10  # min_s


# ---------------------------------------------------------------------------
# 5. Timeout escalates geometrically across attempts before exclusion
# ---------------------------------------------------------------------------


def test_timeout_escalates_before_exclusion() -> None:
    svc = AdaptiveTimeoutService(min_s=10, max_s=60, retry_count=3, max_failures_to_exclude=3)
    provider, model = "p", "m"

    t0 = svc.next_timeout(provider, model, attempt=0)
    t1 = svc.next_timeout(provider, model, attempt=1)
    t2 = svc.next_timeout(provider, model, attempt=2)

    assert t0 == 10  # starts at min_s
    assert t0 < t1 < t2  # strictly escalating
    assert t2 == 60  # last attempt == max_s


# ---------------------------------------------------------------------------
# 6. Partial failure (below max_s) resets consecutive counter
# ---------------------------------------------------------------------------


def test_non_max_failure_resets_consecutive_counter(pipeline_svc: AdaptiveTimeoutService) -> None:
    provider, model = "bench_provider", "bench_model"

    # Two max failures — below threshold of 3
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)

    # Partial failure (below max_s) resets the consecutive counter
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=15)

    # Now one more max failure — consecutive counter is 1, not 3
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)

    assert pipeline_svc.is_excluded(provider, model) is False


# ---------------------------------------------------------------------------
# 7. Success mid-pipeline resets the consecutive failure counter
# ---------------------------------------------------------------------------


def test_success_mid_pipeline_prevents_exclusion(pipeline_svc: AdaptiveTimeoutService) -> None:
    provider, model = "bench_provider", "bench_model"

    # Two failures then a success
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)
    pipeline_svc.record_success(provider, model, successful_timeout_s=15)

    # Another two failures — counter reset means still below threshold of 3
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)
    pipeline_svc.record_full_failure(provider, model, final_timeout_s=30)

    assert pipeline_svc.is_excluded(provider, model) is False
