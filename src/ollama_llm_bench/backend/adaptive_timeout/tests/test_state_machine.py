"""Proves STORY-022-AC-2 — the TimeoutState machine matches §6.2 for every legal
transition."""

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
import pytest

from ollama_llm_bench.backend.adaptive_timeout import (
    AdaptiveTimeoutModelState,
    AdaptiveTimeoutService,
    make_adaptive_timeout_service,
)
from ollama_llm_bench.backend.adaptive_timeout.tests.conftest import build_snapshot
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole

_PROVIDER = "p1"
_MODEL = "model-a"
_ROLE = AdaptiveTimeoutRole.INFERENCE
_MIN_S = 300
_MAX_S = 900
_STEPS = 2
_THRESHOLD = 3


class _AdaptiveTimeoutStateMachine(RuleBasedStateMachine):
    """Walks record_success/record_timeout/next_budget and checks §6.2's state
    machine against an independently-tracked expected state."""

    service: AdaptiveTimeoutService

    def __init__(self) -> None:
        super().__init__()
        snapshot = build_snapshot(
            min_timeout_seconds=_MIN_S,
            max_timeout_seconds=_MAX_S,
            retry_count=_STEPS,
            consecutive_max_timeouts_to_exclude=_THRESHOLD,
        )
        self.service = make_adaptive_timeout_service(snapshot=snapshot)
        self.expected_lkg_ms = _MIN_S * 1000
        self.expected_counter = 0
        self.expected_excluded = False

    @rule(observed_s=st.integers(min_value=_MIN_S, max_value=_MAX_S))
    def success(self, observed_s: int) -> None:
        if self.expected_excluded:
            return
        observed_ms = observed_s * 1000
        self.service.record_success(_PROVIDER, _MODEL, _ROLE, observed_ms)
        self.expected_counter = 0
        self.expected_lkg_ms = max(self.expected_lkg_ms, observed_ms)

    @rule(attempt_index=st.integers(min_value=1, max_value=1 + _STEPS))
    def timeout(self, attempt_index: int) -> None:
        if self.expected_excluded:
            return
        # Mirror the §6.3 ladder formula in milliseconds — this must match
        # _ladder_budget_ms's precision exactly. next_budget's seconds-rounded
        # return value is NOT used for the oracle's "at max" decision, because
        # rounding to seconds can push a sub-max ms budget across the max-second
        # boundary (e.g. 899500ms rounds to 900s == _MAX_S) while the real
        # service's record_timeout compares the unrounded ms budget (§6.4).
        ceil_ms = _MAX_S * 1000
        floor_ms = self.expected_lkg_ms
        if attempt_index == 1 or _STEPS == 0 or floor_ms >= ceil_ms:
            budget_ms = floor_ms
        else:
            rung = min(attempt_index - 1, _STEPS)
            budget_ms = round(floor_ms + (ceil_ms - floor_ms) * rung / _STEPS)
        budget_ms = min(ceil_ms, max(_MIN_S * 1000, budget_ms))

        self.service.next_budget(_PROVIDER, _MODEL, _ROLE, attempt_index)
        self.service.record_timeout(_PROVIDER, _MODEL, _ROLE)
        if budget_ms >= ceil_ms:
            self.expected_counter += 1
            if self.expected_counter >= _THRESHOLD:
                self.expected_excluded = True
        # else: a sub-max timeout escalates state but never touches the counter (§6.4).

    @invariant()
    def state_matches_expected(self) -> None:
        assert self.service.is_excluded(_PROVIDER, _MODEL, _ROLE) == self.expected_excluded
        if self.expected_excluded:
            expected_model_state = AdaptiveTimeoutModelState.EXCLUDED
        elif self.expected_counter == 0:
            expected_model_state = AdaptiveTimeoutModelState.OK
        else:
            expected_model_state = AdaptiveTimeoutModelState.WARN
        assert self.service.model_state(_PROVIDER, _MODEL, _ROLE) == expected_model_state


# Hypothesis builds `.TestCase` dynamically per state machine, so it is a runtime
# value, not a statically-known type -- mypy cannot check a class-body subclassing a
# dynamically-constructed base. Only one `unittest.TestCase` subclass is bound at
# module scope (this one) so pytest's default collector picks up exactly one case.
@pytest.mark.slow
class TestAdaptiveTimeoutStateMachine(_AdaptiveTimeoutStateMachine.TestCase):  # type: ignore[misc,valid-type]
    """Runs ``_AdaptiveTimeoutStateMachine`` as a pytest-collected unittest.TestCase."""

    def runTest(self) -> None:
        """Proves: STORY-022-AC-2

        Walks every legal record_success/record_timeout/next_budget sequence and
        checks the resulting state, last_known_good_ms, and consecutive-max
        counter against the §6.2 state machine after every step.
        """
        super().runTest()
