"""Proves STORY-022-AC-3 and STORY-022-AC-4 — the outcome/counter/LKG table and the
exact exclusion boundary."""

from ollama_llm_bench.backend.adaptive_timeout import (
    AdaptiveTimeoutService,
    make_adaptive_timeout_service,
)
from ollama_llm_bench.backend.adaptive_timeout.tests.conftest import build_snapshot
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole

_PROVIDER = "p1"
_MODEL = "model-a"
_ROLE = AdaptiveTimeoutRole.INFERENCE
_MIN_EQ_MAX_SECONDS = 300


def _service(
    *, min_s: int = 300, max_s: int = 900, steps: int = 0, threshold: int = 3
) -> AdaptiveTimeoutService:
    snapshot = build_snapshot(
        min_timeout_seconds=min_s,
        max_timeout_seconds=max_s,
        retry_count=steps,
        consecutive_max_timeouts_to_exclude=threshold,
    )
    return make_adaptive_timeout_service(snapshot=snapshot)


def _min_eq_max_service(*, threshold: int = 3) -> AdaptiveTimeoutService:
    # min == max, steps == 0: every attempt at every index returns exactly that
    # value, so every timeout is trivially "at max" — isolates counter/LKG
    # logic from ladder-position bookkeeping. Valid per §4 precondition.
    return _service(
        min_s=_MIN_EQ_MAX_SECONDS, max_s=_MIN_EQ_MAX_SECONDS, steps=0, threshold=threshold
    )


def _record_max_timeout(service: AdaptiveTimeoutService) -> None:
    service.next_budget(_PROVIDER, _MODEL, _ROLE, 1)
    service.record_timeout(_PROVIDER, _MODEL, _ROLE)


def test_success_resets_counter_and_raises_lkg() -> None:
    """Proves: STORY-022-AC-3

    A SUCCESS resets the consecutive-max counter to 0 and raises
    last_known_good_ms to max(LKG, observed_ms); a SUCCESS never lowers it.
    """
    service = _min_eq_max_service()
    _record_max_timeout(service)
    _record_max_timeout(service)  # counter == 2

    service.record_success(_PROVIDER, _MODEL, _ROLE, 250_000)  # below current LKG (300_000)

    # LKG NOT lowered to 250
    assert service.next_budget(_PROVIDER, _MODEL, _ROLE, 1) == _MIN_EQ_MAX_SECONDS
    _record_max_timeout(service)
    _record_max_timeout(service)
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is False  # only 2 since the reset
    _record_max_timeout(service)
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is True  # 3rd since the reset


def test_success_promotes_lkg_above_the_minimum() -> None:
    """Proves: STORY-022-AC-3

    A SUCCESS observed above the current last_known_good_ms raises it.
    """
    promoted_seconds = 600
    service = _service(min_s=300, max_s=900, steps=0)
    service.record_success(_PROVIDER, _MODEL, _ROLE, promoted_seconds * 1000)
    assert service.next_budget(_PROVIDER, _MODEL, _ROLE, 1) == promoted_seconds


def test_timeout_below_max_does_not_touch_counter() -> None:
    """Proves: STORY-022-AC-3

    A TIMEOUT below the role's maximum escalates state but leaves the
    consecutive-max counter untouched — five sub-max timeouts in a row never
    approach a threshold of 1.
    """
    attempts_below_max = 5
    service = _service(min_s=300, max_s=900, steps=3, threshold=1)
    for _ in range(attempts_below_max):
        service.next_budget(_PROVIDER, _MODEL, _ROLE, 1)  # attempt 1 == floor == 300s < 900s max
        service.record_timeout(_PROVIDER, _MODEL, _ROLE)
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is False


def test_error_outcome_is_never_reported_so_state_is_unchanged() -> None:
    """Proves: STORY-022-AC-3

    The Protocol exposes no error-reporting method (08-E §17) — an
    AttemptOutcome.ERROR never reaches this service (§6.6): the caller simply
    does not call record_success or record_timeout for an errored attempt, so
    the counter and last_known_good_ms are exactly as if that attempt never
    happened.
    """
    service = _min_eq_max_service()
    _record_max_timeout(service)
    _record_max_timeout(service)  # counter == 2
    # An ERROR attempt happens here in a real caller — no service call is made.
    _record_max_timeout(service)  # this is the 3rd genuine timeout, not a 4th
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is True


def test_exclusion_after_exactly_threshold_consecutive_max_timeouts() -> None:
    """Proves: STORY-022-AC-4

    is_excluded flips to True on exactly the Nth consecutive max-budget
    timeout and not before.
    """
    timeouts_before_threshold = 2
    service = _min_eq_max_service(threshold=3)
    for _ in range(timeouts_before_threshold):
        _record_max_timeout(service)
        assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is False
    _record_max_timeout(service)
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is True


def test_success_before_threshold_prevents_exclusion() -> None:
    """Proves: STORY-022-AC-4

    A SUCCESS before the threshold resets the counter so exclusion does not
    occur even after as many total timeouts as the threshold.
    """
    service = _min_eq_max_service(threshold=3)
    _record_max_timeout(service)
    _record_max_timeout(service)
    service.record_success(_PROVIDER, _MODEL, _ROLE, _MIN_EQ_MAX_SECONDS * 1000)
    _record_max_timeout(service)
    assert service.is_excluded(_PROVIDER, _MODEL, _ROLE) is False  # only 1 since the reset
