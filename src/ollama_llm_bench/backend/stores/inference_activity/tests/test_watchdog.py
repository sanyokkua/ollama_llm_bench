"""Per-activity watchdog tests for ``InferenceActivityGate`` (STORY-015-AC-5, AC-6, EC-RUN-14)."""

import pytest

from ollama_llm_bench.backend.domain.models import InferenceActivity, InferenceActivityContext
from ollama_llm_bench.backend.events.models import SIGNAL_INFERENCE_ACTIVITY_CHANGED
from ollama_llm_bench.backend.stores.inference_activity._internal.gate import (
    InferenceActivityGate,
)
from ollama_llm_bench.backend.stores.inference_activity.tests.conftest import (
    FakeClock,
    SpyEventBus,
)


def _make_context(*, activity: InferenceActivity) -> InferenceActivityContext:
    return InferenceActivityContext(activity=activity, started_at=0)


@pytest.mark.parametrize(
    "activity,timeout_ms,auto_released",
    [
        (InferenceActivity.BENCHMARK_RUN, 10 * 60 * 1000 * 100, False),
        (InferenceActivity.JUDGE_ANALYSIS, 10 * 60 * 1000, True),
        (InferenceActivity.PROVIDER_TEST, 60 * 1000, True),
        (InferenceActivity.READINESS_PROBE, 30 * 1000, True),
    ],
    ids=["benchmark_run_never", "judge_analysis_10min", "provider_test_60s", "readiness_probe_30s"],
)
def test_watchdog_auto_release_per_activity(
    fake_clock: FakeClock,
    spy_event_bus: SpyEventBus,
    activity: InferenceActivity,
    timeout_ms: int,
    *,
    auto_released: bool,
) -> None:
    """Proves: STORY-015-AC-5

    Covers: EC-RUN-14

    For each non-pipeline activity, holding the gate longer than its watchdog timeout
    without releasing causes an auto-release (gate returns to IDLE, one
    ``_inference_activity_changed`` event is emitted for the release); BENCHMARK_RUN
    has no watchdog and is never auto-released, even past a very long elapsed time.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    context = _make_context(activity=activity)
    lease = gate.try_acquire(activity, context)
    assert lease is not None
    events_after_acquire = len(spy_event_bus.emitted)

    # Act
    fake_clock.advance_monotonic_ms(timeout_ms)
    state = gate.state()

    # Assert
    assert (state.current == InferenceActivity.IDLE) is auto_released
    changed_events_after = [
        e for e in spy_event_bus.emitted if e[0] == SIGNAL_INFERENCE_ACTIVITY_CHANGED
    ]
    expected_additional_events = 1 if auto_released else 0
    assert len(changed_events_after) == events_after_acquire + expected_additional_events


def test_watchdog_does_not_fire_before_its_timeout_elapses(
    fake_clock: FakeClock, spy_event_bus: SpyEventBus
) -> None:
    """Proves: STORY-015-AC-5

    Covers: EC-RUN-14

    A non-pipeline activity held for less than its watchdog timeout is not
    auto-released — the gate stays held by the original activity.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    context = _make_context(activity=InferenceActivity.READINESS_PROBE)
    lease = gate.try_acquire(InferenceActivity.READINESS_PROBE, context)
    assert lease is not None

    # Act
    fake_clock.advance_monotonic_ms(30 * 1000 - 1)
    state = gate.state()

    # Assert
    assert state.current == InferenceActivity.READINESS_PROBE


def test_late_release_after_watchdog_noops_and_reacquire_succeeds(
    fake_clock: FakeClock, spy_event_bus: SpyEventBus
) -> None:
    """Proves: STORY-015-AC-6

    Covers: EC-RUN-14

    Given a watchdog has auto-released an abandoned activity's lease, the abandoned
    holder's own late release afterwards is a no-op, and a fresh try_acquire issued
    after the watchdog fired succeeds normally.
    """
    # Arrange
    gate = InferenceActivityGate(clock=fake_clock, event_bus=spy_event_bus)
    context = _make_context(activity=InferenceActivity.PROVIDER_TEST)
    abandoned_lease = gate.try_acquire(InferenceActivity.PROVIDER_TEST, context)
    assert abandoned_lease is not None
    fake_clock.advance_monotonic_ms(60 * 1000)
    assert gate.state().current == InferenceActivity.IDLE  # watchdog fired

    # Act
    new_context = _make_context(activity=InferenceActivity.READINESS_PROBE)
    new_lease = gate.try_acquire(InferenceActivity.READINESS_PROBE, new_context)
    gate.release(abandoned_lease)

    # Assert
    assert new_lease is not None
    state = gate.state()
    assert state.current == InferenceActivity.READINESS_PROBE
    assert state.context == new_context
