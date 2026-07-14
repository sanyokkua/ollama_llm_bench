"""Proves: STORY-035-AC-5"""

from ollama_llm_bench.backend.run_analysis._internal.timeout_cache import RunAdaptiveTimeoutCache
from ollama_llm_bench.backend.run_analysis.tests.conftest import build_run_analysis_snapshot


def test_same_run_id_reuses_the_same_service_instance() -> None:
    """Proves: RA-25 (cross-call last-known-good persistence)

    Two lookups for the same run_id return the identical AdaptiveTimeoutService
    object, so a promoted last-known-good survives from one generate() call to
    the next; a different run_id gets an independent instance.
    """
    cache = RunAdaptiveTimeoutCache()
    snapshot = build_run_analysis_snapshot()
    first = cache.get_or_create(run_id=1, snapshot=snapshot)
    second = cache.get_or_create(run_id=1, snapshot=snapshot)
    other_run = cache.get_or_create(run_id=2, snapshot=snapshot)
    assert first is second
    assert first is not other_run
