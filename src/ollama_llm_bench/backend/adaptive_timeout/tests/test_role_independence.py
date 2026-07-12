"""Proves STORY-022-AC-5 — INFERENCE, JUDGE, and RUN_ANALYSIS buckets evolve
independently for the same (provider, model)."""

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.tests.conftest import build_snapshot
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole

_PROVIDER = "p1"
_MODEL = "shared-model"
_JUDGE_EXCLUSION_TIMEOUTS = 3
_RUN_ANALYSIS_START_SECONDS = 20


def test_judge_exclusion_leaves_inference_bucket_usable() -> None:
    """Proves: STORY-022-AC-5

    A (provider, model) excluded at role=JUDGE stays usable at role=INFERENCE;
    each role's last_known_good_ms and counter evolve independently.
    """
    snapshot = build_snapshot(
        min_timeout_seconds=300,
        max_timeout_seconds=300,
        retry_count=0,
        consecutive_max_timeouts_to_exclude=3,
        judge_min_seconds=20,
        judge_max_seconds=20,
        judge_escalation_steps=0,
        judge_consecutive_threshold=3,
    )
    service = make_adaptive_timeout_service(snapshot=snapshot)

    for _ in range(_JUDGE_EXCLUSION_TIMEOUTS):
        service.next_budget(_PROVIDER, _MODEL, AdaptiveTimeoutRole.JUDGE, 1)
        service.record_timeout(_PROVIDER, _MODEL, AdaptiveTimeoutRole.JUDGE)

    assert service.is_excluded(_PROVIDER, _MODEL, AdaptiveTimeoutRole.JUDGE) is True
    assert service.is_excluded(_PROVIDER, _MODEL, AdaptiveTimeoutRole.INFERENCE) is False

    service.record_success(_PROVIDER, _MODEL, AdaptiveTimeoutRole.INFERENCE, 300_000)
    assert service.is_excluded(_PROVIDER, _MODEL, AdaptiveTimeoutRole.INFERENCE) is False


def test_judge_and_run_analysis_buckets_are_independent_but_share_parameters() -> None:
    """Proves: STORY-022-AC-5 (bucket independence extends to the third role, §1.3, DD-65)

    role=JUDGE and role=RUN_ANALYSIS share the same eval.judge_timeout_*
    parameter values but never share TimeoutState: excluding one never
    excludes the other, and RUN_ANALYSIS starts its own ladder from its own
    minimum even after JUDGE has been driven to exclusion.
    """
    snapshot = build_snapshot(
        judge_min_seconds=_RUN_ANALYSIS_START_SECONDS,
        judge_max_seconds=_RUN_ANALYSIS_START_SECONDS,
        judge_escalation_steps=0,
        judge_consecutive_threshold=2,
    )
    service = make_adaptive_timeout_service(snapshot=snapshot)

    judge_exclusion_timeouts = 2
    for _ in range(judge_exclusion_timeouts):
        service.next_budget(_PROVIDER, _MODEL, AdaptiveTimeoutRole.JUDGE, 1)
        service.record_timeout(_PROVIDER, _MODEL, AdaptiveTimeoutRole.JUDGE)

    assert service.is_excluded(_PROVIDER, _MODEL, AdaptiveTimeoutRole.JUDGE) is True
    assert service.is_excluded(_PROVIDER, _MODEL, AdaptiveTimeoutRole.RUN_ANALYSIS) is False
    assert (
        service.next_budget(_PROVIDER, _MODEL, AdaptiveTimeoutRole.RUN_ANALYSIS, 1)
        == _RUN_ANALYSIS_START_SECONDS
    )
