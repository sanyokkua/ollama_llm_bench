"""Proves STORY-022-AC-6 — an EXCLUDED bucket ignores late outcomes, and a
degenerate min > max snapshot never raises and stays clamped."""

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.tests.conftest import build_snapshot
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole

_PROVIDER = "p1"
_MODEL = "model-a"
_ROLE = AdaptiveTimeoutRole.INFERENCE


def test_excluded_bucket_ignores_late_outcomes() -> None:
    """Proves: STORY-022-AC-6

    Once EXCLUDED, further record_success/record_timeout calls leave state,
    last_known_good_ms, and the counter unchanged, and raise nothing.
    """
    fixed_budget_seconds = 300
    snapshot = build_snapshot(
        min_timeout_seconds=fixed_budget_seconds,
        max_timeout_seconds=fixed_budget_seconds,
        retry_count=0,
        consecutive_max_timeouts_to_exclude=1,
    )
    service = make_adaptive_timeout_service(snapshot=snapshot)
    service.next_budget(_PROVIDER, _MODEL, _ROLE, 1)
    service.record_timeout(_PROVIDER, _MODEL, _ROLE)
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is True

    service.record_success(_PROVIDER, _MODEL, _ROLE, 999_000)  # late, ignored
    service.record_timeout(_PROVIDER, _MODEL, _ROLE)  # late, ignored

    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is True
    # LKG unaffected
    assert service.next_budget(_PROVIDER, _MODEL, _ROLE, 1) == fixed_budget_seconds


def test_degenerate_min_greater_than_max_clamps_and_does_not_raise() -> None:
    """Proves: STORY-022-AC-6

    A snapshot with role.min > role.max is a valid, non-fatal configuration
    (§8): every next_budget result is <= role.max, and the service never
    raises.
    """
    degenerate_max_seconds = 300
    attempts_to_probe = 6
    snapshot = build_snapshot(
        min_timeout_seconds=900, max_timeout_seconds=degenerate_max_seconds, retry_count=3
    )
    service = make_adaptive_timeout_service(snapshot=snapshot)

    for attempt_index in range(1, attempts_to_probe):
        budget = service.next_budget(_PROVIDER, _MODEL, _ROLE, attempt_index)
        assert budget <= degenerate_max_seconds
