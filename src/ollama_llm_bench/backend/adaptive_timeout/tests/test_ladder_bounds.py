"""Proves STORY-022-AC-1 — the escalation ladder stays in bounds and lands on max."""

from hypothesis import given, strategies as st
import pytest

from ollama_llm_bench.backend.adaptive_timeout import make_adaptive_timeout_service
from ollama_llm_bench.backend.adaptive_timeout.tests.conftest import build_snapshot
from ollama_llm_bench.backend.domain import AdaptiveTimeoutRole


@st.composite
def _role_bounds(draw: st.DrawFn) -> tuple[int, int, int, int]:
    min_s = draw(st.integers(min_value=1, max_value=3600))
    max_s = draw(st.integers(min_value=min_s, max_value=3600))
    steps = draw(st.integers(min_value=0, max_value=10))
    attempt_index = draw(st.integers(min_value=1, max_value=steps + 5))
    return min_s, max_s, steps, attempt_index


@pytest.mark.slow
@given(_role_bounds())
def test_next_budget_stays_within_bounds_and_lands_on_max(
    bounds: tuple[int, int, int, int],
) -> None:
    """Proves: STORY-022-AC-1

    For any well-formed per-role min/max/steps configuration, next_budget stays
    within [min, max], equals min at attempt_index == 1, and lands exactly on
    max at attempt_index == 1 + escalation_steps.
    """
    min_s, max_s, steps, attempt_index = bounds
    snapshot = build_snapshot(
        min_timeout_seconds=min_s, max_timeout_seconds=max_s, retry_count=steps
    )
    service = make_adaptive_timeout_service(snapshot=snapshot)

    budget = service.next_budget("p1", "model-a", AdaptiveTimeoutRole.INFERENCE, attempt_index)

    assert min_s <= budget <= max_s
    if attempt_index == 1:
        assert budget == min_s
    # When steps == 0, attempt_index == 1 + steps coincides with attempt 1, whose
    # value is pinned to role.min by the ladder's attempt-1 collapse (§6.3) — the
    # "final retry lands on max" property only holds when there is at least one
    # retry to escalate across.
    if attempt_index == 1 + steps and steps > 0:
        assert budget == max_s
